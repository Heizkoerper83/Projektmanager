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
    base_url = os.getenv("PM_BASE_URL", "https://100.80.250.84:8765")
    return base_url.rstrip("/")


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
                if isinstance(account, dict):
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
