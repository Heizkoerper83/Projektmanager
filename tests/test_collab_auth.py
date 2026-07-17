from __future__ import annotations

import http.client
import io
import json
import threading
import zipfile
import tempfile
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from pmtool.collab_server import _CollabHandler, _package_windows_app
from pmtool.collab_accounts import (
    activate_account,
    authenticate,
    create_account,
    ensure_api_keys,
    list_accounts,
    rotate_api_key,
    set_account_enabled,
)


TEST_PASSWORD = "secret123456"


class CollabAuthTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.accounts_path = Path(self.temp_dir.name) / "accounts.json"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_create_account_returns_activation_key_and_login_requires_activation(self) -> None:
        account = create_account("alice@example.com", password=TEST_PASSWORD, role="reader", path=self.accounts_path)
        activation_key = account["activation_api_key"]

        self.assertTrue(activation_key.startswith("act_"))
        self.assertIsNone(authenticate(email="alice@example.com", password=TEST_PASSWORD, path=self.accounts_path))

    def test_new_account_is_pending(self) -> None:
        create_account("alice@example.com", password=TEST_PASSWORD, role="reader", path=self.accounts_path)

        rows = list_accounts(self.accounts_path)
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["enabled"])
        self.assertEqual(rows[0]["status"], "pending")

    def test_activation_with_wrong_key_fails(self) -> None:
        create_account("alice@example.com", password=TEST_PASSWORD, role="reader", path=self.accounts_path)

        with self.assertRaises(ValueError):
            activate_account("alice@example.com", "act_wrong", path=self.accounts_path)

    def test_activation_with_correct_key_enables_login(self) -> None:
        account = create_account("alice@example.com", password=TEST_PASSWORD, role="reader", path=self.accounts_path)
        activation_key = account["activation_api_key"]

        result = activate_account("alice@example.com", activation_key, path=self.accounts_path)
        self.assertTrue(result["enabled"])

        principal = authenticate(email="alice@example.com", password=TEST_PASSWORD, path=self.accounts_path)
        self.assertIsNotNone(principal)
        self.assertEqual(principal["name"], "alice@example.com")

    def test_migration_generates_missing_keys_for_legacy_accounts(self) -> None:
        self.accounts_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "accounts": [
                        {
                            "name": "legacy",
                            "role": "editor",
                            "enabled": True,
                            "created_at": "2026-01-01T00:00:00",
                        }
                    ],
                    "audit_log": [],
                }
            ),
            encoding="utf-8",
        )

        generated = ensure_api_keys(self.accounts_path)
        self.assertEqual(len(generated), 1)
        self.assertEqual(generated[0]["email"], "legacy@local.invalid")

        data = json.loads(self.accounts_path.read_text(encoding="utf-8"))
        account = data["accounts"][0]
        self.assertIn("api_key_hash", account)
        self.assertNotIn("api_key", account)

        self.assertIsNone(authenticate(email="legacy@example.com", password="anything", path=self.accounts_path))


    def test_web_app_has_separate_browser_pages(self) -> None:
        from pmtool.collab_server import _app_html

        principal = {"name": "alice@example.com", "role": "editor"}

        app_html = _app_html(principal, current_path="/app")

        self.assertIn("const currentPage = 'app';", app_html)
        self.assertIn('<article class="readme">', app_html)
        self.assertIn("Projektmanager", app_html)
        self.assertIn("const currentPage = 'projects';", _app_html(principal, current_path="/projects"))
        self.assertIn("const currentPage = 'downloads';", _app_html(principal, current_path="/downloads"))
        self.assertIn("const currentPage = 'reports';", _app_html(principal, current_path="/reports"))

    def test_web_logout_redirects_to_login_and_invalidates_session(self) -> None:
        create_account("alice@example.com", password=TEST_PASSWORD, role="editor", path=self.accounts_path)
        set_account_enabled("alice@example.com", True, path=self.accounts_path)

        server = ThreadingHTTPServer(("127.0.0.1", 0), _CollabHandler)
        server.sessions = {}
        server.sessions_lock = threading.Lock()
        server.desktop_logins = {}
        server.desktop_logins_lock = threading.Lock()
        server.request_log = {}
        server.request_log_lock = threading.Lock()
        server.accounts_path = self.accounts_path
        server.config = type("Config", (), {"public_base_url": "", "trust_proxy_headers": False})()

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host, port = server.server_address
        try:
            conn = http.client.HTTPConnection(host, port, timeout=5)
            body = f"email=alice%40example.com&password={TEST_PASSWORD}"
            conn.request("POST", "/login", body=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
            login_response = conn.getresponse()
            login_response.read()
            cookie = login_response.getheader("Set-Cookie") or ""
            session_cookie = cookie.split(";", 1)[0]

            self.assertEqual(login_response.status, 302)
            self.assertTrue(session_cookie.startswith("PMTOOL_SESSION="))
            self.assertIn(session_cookie.split("=", 1)[1], server.sessions)

            conn.request("GET", "/logout", headers={"Cookie": session_cookie})
            logout_response = conn.getresponse()
            logout_response.read()
            clear_cookie = logout_response.getheader("Set-Cookie") or ""

            self.assertEqual(logout_response.status, 302)
            self.assertEqual(logout_response.getheader("Location"), "/login")
            self.assertIn("PMTOOL_SESSION=", clear_cookie)
            self.assertIn("Max-Age=0", clear_cookie)
            self.assertNotIn(session_cookie.split("=", 1)[1], server.sessions)

            conn.request("GET", "/app", headers={"Cookie": session_cookie})
            app_response = conn.getresponse()
            app_response.read()

            self.assertEqual(app_response.status, 302)
            self.assertEqual(app_response.getheader("Location"), "/login")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_windows_app_package_contains_exe_config_and_start_script(self) -> None:
        archive = _package_windows_app(
            base_url="http://100.80.250.84:8765",
            exe_data=b"fake-exe",
            checksum_data=b"fake-hash  pr.exe\n",
        )

        with zipfile.ZipFile(io.BytesIO(archive)) as zip_file:
            names = set(zip_file.namelist())
            self.assertIn("pr.exe", names)
            self.assertIn("pr.exe.sha256", names)
            self.assertIn("pmtool_server.json", names)
            self.assertIn("start-projektmanager.bat", names)
            self.assertIn("README.txt", names)

            config = json.loads(zip_file.read("pmtool_server.json").decode("utf-8"))
            start_script = zip_file.read("start-projektmanager.bat").decode("utf-8")

        self.assertEqual(config["base_url"], "http://100.80.250.84:8765")
        self.assertIn('set "PM_BASE_URL=http://100.80.250.84:8765"', start_script)

    def test_rotate_api_key_still_works(self) -> None:
        create_account("alice@example.com", password=TEST_PASSWORD, role="editor", path=self.accounts_path)

        rotated = rotate_api_key("alice@example.com", path=self.accounts_path)
        new_key = rotated["api_key"]

        self.assertTrue(new_key.startswith("pmk_"))


if __name__ == "__main__":
    unittest.main()