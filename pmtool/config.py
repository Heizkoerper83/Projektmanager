"""Central, environment-backed configuration for client and server."""
from __future__ import annotations
from dataclasses import dataclass
import os
from pathlib import Path
from urllib.parse import urlparse
from pmtool.paths import get_data_dir

DEFAULT_GITHUB_REPOSITORY = "Heizkoerper83/Projektmanager"

def normalize_http_url(value: str) -> str:
    value = str(value or "").strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Server-URL muss mit http:// oder https:// beginnen")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Server-URL darf keine Zugangsdaten, Query oder Fragment enthalten")
    return value

def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}

@dataclass(frozen=True)
class ServerConfig:
    public_base_url: str | None
    trust_proxy_headers: bool
    github_repository: str
    fallback_exe_path: Path
    orphan_project_owner: str | None

    @classmethod
    def from_env(cls) -> "ServerConfig":
        public_url = os.getenv("PMTOOL_PUBLIC_BASE_URL", "").strip()
        return cls(
            public_base_url=normalize_http_url(public_url) if public_url else None,
            trust_proxy_headers=_env_bool("PMTOOL_TRUST_PROXY_HEADERS"),
            github_repository=os.getenv("PMTOOL_GITHUB_REPOSITORY", DEFAULT_GITHUB_REPOSITORY).strip(),
            fallback_exe_path=Path(os.getenv("PMTOOL_FALLBACK_EXE", str(get_data_dir() / "releases" / "pr.exe"))).expanduser(),
            orphan_project_owner=os.getenv("PMTOOL_ORPHAN_PROJECT_OWNER", "").strip().lower() or None,
        )
