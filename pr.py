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
from pmtool.client_config import load_base_url, save_base_url


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
    configured = load_base_url()
    if configured:
        return _normalize_base_url(configured)

    prompt = "Adresse des Projektmanager-Servers (z.B. https://pm.example.com): "
    value = ""
    try:
        import tkinter as tk
        from tkinter import simpledialog
        root = tk.Tk()
        root.withdraw()
        value = simpledialog.askstring("Projektmanager einrichten", prompt, parent=root) or ""
        root.destroy()
    except Exception:
        if sys.stdin.isatty():
            value = input(prompt).strip()
    if not value:
        raise ValueError("Keine Server-URL konfiguriert.")
    return _normalize_base_url(save_base_url(value))


def _check_server(base_url: str) -> None:
    request = urllib.request.Request(base_url.rstrip("/") + "/login", method="GET")
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            if response.status >= 400:
                raise ValueError(f"Server antwortet mit HTTP {response.status}.")
    except urllib.error.URLError as exc:
        raise ValueError(f"Server ist nicht erreichbar: {exc.reason}") from exc


def _normalize_base_url(base_url: str) -> str:
    base_url = base_url.strip().rstrip("/")
    try:
        parsed = urllib.parse.urlparse(base_url)
    except Exception:
        return base_url
    if parsed.hostname and parsed.scheme in ("http", "https"):
        netloc = parsed.hostname
        if parsed.username and parsed.password:
            netloc = f"{parsed.username}:{parsed.password}@{netloc}"
        if parsed.scheme == "https" and parsed.port == 8765:
            return urllib.parse.urlunparse(parsed._replace(netloc=netloc))
        if parsed.scheme == "http" and parsed.port is None:
            return urllib.parse.urlunparse(parsed._replace(netloc=f"{netloc}:8765"))
        return urllib.parse.urlunparse(parsed)
    return base_url


def _login_base_url(sync_base_url: str) -> str:
    return sync_base_url.strip().rstrip("/")


def _new_desktop_token() -> str:
    return secrets.token_urlsafe(24)


def _wait_for_desktop_login(base_urls: list[str], token: str, timeout_seconds: float = 3600) -> dict[str, object] | None:
    endpoints: list[str] = []
    seen: set[str] = set()
    for base_url in base_urls:
        base = base_url.strip().rstrip("/")
        if not base or base in seen:
            continue
        seen.add(base)
        endpoints.append(f"{base}/api/desktop-login?{urllib.parse.urlencode({'token': token})}")

    start_time = time.time()

    while time.time() - start_time < timeout_seconds:
        for endpoint in endpoints:
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

        try:
            base_url = _base_url()
            _check_server(base_url)
        except ValueError as exc:
            print(f"Fehler: {exc}")
            return 1
        login_base_url = _login_base_url(base_url)
        desktop_token = _new_desktop_token()
        login_url = f"{login_base_url}/login?{urllib.parse.urlencode({'desktop_token': desktop_token})}"

        _open_browser_later(login_url)
        print("Warte auf Anmeldung im Browser auf dem bestehenden Server...")
        user = _wait_for_desktop_login([login_base_url, base_url], desktop_token)

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
