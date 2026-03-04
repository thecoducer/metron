"""
Unit tests for utility functions (multi-tenant SessionManager, StateManager, etc.)
"""
import json
import os
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo

from app.constants import STATE_ERROR, STATE_UPDATED, STATE_UPDATING
from app.utils import (SessionManager, StateManager, encrypt_credential,
                       decrypt_credential, format_timestamp,
                       is_market_open_ist, load_config)

# Default google_id used throughout tests
_GID = "test_google_id_123"


class TestCredentialEncryption(unittest.TestCase):
    """Test per-user encrypt/decrypt credential helpers."""

    def test_round_trip(self):
        """Encrypting then decrypting returns the original value."""
        original = "my_super_secret_api_key"
        encrypted = encrypt_credential(original, _GID)
        self.assertNotEqual(encrypted, original)
        self.assertEqual(decrypt_credential(encrypted, _GID), original)

    def test_decrypt_plaintext_raises(self):
        """Decrypting a plaintext string raises InvalidToken (no fallback)."""
        from cryptography.fernet import InvalidToken
        with self.assertRaises(InvalidToken):
            decrypt_credential("not_encrypted_at_all", _GID)

    def test_different_values_produce_different_ciphertext(self):
        """Two different plaintexts must not produce the same ciphertext."""
        a = encrypt_credential("key_aaa", _GID)
        b = encrypt_credential("key_bbb", _GID)
        self.assertNotEqual(a, b)

    def test_empty_string_round_trip(self):
        """Empty string should survive the round trip."""
        encrypted = encrypt_credential("", _GID)
        self.assertEqual(decrypt_credential(encrypted, _GID), "")

    def test_per_user_isolation(self):
        """Data encrypted for user A cannot be decrypted by user B."""
        from cryptography.fernet import InvalidToken
        encrypted = encrypt_credential("secret", "userA")
        # Same user can decrypt
        self.assertEqual(decrypt_credential(encrypted, "userA"), "secret")
        # Different user cannot
        with self.assertRaises(InvalidToken):
            decrypt_credential(encrypted, "userB")


