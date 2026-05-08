"""Shared path resolution for local data files."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

DATA_DIR_ENV = "PMTOOL_DATA_DIR"
ACCOUNTS_FILENAME = "collab_accounts.json"
DB_FILENAME = "app.db"


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    deduped: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(resolved)
    return deduped


def _candidate_dirs() -> list[Path]:
    candidates: list[Path] = []
    env_dir = os.environ.get(DATA_DIR_ENV)
    if env_dir:
        candidates.append(Path(env_dir).expanduser())

    if _is_frozen():
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend([exe_dir, exe_dir.parent])
    else:
        candidates.append(Path.cwd())
        candidates.append(Path(__file__).resolve().parents[1])

    return _dedupe_paths(candidates)


def _has_data_files(directory: Path) -> bool:
    return (directory / ACCOUNTS_FILENAME).exists() or (directory / DB_FILENAME).exists()


def _copy_if_missing(source: Path, destination: Path) -> None:
    if destination.exists() or not source.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _maybe_migrate_data(target_dir: Path) -> None:
    if _has_data_files(target_dir):
        return
    for candidate in _candidate_dirs():
        if candidate == target_dir:
            continue
        if not _has_data_files(candidate):
            continue
        _copy_if_missing(candidate / ACCOUNTS_FILENAME, target_dir / ACCOUNTS_FILENAME)
        _copy_if_missing(candidate / DB_FILENAME, target_dir / DB_FILENAME)
        return


def get_data_dir() -> Path:
    env_dir = os.environ.get(DATA_DIR_ENV)
    if env_dir:
        resolved = Path(env_dir).expanduser().resolve()
        resolved.mkdir(parents=True, exist_ok=True)
        return resolved

    appdata = os.environ.get("APPDATA")
    fallback = Path(appdata) / "pmtool" if appdata else Path.home() / ".pmtool"
    fallback.mkdir(parents=True, exist_ok=True)
    _maybe_migrate_data(fallback)
    return fallback


def get_accounts_path() -> Path:
    return get_data_dir() / ACCOUNTS_FILENAME


def get_db_path() -> Path:
    return get_data_dir() / DB_FILENAME
