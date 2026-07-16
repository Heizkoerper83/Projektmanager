from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from pmtool.client_config import load_base_url, save_base_url
from pmtool.config import ServerConfig, normalize_http_url
from pmtool.collab_accounts import create_account
from pmtool.collab_server import _CollabHandler, _checksum_matches


class ConfigurationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_url_validation_rejects_unsafe_values(self) -> None:
        with self.assertRaises(ValueError):
            normalize_http_url("pm.example.com")
        with self.assertRaises(ValueError):
            normalize_http_url("https://user:secret@pm.example.com")

    def test_client_url_is_persisted(self) -> None:
        save_base_url("https://pm.example.com/", self.path / "client.json")
        self.assertEqual(load_base_url(self.path / "client.json"), "https://pm.example.com")

    def test_environment_overrides_client_file(self) -> None:
        save_base_url("https://stored.example.com", self.path / "client.json")
        with mock.patch.dict(os.environ, {"PM_BASE_URL": "https://env.example.com"}):
            self.assertEqual(load_base_url(self.path / "client.json"), "https://env.example.com")

    def test_server_configuration_reads_proxy_settings(self) -> None:
        with mock.patch.dict(os.environ, {"PMTOOL_PUBLIC_BASE_URL": "https://pm.example.com", "PMTOOL_TRUST_PROXY_HEADERS": "1"}, clear=False):
            config = ServerConfig.from_env()
        self.assertTrue(config.trust_proxy_headers)
        self.assertEqual(config.public_base_url, "https://pm.example.com")

    def test_admin_is_a_supported_account_role(self) -> None:
        account = create_account("admin@example.com", "secret123", role="admin", path=self.path / "accounts.json")
        self.assertEqual(account["role"], "admin")

    def test_https_configuration_adds_secure_cookie_attribute(self) -> None:
        config = ServerConfig("https://pm.example.com", False, "owner/repo", self.path / "pr.exe", None)
        fake_handler = SimpleNamespace(server=SimpleNamespace(config=config), headers={})
        self.assertEqual(_CollabHandler._cookie_security_suffix(fake_handler), "; Secure")

    def test_fallback_executable_requires_matching_checksum(self) -> None:
        exe_path = self.path / "pr.exe"
        data = b"test executable"
        exe_path.write_bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        exe_path.with_name("pr.exe.sha256").write_text(f"{digest}  pr.exe\n", encoding="utf-8")
        self.assertTrue(_checksum_matches(exe_path))


if __name__ == "__main__":
    unittest.main()