class TestSessionManager(unittest.TestCase):
    """Test multi-tenant SessionManager class."""

    def setUp(self):
        self.sm = SessionManager()

    def test_get_token_empty_cache(self):
        """Token for unknown user/account returns None."""
        self.assertIsNone(self.sm.get_token(_GID, "test_account"))

    def test_set_and_get_token(self):
        """Set and retrieve a token for a specific user/account."""
        self.sm.set_token(_GID, "test_account", "tok_123")
        self.assertEqual(self.sm.get_token(_GID, "test_account"), "tok_123")

    def test_token_expiry(self):
        """Expired token: get_token still returns it but is_valid returns False."""
        self.sm.set_token(_GID, "test_account", "expired_tok", hours=0, minutes=0)
        # Force expiry
        sessions = self.sm._sessions_for(_GID)
        sessions["test_account"]["expiry"] = datetime.now(timezone.utc) - timedelta(hours=1)

        self.assertEqual(self.sm.get_token(_GID, "test_account"), "expired_tok")
        self.assertFalse(self.sm.is_valid(_GID, "test_account"))

    def test_invalidate_removes_token(self):
        """invalidate removes the session and persists via save."""
        with patch('app.firebase_store.save_zerodha_sessions'):
            self.sm.set_token(_GID, "Acc1", "tok")
            self.sm.invalidate(_GID, "Acc1")
            self.assertIsNone(self.sm.get_token(_GID, "Acc1"))

    def test_multiple_accounts_same_user(self):
        """Multiple accounts for the same user are isolated."""
        self.sm.set_token(_GID, "acc1", "tok1")
        self.sm.set_token(_GID, "acc2", "tok2")
        self.assertEqual(self.sm.get_token(_GID, "acc1"), "tok1")
        self.assertEqual(self.sm.get_token(_GID, "acc2"), "tok2")

    def test_user_isolation(self):
        """Tokens for different users must not leak."""
        self.sm.set_token("userA", "acc1", "tokA")
        self.sm.set_token("userB", "acc1", "tokB")
        self.assertEqual(self.sm.get_token("userA", "acc1"), "tokA")
        self.assertEqual(self.sm.get_token("userB", "acc1"), "tokB")

    def test_set_token_updates_existing(self):
        """Setting token again overwrites the old one."""
        self.sm.set_token(_GID, "acc", "tok1")
        self.sm.set_token(_GID, "acc", "tok2")
        self.assertEqual(self.sm.get_token(_GID, "acc"), "tok2")

    @patch('app.firebase_store.get_zerodha_sessions')
    def test_load_user_from_firestore(self, mock_get):
        """load_user populates in-memory sessions from Firestore."""
        encrypted = self.sm._encrypt("my_token", _GID)
        future = (datetime.now(timezone.utc) + timedelta(hours=23)).isoformat()
        mock_get.return_value = {
            "Account1": {"access_token": encrypted, "expiry": future}
        }

        self.sm.load_user(_GID)

        self.assertEqual(self.sm.get_token(_GID, "Account1"), "my_token")
        self.assertTrue(self.sm.is_valid(_GID, "Account1"))

    @patch('app.firebase_store.save_zerodha_sessions')
    def test_save_to_firestore(self, mock_save):
        """save persists encrypted tokens to Firestore."""
        self.sm.set_token(_GID, "Account1", "token_abc")
        self.sm.save(_GID)

        mock_save.assert_called_once()
        args = mock_save.call_args[0]
        self.assertEqual(args[0], _GID)
        # Token should be encrypted
        self.assertNotEqual(args[1]["Account1"]["access_token"], "token_abc")

    def test_save_without_google_id_warns(self):
        """save('') should not raise, just warn."""
        self.sm.set_token(_GID, "Acc1", "tok")
        self.sm.save("")  # no crash

    def test_get_validity(self):
        """get_validity returns correct status for all accounts."""
        self.sm.set_token(_GID, "valid_acc", "tok1")
        # Expire one
        sessions = self.sm._sessions_for(_GID)
        sessions["expired_acc"] = {
            "access_token": "tok2",
            "expiry": datetime.now(timezone.utc) - timedelta(hours=1),
        }

        result = self.sm.get_validity(_GID, ["valid_acc", "expired_acc", "missing_acc"])
        self.assertTrue(result["valid_acc"])
        self.assertFalse(result["expired_acc"])
        self.assertFalse(result["missing_acc"])

    def test_get_validity_no_accounts_list(self):
        """get_validity without explicit accounts uses stored sessions."""
        self.sm.set_token(_GID, "acc1", "tok")
        result = self.sm.get_validity(_GID)
        self.assertIn("acc1", result)

    def test_is_valid_nonexistent(self):
        self.assertFalse(self.sm.is_valid(_GID, "nonexistent"))

    def test_encrypt_decrypt_roundtrip(self):
        original = "super_secret_token_12345"
        encrypted = self.sm._encrypt(original, _GID)
        self.assertNotEqual(encrypted, original)
        decrypted = self.sm._decrypt(encrypted, _GID)
        self.assertEqual(decrypted, original)

    @patch.dict(os.environ, {"ZERODHA_TOKEN_SECRET": "my_production_secret"})
    def test_cipher_uses_env_var(self):
        sm = SessionManager()
        encrypted = sm._encrypt("test_token", _GID)
        decrypted = sm._decrypt(encrypted, _GID)
        self.assertEqual(decrypted, "test_token")

    def test_load_user_empty_noop(self):
        """load_user with empty string should not raise."""
        self.sm.load_user("")
        self.sm.load_user(None)


