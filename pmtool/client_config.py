"""Persist the non-sensitive desktop client configuration."""
from __future__ import annotations
import json
import os
from pathlib import Path
from pmtool.config import normalize_http_url
from pmtool.paths import get_data_dir

def client_config_path() -> Path:
    override = os.getenv("PMTOOL_CLIENT_CONFIG", "").strip()
    return Path(override).expanduser() if override else get_data_dir() / "client.json"

def load_base_url(path: Path | None = None) -> str | None:
    env_url = os.getenv("PM_BASE_URL", "").strip()
    if env_url:
        return normalize_http_url(env_url)
    config_path = path or client_config_path()
    if not config_path.is_file():
        return None
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        value = payload.get("base_url", "") if isinstance(payload, dict) else ""
        return normalize_http_url(str(value)) if value else None
    except (OSError, json.JSONDecodeError, ValueError):
        return None

def save_base_url(base_url: str, path: Path | None = None) -> str:
    normalized = normalize_http_url(base_url)
    config_path = path or client_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps({"base_url": normalized}, indent=2) + "\n", encoding="utf-8")
    return normalized
