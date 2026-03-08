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
                       decrypt_credential, encrypt_google_credentials,
                       decrypt_google_credentials, create_pin_check,
                       verify_pin, format_timestamp,
                       is_market_open_ist, PinRateLimiter,
                       _get_base_secret, _get_flask_secret)

# Default PIN used throughout tests
_GID = "test_google_id_123"
_PIN = "123456"


class TestCredentialEncryption(unittest.TestCase):
    """Test per-user + PIN encrypt/decrypt credential helpers."""

    def test_round_trip(self):
        """Encrypting then decrypting returns the original value."""
        original = "my_super_secret_api_key"
        encrypted = encrypt_credential(original, _PIN)
        self.assertNotEqual(encrypted, original)
        self.assertEqual(decrypt_credential(encrypted, _PIN), original)

    def test_decrypt_plaintext_raises(self):
        """Decrypting a plaintext string raises InvalidToken (no fallback)."""
        from cryptography.fernet import InvalidToken
        with self.assertRaises(InvalidToken):
            decrypt_credential("not_encrypted_at_all", _PIN)

    def test_different_values_produce_different_ciphertext(self):
        """Two different plaintexts must not produce the same ciphertext."""
        a = encrypt_credential("key_aaa", _PIN)
        b = encrypt_credential("key_bbb", _PIN)
        self.assertNotEqual(a, b)

    def test_empty_string_round_trip(self):
        """Empty string should survive the round trip."""
        encrypted = encrypt_credential("", _PIN)
        self.assertEqual(decrypt_credential(encrypted, _PIN), "")

    def test_per_pin_isolation(self):
        """Data encrypted with PIN A cannot be decrypted with PIN B."""
        from cryptography.fernet import InvalidToken
        encrypted = encrypt_credential("secret", "111111")
        self.assertEqual(decrypt_credential(encrypted, "111111"), "secret")
        with self.assertRaises(InvalidToken):
            decrypt_credential(encrypted, "999999")


class TestPinCheck(unittest.TestCase):
    """Test PIN verification via encrypted sentinel token."""

    def test_create_and_verify_pin(self):
        """create_pin_check + verify_pin round trip succeeds with correct PIN."""
        token = create_pin_check(_PIN)
        self.assertTrue(verify_pin(token, _PIN))

    def test_verify_pin_wrong_pin(self):
        """verify_pin returns False for wrong PIN."""
        token = create_pin_check("111111")
        self.assertFalse(verify_pin(token, "999999"))


class TestGoogleCredentialsEncryption(unittest.TestCase):
    """Test server-side Google credentials encryption."""

    def test_round_trip(self):
        creds = {"token": "abc", "refresh_token": "xyz", "client_id": "id"}
        encrypted = encrypt_google_credentials(creds)
        self.assertIsInstance(encrypted, str)
        decrypted = decrypt_google_credentials(encrypted)
        self.assertEqual(decrypted, creds)

    def test_decrypt_invalid_raises(self):
        from cryptography.fernet import InvalidToken
        with self.assertRaises(InvalidToken):
            decrypt_google_credentials("not_valid_data")


