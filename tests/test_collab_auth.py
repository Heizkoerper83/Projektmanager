from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pmtool.collab_accounts import (
    activate_account,
    authenticate,
    create_account,
    ensure_api_keys,
    list_accounts,
    rotate_api_key,
)


class CollabAuthTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.accounts_path = Path(self.temp_dir.name) / "accounts.json"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_create_account_returns_activation_key_and_login_requires_activation(self) -> None:
        account = create_account("alice@example.com", password="secret123", role="reader", path=self.accounts_path)
        activation_key = account["activation_api_key"]

        self.assertTrue(activation_key.startswith("act_"))
        self.assertIsNone(authenticate(email="alice@example.com", password="secret123", path=self.accounts_path))

    def test_new_account_is_pending(self) -> None:
        create_account("alice@example.com", password="secret123", role="reader", path=self.accounts_path)

        rows = list_accounts(self.accounts_path)
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["enabled"])
        self.assertEqual(rows[0]["status"], "pending")

    def test_activation_with_wrong_key_fails(self) -> None:
        create_account("alice@example.com", password="secret123", role="reader", path=self.accounts_path)

        with self.assertRaises(ValueError):
            activate_account("alice@example.com", "act_wrong", path=self.accounts_path)

    def test_activation_with_correct_key_enables_login(self) -> None:
        account = create_account("alice@example.com", password="secret123", role="reader", path=self.accounts_path)
        activation_key = account["activation_api_key"]

        result = activate_account("alice@example.com", activation_key, path=self.accounts_path)
        self.assertTrue(result["enabled"])

        principal = authenticate(email="alice@example.com", password="secret123", path=self.accounts_path)
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

    def test_rotate_api_key_still_works(self) -> None:
        create_account("alice@example.com", password="secret123", role="editor", path=self.accounts_path)

        rotated = rotate_api_key("alice@example.com", path=self.accounts_path)
        new_key = rotated["api_key"]

        self.assertTrue(new_key.startswith("pmk_"))


if __name__ == "__main__":
    unittest.main()