"""Build the Windows EXE and copy it to the repository root."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _write_checksum(path: Path, digest: str) -> None:
    path.write_text(f"{digest}  {path.name}\n", encoding="utf-8")


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    exe_name = "pr.exe"
    dist_exe = repo_root / "dist" / exe_name
    root_exe = repo_root / exe_name

    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(repo_root / "pr.spec")],
        cwd=repo_root,
        check=True,
    )

    if not dist_exe.exists():
        raise FileNotFoundError(f"Build erfolgreich, aber {dist_exe} wurde nicht gefunden")

    shutil.copy2(dist_exe, root_exe)

    dist_digest = _sha256(dist_exe)
    root_digest = _sha256(root_exe)
    _write_checksum(dist_exe.with_name(f"{exe_name}.sha256"), dist_digest)
    _write_checksum(root_exe.with_name(f"{exe_name}.sha256"), root_digest)

    print(f"Built: {dist_exe}")
    print(f"Copied to: {root_exe}")
    print(f"SHA256: {root_digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