class TestSessionManager(unittest.TestCase):
    """Test multi-tenant SessionManager class."""

    def setUp(self):
        self.sm = SessionManager()
        # Most tests need a PIN set for encryption/decryption
        self.sm.set_pin(_GID, _PIN)

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
        self.sm.set_pin("userA", _PIN)
        self.sm.set_pin("userB", _PIN)
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

    def test_encrypt_without_pin_raises(self):
        """_encrypt raises ValueError when no PIN is set for user."""
        sm = SessionManager()
        with self.assertRaises(ValueError):
            sm._encrypt("token", "no_pin_user")

    def test_pin_management(self):
        """set_pin, get_pin, clear_pin work correctly."""
        sm = SessionManager()
        self.assertIsNone(sm.get_pin("user1"))
        sm.set_pin("user1", "654321")
        self.assertEqual(sm.get_pin("user1"), "654321")
        sm.clear_pin("user1")
        self.assertIsNone(sm.get_pin("user1"))

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
        sm.set_pin(_GID, _PIN)
        encrypted = sm._encrypt("test_token", _GID)
        decrypted = sm._decrypt(encrypted, _GID)
        self.assertEqual(decrypted, "test_token")

    def test_load_user_empty_noop(self):
        """load_user with empty string should not raise."""
        self.sm.load_user("")
        self.sm.load_user(None)

    def test_decrypt_without_pin_raises(self):
        """_decrypt raises ValueError when no PIN is set for user."""
        sm = SessionManager()
        with self.assertRaises(ValueError):
            sm._decrypt("encrypted_data", "no_pin_user")

    @patch('app.firebase_store.get_zerodha_sessions')
    def test_load_user_no_pin_skips(self, mock_get):
        """load_user skips when PIN not in memory."""
        sm = SessionManager()
        sm.load_user("user_no_pin")
        mock_get.assert_not_called()

    @patch('app.firebase_store.get_zerodha_sessions', side_effect=Exception("db error"))
    def test_load_user_firestore_exception(self, mock_get):
        """load_user handles Firestore errors gracefully."""
        self.sm.load_user(_GID)
        # Should not raise

    @patch('app.firebase_store.get_zerodha_sessions')
    def test_load_user_bad_expiry_skipped(self, mock_get):
        """load_user skips sessions with invalid expiry dates."""
        mock_get.return_value = {
            "BadAcc": {"access_token": "enc", "expiry": "not-a-date"}
        }
        self.sm.load_user(_GID)
        self.assertIsNone(self.sm.get_token(_GID, "BadAcc"))

    @patch('app.firebase_store.get_zerodha_sessions')
    def test_load_user_decrypt_failure_skipped(self, mock_get):
        """load_user skips sessions that fail to decrypt (wrong PIN)."""
        future = (datetime.now(timezone.utc) + timedelta(hours=23)).isoformat()
        mock_get.return_value = {
            "CorruptAcc": {"access_token": "bad_encrypted_data", "expiry": future}
        }
        self.sm.load_user(_GID)
        self.assertIsNone(self.sm.get_token(_GID, "CorruptAcc"))

    @patch('app.firebase_store.get_zerodha_sessions')
    def test_load_user_naive_expiry_gets_utc(self, mock_get):
        """load_user adds UTC tz to naive expiry timestamps."""
        encrypted = self.sm._encrypt("my_token", _GID)
        # Naive datetime string (no tzinfo)
        future = (datetime.now() + timedelta(hours=23)).strftime("%Y-%m-%dT%H:%M:%S")
        mock_get.return_value = {
            "NaiveAcc": {"access_token": encrypted, "expiry": future}
        }
        self.sm.load_user(_GID)
        self.assertEqual(self.sm.get_token(_GID, "NaiveAcc"), "my_token")

    @patch('app.firebase_store.get_zerodha_sessions')
    def test_load_user_all_invalid_warns(self, mock_get):
        """load_user warns when stored sessions exist but none are valid."""
        mock_get.return_value = {
            "Bad1": {"access_token": "enc", "expiry": "not-a-date"},
            "Bad2": {"access_token": "enc", "expiry": "also-bad"},
        }
        self.sm.load_user(_GID)
        # No sessions loaded
        self.assertIsNone(self.sm.get_token(_GID, "Bad1"))

    def test_save_without_pin_warns(self):
        """save() warns and returns when PIN not in memory."""
        sm = SessionManager()
        sm.set_token("g1", "acc1", "tok")
        sm._user_pins.clear()
        sm.save("g1")  # Should not raise

    @patch('app.firebase_store.save_zerodha_sessions', side_effect=Exception("db error"))
    def test_save_firestore_exception(self, mock_save):
        """save() handles Firestore errors gracefully."""
        self.sm.set_token(_GID, "Acc1", "token_abc")
        self.sm.save(_GID)  # Should not raise


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

    def test_set_updating_with_error(self):
        """_set_updating with error sets last_error."""
        self.sm.set_nifty50_updating(error="timeout")
        self.assertEqual(self.sm.nifty50_state, STATE_UPDATING)
        self.assertEqual(self.sm.last_error, "timeout")

    def test_set_updated_clear_global_error(self):
        """_set_updated with clear_global_error=True resets last_error."""
        self.sm.last_error = "old error"
        self.sm._set_updated("nifty50", clear_global_error=True)
        self.assertIsNone(self.sm.last_error)

    def test_is_any_running_no_google_id_global_done(self):
        """is_any_running without google_id returns False when all global done."""
        self.sm.set_nifty50_updated()
        self.assertFalse(self.sm.is_any_running())


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


# ---------------------------------------------------------------------------
# PinRateLimiter tests
# ---------------------------------------------------------------------------

