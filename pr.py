"""Entry point for the local project management tool."""

from __future__ import annotations

import json
import os
import secrets
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

from pmtool.cli import build_parser


def _open_browser_later(url: str, delay_seconds: float = 0.8) -> None:
    def _open() -> None:
        time.sleep(delay_seconds)
        try:
            opened = False
            try:
                opened = webbrowser.open(url)
            except Exception:
                opened = False
            if opened:
                return
        except Exception:
            pass

        # Platform-specific fallbacks (xdg-open / open / start)
        try:
            import subprocess
            import shutil
            import sys

            cmds = []
            if sys.platform.startswith("linux"):
                cmds = [["xdg-open", url], ["gio", "open", url], ["gvfs-open", url]]
            elif sys.platform == "darwin":
                cmds = [["open", url]]
            elif sys.platform.startswith("win"):
                cmds = [["cmd", "/c", "start", "", url]]

            for cmd in cmds:
                try:
                    if shutil.which(cmd[0]) or sys.platform.startswith("win"):
                        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        return
                except Exception:
                    continue
        except Exception:
            pass

        # Last attempt: ask webbrowser to get a controller and open
        try:
            try:
                browser = webbrowser.get()
                browser.open(url)
            except Exception:
                pass
        except Exception:
            pass

    thread = threading.Thread(target=_open, daemon=True)
    thread.start()



def _base_url() -> str:
    base_url = _load_base_url_from_config() or os.getenv("PM_BASE_URL", "https://100.80.250.84:8765")
    return _normalize_base_url(base_url)


def _normalize_base_url(base_url: str) -> str:
    base_url = base_url.strip().rstrip("/")
    try:
        urllib.parse.urlparse(base_url)
    except Exception:
        return base_url
    return base_url


def _load_base_url_from_config() -> str | None:
    config_name = "pmtool_server.json"
    candidates: list[Path] = []
    appdata = os.getenv("APPDATA")
    if appdata:
        candidates.append(Path(appdata) / "pmtool" / config_name)
    try:
        candidates.append(Path(sys.executable).resolve().parent / config_name)
    except (OSError, RuntimeError, ValueError):
        pass
    try:
        candidates.append(Path(sys.argv[0]).resolve().parent / config_name)
    except (OSError, RuntimeError, ValueError):
        pass
    candidates.append(Path.cwd() / config_name)
    candidates.append(Path.home() / config_name)
    for path in candidates:
        try:
            if not path.is_file():
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            base_url = str(payload.get("base_url", "")).strip()
            if base_url:
                return base_url
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue
    return None


def _new_desktop_token() -> str:
    return secrets.token_urlsafe(24)


def _wait_for_desktop_login(base_url: str, token: str, timeout_seconds: float = 3600) -> dict[str, object] | None:
    endpoint = f"{base_url}/api/desktop-login?{urllib.parse.urlencode({'token': token})}"
    start_time = time.time()

    while time.time() - start_time < timeout_seconds:
        try:
            with urllib.request.urlopen(endpoint, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("status") == "ready":
                account = payload.get("account")
                session_id = payload.get("session_id")
                if isinstance(account, dict):
                    if session_id:
                        account = dict(account)
                        account["session_id"] = session_id
                    return account
                return None
        except (urllib.error.URLError, json.JSONDecodeError):
            pass
        time.sleep(1.0)

    return None


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        from pmtool.gui import launch_gui

        base_url = _base_url()
        desktop_token = _new_desktop_token()
        login_url = f"{base_url}/login?{urllib.parse.urlencode({'desktop_token': desktop_token})}"

        _open_browser_later(login_url)
        print("Warte auf Anmeldung im Browser auf dem bestehenden Server...")
        user = _wait_for_desktop_login(base_url, desktop_token)

        if user is None:
            print("Anmeldungs-Timeout.")
            return 1

        print(f"Benutzer angemeldet: {user.get('name', 'Unbekannt')}")
        user = dict(user)
        user["base_url"] = base_url
        return launch_gui(user_data=user)

    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    try:
        result = args.func(args)
        if isinstance(result, int):
            return result
    except ValueError as exc:
        print(f"Fehler: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
