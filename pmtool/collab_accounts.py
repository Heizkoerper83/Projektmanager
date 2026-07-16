"""Account and API-key management for collaboration server."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any

from pmtool.paths import get_accounts_path

try:
    import bcrypt
except ImportError:
    raise ImportError("bcrypt erforderlich: pip install bcrypt")


DEFAULT_ACCOUNTS_PATH = get_accounts_path()
ALLOWED_ROLES = {"reader", "editor", "admin"}
MIN_PASSWORD_LENGTH = 8
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
API_KEY_PREFIX = "pmk_"
ACTIVATION_KEY_PREFIX = "act_"

logger = logging.getLogger(__name__)


def _now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (TypeError, ValueError):
        return False


def _generate_api_key() -> str:
    return f"{API_KEY_PREFIX}{secrets.token_urlsafe(24)}"


def _hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def _verify_api_key(api_key: str, api_key_hash: str) -> bool:
    if not api_key or not api_key_hash:
        return False
    return secrets.compare_digest(_hash_api_key(api_key), api_key_hash)


def _hash_activation_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _verify_activation_key(key: str, key_hash: str) -> bool:
    if not key or not key_hash:
        return False
    return secrets.compare_digest(_hash_activation_key(key), key_hash)


def _generate_activation_key() -> str:
    return f"{ACTIVATION_KEY_PREFIX}{secrets.token_urlsafe(24)}"

def _validate_password(password: str) -> None:
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Passwort muss mindestens {MIN_PASSWORD_LENGTH} Zeichen lang sein")


def _normalize_email(email: str) -> str:
    clean_email = (email or "").strip().lower()
    if not EMAIL_REGEX.match(clean_email):
        raise ValueError("Ungueltige E-Mail-Adresse")
    return clean_email


def _coerce_email_identifier(value: str) -> str:
    clean = (value or "").strip().lower()
    if EMAIL_REGEX.match(clean):
        return clean
    safe = re.sub(r"[^a-z0-9._+-]+", "-", clean).strip("-")
    if not safe:
        safe = "account"
    return f"{safe}@local.invalid"


def _account_email(item: dict[str, Any]) -> str:
    value = str(item.get("email", item.get("name", ""))).strip().lower()
    return _coerce_email_identifier(value)


def _load_data(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 3, "accounts": [], "audit_log": []}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Ungueltige Account-Datei")
    raw.setdefault("version", 3)
    raw.setdefault("accounts", [])
    raw.setdefault("audit_log", [])
    if not isinstance(raw["accounts"], list):
        raise ValueError("Ungueltige Account-Datei")
    if not isinstance(raw["audit_log"], list):
        raw["audit_log"] = []
    return raw


def _save_data(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _append_audit(data: dict[str, Any], action: str, username: str = "", details: str = "", status: str = "success") -> None:
    data.setdefault("audit_log", []).append(
        {
            "timestamp": _now_text(),
            "action": action,
            "username": username,
            "details": details,
            "status": status,
        }
    )
    if len(data["audit_log"]) > 1000:
        data["audit_log"] = data["audit_log"][-1000:]


def _log_audit(path: Path, action: str, username: str = "", details: str = "", status: str = "success") -> None:
    data = _load_data(path)
    _append_audit(data, action, username=username, details=details, status=status)
    _save_data(path, data)
    logger.info("[AUDIT] %s: %s - %s", action, username, status)


def _normalize_role(role: str) -> str:
    value = role.strip().lower()
    if value not in ALLOWED_ROLES:
        raise ValueError("Rolle muss 'reader', 'editor' oder 'admin' sein")
    return value


def ensure_api_keys(path: str | Path = DEFAULT_ACCOUNTS_PATH) -> list[dict[str, str]]:
    """Ensure every account has required hashes and return newly generated plain API keys once."""
    file_path = Path(path)
    data = _load_data(file_path)
    changed = False
    generated_keys: list[dict[str, str]] = []

    for item in data["accounts"]:
        account_email = _account_email(item) or "unknown@example.invalid"
        item["email"] = account_email
        item["name"] = account_email
        if "enabled" not in item:
            item["enabled"] = True
            changed = True
        if "failed_login_attempts" not in item:
            item["failed_login_attempts"] = 0
            changed = True
        if not str(item.get("password_hash", "")).strip():
            # For migrated accounts without password, set a temporary reset secret.
            item["password_hash"] = _hash_password(secrets.token_urlsafe(18))
            changed = True

        api_key_hash = str(item.get("api_key_hash", "")).strip()
        legacy_plain = str(item.get("api_key", "")).strip()

        if not api_key_hash:
            if legacy_plain:
                item["api_key_hash"] = _hash_api_key(legacy_plain)
            else:
                new_key = _generate_api_key()
                item["api_key_hash"] = _hash_api_key(new_key)
                generated_keys.append({"email": account_email, "api_key": new_key})
            changed = True

        # Disabled accounts are treated as pending and require activation key.
        activation_hash = str(item.get("activation_api_key_hash", "")).strip()
        if not bool(item.get("enabled", True)) and not activation_hash:
            activation_key = _generate_activation_key()
            item["activation_api_key_hash"] = _hash_activation_key(activation_key)
            _append_audit(
                data,
                "generate_activation_api_key",
                username=account_email,
                details="Automatisch fuer pending Account erzeugt",
            )
            changed = True

        if "api_key" in item:
            # Remove plaintext key from persisted storage.
            item.pop("api_key", None)
            changed = True

    if changed:
        data["version"] = 3
        for entry in generated_keys:
            _append_audit(
                data,
                "generate_api_key",
                username=entry["email"],
                details="Automatisch fuer bestehenden Account erzeugt",
            )
        _save_data(file_path, data)

    return generated_keys

def list_accounts(path: str | Path = DEFAULT_ACCOUNTS_PATH) -> list[dict[str, Any]]:
    """List all user accounts with their status and metadata.
    
    Args:
        path: Path to accounts database file
        
    Returns:
        List of account dicts with email, role, status, creation date, API keys, etc.
    """
    data = _load_data(Path(path))
    return [
        {
            "email": _account_email(item),
            "name": _account_email(item),
            "role": item.get("role", "reader"),
            "enabled": bool(item.get("enabled", True)),
            "created_at": item.get("created_at", ""),
            "last_used_at": item.get("last_used_at"),
            "failed_login_attempts": item.get("failed_login_attempts", 0),
            "has_password": bool(item.get("password_hash")),
            "has_api_key": bool(item.get("api_key_hash")),
            "has_activation_key": bool(item.get("activation_api_key_hash")),
            "status": "aktiv" if bool(item.get("enabled", True)) else "pending",
        }
        for item in data["accounts"]
    ]


def create_account(
    email: str,
    password: str,
    role: str = "reader",
    path: str | Path = DEFAULT_ACCOUNTS_PATH,
) -> dict[str, Any]:
    """Create a new user account with email and password.
    
    Account is created in pending state and requires activation with activation_api_key.
    
    Args:
        email: User email address (must be valid format)
        password: User password (minimum 8 characters)
        role: User role ('reader' or 'editor', default: 'reader')
        path: Path to accounts database file
        
    Returns:
        Account info dict with email, role, created_at, and activation_api_key
        
    Raises:
        ValueError: If email invalid, password too short, or account exists
    """
    clean_email = _normalize_email(email)
    _validate_password(password)
    clean_role = _normalize_role(role)
    file_path = Path(path)
    data = _load_data(file_path)

    for item in data["accounts"]:
        if _account_email(item) == clean_email:
            raise ValueError(f"Account '{clean_email}' existiert bereits")

    activation_key = _generate_activation_key()
    account: dict[str, Any] = {
        "name": clean_email,
        "email": clean_email,
        "role": clean_role,
        "enabled": False,
        "api_key_hash": _hash_api_key(_generate_api_key()),
        "activation_api_key_hash": _hash_activation_key(activation_key),
        "created_at": _now_text(),
        "last_used_at": None,
        "failed_login_attempts": 0,
        "password_hash": _hash_password(password),
    }

    data["accounts"].append(account)
    _append_audit(data, "create_account", clean_email, f"Role: {clean_role}")
    _save_data(file_path, data)

    return {
        "email": clean_email,
        "name": clean_email,
        "role": account["role"],
        "enabled": account["enabled"],
        "created_at": account["created_at"],
        "activation_api_key": activation_key,
    }


def activate_account(
    email: str,
    activation_api_key: str,
    path: str | Path = DEFAULT_ACCOUNTS_PATH,
) -> dict[str, Any]:
    """Activate a pending account with activation API key.
    
    Args:
        email: User email address
        activation_api_key: Secret activation key (provided during account creation)
        path: Path to accounts database file
        
    Returns:
        Account info dict with email, role, and created_at
        
    Raises:
        ValueError: If account not found, already activated, or activation key invalid
    """
    clean_email = _normalize_email(email)
    if not activation_api_key:
        raise ValueError("Aktivierungs-API-Key ist erforderlich")

    file_path = Path(path)
    data = _load_data(file_path)

    for item in data["accounts"]:
        if _account_email(item) != clean_email:
            continue

        if bool(item.get("enabled", True)):
            raise ValueError(f"Account '{clean_email}' ist bereits aktiviert")

        activation_hash = str(item.get("activation_api_key_hash", "")).strip()
        if not _verify_activation_key(activation_api_key, activation_hash):
            _append_audit(data, "activate_account_failed", clean_email, "Ungültiger Aktivierungs-API-Key", "failed")
            _save_data(file_path, data)
            raise ValueError("Ungültiger Aktivierungs-API-Key")

        item["enabled"] = True
        item["activation_api_key_hash"] = ""
        item["failed_login_attempts"] = 0
        _append_audit(data, "activate_account", clean_email, "Account aktiviert")
        _save_data(file_path, data)

        return {
            "email": _account_email(item),
            "name": _account_email(item),
            "role": item.get("role", "reader"),
            "enabled": True,
            "created_at": item.get("created_at", ""),
        }

    raise ValueError(f"Account '{clean_email}' nicht gefunden")


def set_password(email: str, password: str, path: str | Path = DEFAULT_ACCOUNTS_PATH) -> None:
    _validate_password(password)

    clean_email = _normalize_email(email)
    file_path = Path(path)
    data = _load_data(file_path)

    for item in data["accounts"]:
        if _account_email(item) == clean_email:
            item["password_hash"] = _hash_password(password)
            item["failed_login_attempts"] = 0
            _save_data(file_path, data)
            _log_audit(file_path, "set_password", clean_email)
            return
    raise ValueError(f"Account '{clean_email}' nicht gefunden")


def rotate_api_key(email: str, path: str | Path = DEFAULT_ACCOUNTS_PATH) -> dict[str, str]:
    clean_email = _normalize_email(email)
    file_path = Path(path)
    data = _load_data(file_path)

    for item in data["accounts"]:
        if _account_email(item) == clean_email:
            new_api_key = _generate_api_key()
            item["api_key_hash"] = _hash_api_key(new_api_key)
            item["failed_login_attempts"] = 0
            account_email = _account_email(item)
            _append_audit(data, "rotate_api_key", account_email, "API-Key rotiert")
            _save_data(file_path, data)
            return {"email": account_email, "api_key": new_api_key}

    raise ValueError(f"Account '{clean_email}' nicht gefunden")


def delete_account(email: str, path: str | Path = DEFAULT_ACCOUNTS_PATH) -> None:
    clean_email = _normalize_email(email)
    file_path = Path(path)
    data = _load_data(file_path)
    filtered = [item for item in data["accounts"] if _account_email(item) != clean_email]
    if len(filtered) == len(data["accounts"]):
        raise ValueError(f"Account '{clean_email}' nicht gefunden")
    data["accounts"] = filtered
    _save_data(file_path, data)
    _log_audit(file_path, "delete_account", clean_email)


def set_account_enabled(email: str, enabled: bool, path: str | Path = DEFAULT_ACCOUNTS_PATH) -> None:
    clean_email = _normalize_email(email)
    file_path = Path(path)
    data = _load_data(file_path)
    for item in data["accounts"]:
        if _account_email(item) == clean_email:
            item["enabled"] = bool(enabled)
            item["failed_login_attempts"] = 0
            _save_data(file_path, data)
            status = "enabled" if enabled else "disabled"
            _log_audit(file_path, "set_account_enabled", clean_email, f"Status: {status}")
            return
    raise ValueError(f"Account '{clean_email}' nicht gefunden")


def set_account_role(email: str, role: str, path: str | Path = DEFAULT_ACCOUNTS_PATH) -> None:
    clean_email = _normalize_email(email)
    clean_role = _normalize_role(role)
    file_path = Path(path)
    data = _load_data(file_path)
    for item in data["accounts"]:
        if _account_email(item) == clean_email:
            item["role"] = clean_role
            _save_data(file_path, data)
            _log_audit(file_path, "set_account_role", clean_email, f"New role: {clean_role}")
            return
    raise ValueError(f"Account '{clean_email}' nicht gefunden")


def authenticate(
    email: str,
    password: str,
    path: str | Path = DEFAULT_ACCOUNTS_PATH,
) -> dict[str, Any] | None:
    """Authenticate user with email and password.
    
    Returns user principal info if successful, None otherwise.
    Locks account after 5 failed login attempts.
    Disables account if not yet activated.
    
    Args:
        email: User email address
        password: User password
        path: Path to accounts database file
        
    Returns:
        Dict with 'name' and 'role' keys if successful, None if failed or account locked
    """
    if not email or not password:
        return None

    clean_email = _normalize_email(email)
    file_path = Path(path)
    data = _load_data(file_path)

    principal: dict[str, Any] | None = None
    found = False

    for item in data["accounts"]:
        if _account_email(item) != clean_email:
            continue

        found = True
        failed_attempts = int(item.get("failed_login_attempts", 0) or 0)
        if failed_attempts >= 5:
            _append_audit(data, "login_failed", clean_email, "Account locked (too many attempts)", "failed")
            _save_data(file_path, data)
            return None

        if not bool(item.get("enabled", True)):
            _append_audit(data, "login_failed", clean_email, "Account disabled", "failed")
            _save_data(file_path, data)
            return None

        password_hash = str(item.get("password_hash", "")).strip()
        if not password_hash:
            item["failed_login_attempts"] = failed_attempts + 1
            _append_audit(data, "login_failed", clean_email, "Kein Passwort gesetzt", "failed")
            _save_data(file_path, data)
            return None

        if not _verify_password(password, password_hash):
            item["failed_login_attempts"] = failed_attempts + 1
            _append_audit(data, "login_failed", clean_email, f"Ungueltiges Passwort ({item['failed_login_attempts']}/5)", "failed")
            _save_data(file_path, data)
            return None

        principal = {
            "name": item.get("name", ""),
            "role": item.get("role", "reader"),
            "enabled": bool(item.get("enabled", True)),
        }
        item["last_used_at"] = _now_text()
        item["failed_login_attempts"] = 0
        _append_audit(data, "login_success", clean_email)
        _save_data(file_path, data)
        break

    if not found:
        _append_audit(data, "login_failed", clean_email, "User not found", "failed")
        _save_data(file_path, data)

    return principal


def authorize_account_creation_api_key(
    api_key: str,
    path: str | Path = DEFAULT_ACCOUNTS_PATH,
    require_editor: bool = True,
) -> dict[str, Any] | None:
    """Authorize account creation via API key of an existing enabled account."""
    if not api_key:
        return None

    file_path = Path(path)
    data = _load_data(file_path)

    for item in data["accounts"]:
        if not bool(item.get("enabled", True)):
            continue
        role = str(item.get("role", "reader"))
        if require_editor and role != "editor":
            continue
        api_key_hash = str(item.get("api_key_hash", "")).strip()
        if _verify_api_key(api_key, api_key_hash):
            item["last_used_at"] = _now_text()
            principal = {
                "name": _account_email(item),
                "role": role,
                "enabled": bool(item.get("enabled", True)),
            }
            _append_audit(data, "account_creation_api_key_auth_success", _account_email(item))
            _save_data(file_path, data)
            return principal

    return None


def get_audit_log(path: str | Path = DEFAULT_ACCOUNTS_PATH, limit: int = 100) -> list[dict[str, Any]]:
    """Retrieve audit log entries (account actions like login, account creation, etc).
    
    Args:
        path: Path to accounts database file
        limit: Maximum number of entries to return (default 100)
        
    Returns:
        List of audit log entries, most recent first
    """
    data = _load_data(Path(path))
    audit_log = data.get("audit_log", [])
    return audit_log[-limit:][::-1]