class TestPinRateLimiter(unittest.TestCase):
    """Tests for the escalating PIN rate limiter."""

    def setUp(self):
        self.limiter = PinRateLimiter()

    def test_initial_state_allows_request(self):
        """Fresh user should be allowed through."""
        allowed, retry = self.limiter.check("user1")
        self.assertTrue(allowed)
        self.assertIsNone(retry)

    def test_failures_below_threshold_no_lockout(self):
        """Under 3 failures, no lockout is imposed."""
        for _ in range(2):
            attempts, lockout = self.limiter.record_failure("user1")
            self.assertIsNone(lockout)
        allowed, _ = self.limiter.check("user1")
        self.assertTrue(allowed)

    def test_three_failures_triggers_lockout(self):
        """3rd failure triggers the first lockout tier (15 min)."""
        for _ in range(3):
            attempts, lockout = self.limiter.record_failure("user1")
        self.assertEqual(attempts, 3)
        self.assertEqual(lockout, 15 * 60)

    def test_locked_user_denied(self):
        """Once locked, check() should deny with retry_after."""
        for _ in range(3):
            self.limiter.record_failure("user1")
        allowed, retry = self.limiter.check("user1")
        self.assertFalse(allowed)
        self.assertIsNotNone(retry)
        self.assertGreater(retry, 0)

    def test_lockout_expiry(self):
        """After lockout expires, user should be allowed again."""
        for _ in range(3):
            self.limiter.record_failure("user1")
        # Simulate lockout expiry by manipulating the locked_until time
        self.limiter._state["user1"]["locked_until"] = 0  # already expired
        allowed, retry = self.limiter.check("user1")
        self.assertTrue(allowed)

    def test_six_failures_escalates(self):
        """6th failure triggers second tier (60 min)."""
        for _ in range(6):
            attempts, lockout = self.limiter.record_failure("user1")
        self.assertEqual(attempts, 6)
        self.assertEqual(lockout, 60 * 60)

    def test_nine_failures_max_tier(self):
        """9th failure triggers max tier (4 hours)."""
        for _ in range(9):
            attempts, lockout = self.limiter.record_failure("user1")
        self.assertEqual(attempts, 9)
        self.assertEqual(lockout, 4 * 60 * 60)

    def test_beyond_max_tier_continues_locking(self):
        """Failures beyond 9 keep getting the max lockout at every 3rd."""
        for _ in range(12):
            attempts, lockout = self.limiter.record_failure("user1")
        self.assertEqual(attempts, 12)
        self.assertEqual(lockout, 4 * 60 * 60)

    def test_success_clears_state(self):
        """Successful verification clears all rate-limit state."""
        for _ in range(2):
            self.limiter.record_failure("user1")
        self.limiter.record_success("user1")
        # Should be back to zero
        self.assertEqual(self.limiter.get_attempts("user1"), 0)
        allowed, _ = self.limiter.check("user1")
        self.assertTrue(allowed)

    def test_clear_resets_state(self):
        """clear() (e.g. on PIN reset) wipes user state."""
        for _ in range(3):
            self.limiter.record_failure("user1")
        self.limiter.clear("user1")
        allowed, _ = self.limiter.check("user1")
        self.assertTrue(allowed)
        self.assertEqual(self.limiter.get_attempts("user1"), 0)

    def test_per_user_isolation(self):
        """Rate-limit state for different users is independent."""
        for _ in range(3):
            self.limiter.record_failure("user1")
        # user2 should be unaffected
        allowed, _ = self.limiter.check("user2")
        self.assertTrue(allowed)
        self.assertEqual(self.limiter.get_attempts("user2"), 0)

    def test_thread_safety(self):
        """Concurrent failures should not corrupt state."""
        errors = []

        def hammer():
            try:
                for _ in range(10):
                    self.limiter.record_failure("user_concurrent")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=hammer) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(errors), 0)
        self.assertEqual(self.limiter.get_attempts("user_concurrent"), 40)

    def test_attempts_not_reset_after_lockout_expiry(self):
        """Lockout expiry does not reset the attempt counter (cumulative)."""
        for _ in range(3):
            self.limiter.record_failure("user1")
        # Expire the lockout
        self.limiter._state["user1"]["locked_until"] = 0
        self.limiter.check("user1")
        # Counter stays at 3
        self.assertEqual(self.limiter.get_attempts("user1"), 3)


class TestSecretHelpers(unittest.TestCase):
    """Test _get_base_secret and _get_flask_secret env var paths."""

    @patch.dict(os.environ, {"ZERODHA_TOKEN_SECRET": "prod_secret"})
    def test_base_secret_from_env(self):
        result = _get_base_secret()
        self.assertEqual(result, b"prod_secret")

    @patch.dict(os.environ, {}, clear=True)
    def test_base_secret_fallback(self):
        # When env var is absent, falls back to machine-specific key
        result = _get_base_secret()
        self.assertIsInstance(result, bytes)
        self.assertGreater(len(result), 0)

    @patch.dict(os.environ, {"FLASK_SECRET_KEY": ""})
    def test_flask_secret_not_set(self):
        result = _get_flask_secret()
        self.assertIsInstance(result, bytes)
        self.assertGreater(len(result), 0)

    @patch.dict(os.environ, {"FLASK_SECRET_KEY": "my_flask_key"})
    def test_flask_secret_from_env(self):
        result = _get_flask_secret()
        self.assertEqual(result, b"my_flask_key")


class TestSetPortfolioUpdatingWithError(unittest.TestCase):
    """Cover utils.py line 328: set_portfolio_updating with error parameter."""

    def test_set_portfolio_updating_with_error(self):
        sm = StateManager()
        sm.set_portfolio_updating("user1", error="fetch failed")
        us = sm._get_user_state("user1")
        self.assertEqual(us["portfolio_state"], STATE_UPDATING)
        self.assertEqual(us["last_error"], "fetch failed")


if __name__ == '__main__':
    unittest.main()