class TestStateManager(unittest.TestCase):
    """Test StateManager with per-user portfolio state."""

    def setUp(self):
        self.sm = StateManager()

    # -- Global state (nifty50, physical_gold, etc.) ----------------------

    def test_initial_global_state(self):
        self.assertIsNone(self.sm.nifty50_state)
        self.assertIsNone(self.sm.physical_gold_state)
        self.assertIsNone(self.sm.fixed_deposits_state)

    def test_set_nifty50_updating(self):
        self.sm.set_nifty50_updating()
        self.assertEqual(self.sm.nifty50_state, STATE_UPDATING)

    def test_set_nifty50_updated(self):
        self.sm.set_nifty50_updated()
        self.assertEqual(self.sm.nifty50_state, STATE_UPDATED)
        self.assertIsNotNone(self.sm.nifty50_last_updated)

    def test_set_nifty50_updated_with_error(self):
        self.sm.set_nifty50_updated(error="timeout")
        self.assertEqual(self.sm.nifty50_state, STATE_ERROR)
        self.assertEqual(self.sm.last_error, "timeout")

    # -- Per-user portfolio state -----------------------------------------

    def test_initial_portfolio_state_per_user(self):
        self.assertIsNone(self.sm.get_portfolio_state(_GID))

    def test_set_portfolio_updating_per_user(self):
        self.sm.set_portfolio_updating(google_id=_GID)
        self.assertEqual(self.sm.get_portfolio_state(_GID), STATE_UPDATING)

    def test_set_portfolio_updated_per_user(self):
        self.sm.set_portfolio_updated(google_id=_GID)
        self.assertEqual(self.sm.get_portfolio_state(_GID), STATE_UPDATED)
        self.assertIsNotNone(self.sm.get_portfolio_last_updated(_GID))

    def test_set_portfolio_updated_with_error_per_user(self):
        self.sm.set_portfolio_updated(google_id=_GID, error="API fail")
        self.assertEqual(self.sm.get_portfolio_state(_GID), STATE_ERROR)
        self.assertEqual(self.sm.get_user_last_error(_GID), "API fail")

    def test_portfolio_user_isolation(self):
        """Portfolio state for userA must not affect userB."""
        self.sm.set_portfolio_updating(google_id="userA")
        self.sm.set_portfolio_updated(google_id="userB")

        self.assertEqual(self.sm.get_portfolio_state("userA"), STATE_UPDATING)
        self.assertEqual(self.sm.get_portfolio_state("userB"), STATE_UPDATED)

    def test_set_portfolio_updated_clears_user_error(self):
        """Successful update clears in-progress user error."""
        self.sm.set_portfolio_updated(google_id=_GID, error="old_err")
        self.sm.set_portfolio_updated(google_id=_GID)
        self.assertIsNone(self.sm.get_user_last_error(_GID))

    # -- is_any_running ---------------------------------------------------

    def test_is_any_running_global_nifty50(self):
        self.sm.set_nifty50_updating()
        self.assertTrue(self.sm.is_any_running())

    def test_is_any_running_per_user_portfolio(self):
        self.sm.set_portfolio_updating(google_id=_GID)
        self.assertTrue(self.sm.is_any_running(google_id=_GID))

    def test_is_any_running_false_all_done(self):
        self.sm.set_nifty50_updated()
        self.sm.set_portfolio_updated(google_id=_GID)
        self.assertFalse(self.sm.is_any_running(google_id=_GID))

    # -- change listeners --------------------------------------------------

    def test_change_listener_called(self):
        called = []

        def cb(**kwargs):
            called.append(kwargs)

        self.sm.add_change_listener(cb)
        self.sm.set_portfolio_updating(google_id=_GID)
        self.assertTrue(len(called) > 0)

    def test_change_listener_receives_google_id(self):
        received = []

        def cb(google_id=None):
            received.append(google_id)

        self.sm.add_change_listener(cb)
        self.sm.set_portfolio_updating(google_id=_GID)
        self.assertEqual(received[-1], _GID)

    def test_change_listener_error_handling(self):
        """Bad listener should not crash state updates."""
        def bad_cb(**kwargs):
            raise RuntimeError("boom")

        self.sm.add_change_listener(bad_cb)
        self.sm.set_portfolio_updating(google_id=_GID)  # should not raise

    # -- clear_error -------------------------------------------------------

    def test_clear_error_global(self):
        self.sm.last_error = "err"
        self.sm.clear_error()
        self.assertIsNone(self.sm.last_error)

    def test_clear_error_per_user(self):
        self.sm.set_portfolio_updated(google_id=_GID, error="user err")
        self.sm.clear_error(google_id=_GID)
        self.assertIsNone(self.sm.get_user_last_error(_GID))

    # -- dynamic attribute access -----------------------------------------

    def test_dynamic_set_physical_gold_updating(self):
        self.sm.set_physical_gold_updating()
        self.assertEqual(self.sm.physical_gold_state, STATE_UPDATING)

    def test_dynamic_set_fixed_deposits_updated(self):
        self.sm.set_fixed_deposits_updated()
        self.assertEqual(self.sm.fixed_deposits_state, STATE_UPDATED)

    def test_dynamic_unknown_attr_raises(self):
        with self.assertRaises(AttributeError):
            _ = self.sm.nonexistent_attribute


class TestConfigLoader(unittest.TestCase):
    """Test configuration loading and validation."""

    def test_load_valid_config(self):
        config = {"accounts": [{"name": "TestAccount"}]}
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            json.dump(config, f)
            temp_path = f.name
        try:
            loaded = load_config(temp_path)
            self.assertEqual(loaded["accounts"][0]["name"], "TestAccount")
        finally:
            os.unlink(temp_path)

    def test_load_missing_config(self):
        self.assertEqual(load_config("nonexistent.json"), {})

    def test_load_invalid_json(self):
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            f.write("{ invalid }")
            temp_path = f.name
        try:
            self.assertEqual(load_config(temp_path), {})
        finally:
            os.unlink(temp_path)


class TestFormatTimestamp(unittest.TestCase):
    """Test timestamp formatting."""

    def test_format_none(self):
        self.assertIsNone(format_timestamp(None))

    def test_format_valid(self):
        import time
        result = format_timestamp(time.time())
        self.assertIsInstance(result, str)
        self.assertIn(":", result)


class TestMarketHours(unittest.TestCase):
    """Test market hours checking."""

    @patch('app.utils.datetime')
    def test_market_open_weekday_during_hours(self, mock_datetime):
        ist = ZoneInfo('Asia/Kolkata')
        mock_now = datetime(2025, 11, 26, 10, 0, 0, tzinfo=ist)
        mock_datetime.now.return_value = mock_now
        self.assertTrue(is_market_open_ist())

    @patch('app.utils.datetime')
    def test_market_closed_before_hours(self, mock_datetime):
        ist = ZoneInfo('Asia/Kolkata')
        mock_now = datetime(2025, 11, 26, 8, 0, 0, tzinfo=ist)
        mock_datetime.now.return_value = mock_now
        self.assertFalse(is_market_open_ist())

    @patch('app.utils.datetime')
    def test_market_closed_after_hours(self, mock_datetime):
        ist = ZoneInfo('Asia/Kolkata')
        mock_now = datetime(2025, 11, 26, 17, 0, 0, tzinfo=ist)
        mock_datetime.now.return_value = mock_now
        self.assertFalse(is_market_open_ist())

    @patch('app.utils.datetime')
    def test_market_closed_weekend(self, mock_datetime):
        ist = ZoneInfo('Asia/Kolkata')
        mock_now = datetime(2025, 11, 22, 10, 0, 0, tzinfo=ist)  # Saturday
        mock_datetime.now.return_value = mock_now
        self.assertFalse(is_market_open_ist())


if __name__ == '__main__':
    unittest.main()
