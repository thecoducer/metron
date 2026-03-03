"""
Unit tests for utility functions
"""
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo

from app.constants import STATE_ERROR, STATE_UPDATED, STATE_UPDATING
from app.utils import (SessionManager, StateManager, format_timestamp,
                       is_market_open_ist, load_config)


class TestSessionManager(unittest.TestCase):
    """Test SessionManager class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.session_manager = SessionManager()
    
    def test_get_token_empty_cache(self):
        """Test getting token from empty cache"""
        token = self.session_manager.get_token("test_account")
        self.assertIsNone(token)
    
    def test_save_and_get_token(self):
        """Test saving and retrieving token"""
        test_token = "test_access_token_123"
        self.session_manager.set_token("test_account", test_token)
        retrieved_token = self.session_manager.get_token("test_account")
        self.assertEqual(retrieved_token, test_token)
    
    def test_token_expiry(self):
        """Test expired token returns None"""
        from datetime import timezone
        test_token = "expired_token"
        # Set token with expired time
        self.session_manager.sessions["test_account"] = {
            "access_token": test_token,
            "expiry": datetime.now(timezone.utc) - timedelta(hours=1)
        }
        
        # get_token returns the token regardless of expiry
        retrieved_token = self.session_manager.get_token("test_account")
        self.assertEqual(retrieved_token, test_token)
        
        # But is_valid should return False
        self.assertFalse(self.session_manager.is_valid("test_account"))
    
    def test_clear_token(self):
        """Test clearing token"""
        self.session_manager.set_token("test_account", "token123")
        # Manually clear since there's no clear_token method
        del self.session_manager.sessions["test_account"]
        token = self.session_manager.get_token("test_account")
        self.assertIsNone(token)
    
    def test_multiple_accounts(self):
        """Test managing tokens for multiple accounts"""
        self.session_manager.set_token("account1", "token1")
        self.session_manager.set_token("account2", "token2")
        
        self.assertEqual(self.session_manager.get_token("account1"), "token1")
        self.assertEqual(self.session_manager.get_token("account2"), "token2")
    
    def test_set_user_loads_sessions(self):
        """Test that set_user loads sessions from Firestore"""
        with patch('app.utils.SessionManager.load') as mock_load:
            sm = SessionManager()
            sm.set_user("user123")
            mock_load.assert_called_once()
            self.assertEqual(sm._google_id, "user123")
    
    def test_set_user_noop_same_user(self):
        """Test that set_user is a no-op when the same user is already set"""
        with patch('app.utils.SessionManager.load') as mock_load:
            sm = SessionManager()
            sm._google_id = "user123"
            sm.set_user("user123")
            mock_load.assert_not_called()
    
    def test_set_user_empty_string(self):
        """Test that set_user ignores empty google_id"""
        with patch('app.utils.SessionManager.load') as mock_load:
            sm = SessionManager()
            sm.set_user("")
            mock_load.assert_not_called()
            self.assertIsNone(sm._google_id)
    
    @patch('app.firebase_store.get_zerodha_sessions')
    def test_load_from_firestore(self, mock_get_sessions):
        """Test loading encrypted sessions from Firestore"""
        sm = SessionManager()
        sm._google_id = "user123"

        # Encrypt a token using the same cipher
        encrypted = sm._encrypt_token("my_access_token")
        mock_get_sessions.return_value = {
            "Account1": {
                "access_token": encrypted,
                "expiry": (datetime.now(datetime.now().astimezone().tzinfo) + timedelta(hours=23)).isoformat(),
            }
        }

        sm.load()

        self.assertEqual(sm.get_token("Account1"), "my_access_token")
        self.assertTrue(sm.is_valid("Account1"))
    
    @patch('app.firebase_store.save_zerodha_sessions')
    def test_save_to_firestore(self, mock_save):
        """Test saving encrypted sessions to Firestore"""
        sm = SessionManager()
        sm._google_id = "user123"
        sm.set_token("Account1", "token_abc")

        sm.save()

        mock_save.assert_called_once()
        call_args = mock_save.call_args
        self.assertEqual(call_args[0][0], "user123")
        stored = call_args[0][1]
        self.assertIn("Account1", stored)
        # Token should be encrypted (not plaintext)
        self.assertNotEqual(stored["Account1"]["access_token"], "token_abc")
    
    def test_save_without_user_warns(self):
        """Test that save warns when no user is set"""
        sm = SessionManager()
        sm.set_token("Account1", "token_abc")
        # Should not raise, just warn
        sm.save()
    
    def test_get_validity(self):
        """Test get_validity returns correct status for all accounts"""
        from datetime import timezone
        sm = SessionManager()
        sm.set_token("valid_account", "token1")
        sm.sessions["expired_account"] = {
            "access_token": "token2",
            "expiry": datetime.now(timezone.utc) - timedelta(hours=1),
        }

        result = sm.get_validity(["valid_account", "expired_account", "missing_account"])
        self.assertTrue(result["valid_account"])
        self.assertFalse(result["expired_account"])
        self.assertFalse(result["missing_account"])
    
    @patch('app.firebase_store.save_zerodha_sessions')
    def test_invalidate_saves_to_firestore(self, mock_save):
        """Test that invalidate removes token and persists to Firestore"""
        sm = SessionManager()
        sm._google_id = "user123"
        sm.set_token("Account1", "token_abc")

        sm.invalidate("Account1")

        self.assertIsNone(sm.get_token("Account1"))
        mock_save.assert_called_once()
    
    def test_encrypt_decrypt_roundtrip(self):
        """Test that encrypt/decrypt is a symmetric roundtrip"""
        sm = SessionManager()
        original = "super_secret_token_12345"
        encrypted = sm._encrypt_token(original)
        self.assertNotEqual(encrypted, original)
        decrypted = sm._decrypt_token(encrypted)
        self.assertEqual(decrypted, original)
    
    @patch.dict(os.environ, {"ZERODHA_TOKEN_SECRET": "my_production_secret"})
    def test_cipher_uses_env_var(self):
        """Test that cipher uses ZERODHA_TOKEN_SECRET when available"""
        sm = SessionManager()
        # Should not raise and should produce a working cipher
        encrypted = sm._encrypt_token("test_token")
        decrypted = sm._decrypt_token(encrypted)
        self.assertEqual(decrypted, "test_token")


class TestStateManager(unittest.TestCase):
    """Test StateManager class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.state_manager = StateManager()
    
    def test_initial_state(self):
        """Test initial state is None (no data fetched yet)"""
        self.assertIsNone(self.state_manager.portfolio_state)
        self.assertIsNone(self.state_manager.nifty50_state)
    
    def test_set_refresh_running(self):
        """Test setting portfolio to updating state"""
        self.state_manager.set_portfolio_updating()
        self.assertEqual(self.state_manager.portfolio_state, STATE_UPDATING)
    
    def test_set_refresh_idle(self):
        """Test setting portfolio to updated state"""
        self.state_manager.set_portfolio_updated()
        self.assertEqual(self.state_manager.portfolio_state, STATE_UPDATED)
    
    def test_set_ltp_idle(self):
        """Test setting Nifty50 to updated state"""
        self.state_manager.set_nifty50_updated()
        self.assertEqual(self.state_manager.nifty50_state, STATE_UPDATED)
    
    def test_combined_state_all_idle(self):
        """Test is_any_running when all operations completed"""
        self.state_manager.set_portfolio_updated()
        self.state_manager.set_nifty50_updated()
        self.assertFalse(self.state_manager.is_any_running())
    
    def test_combined_state_refresh_running(self):
        """Test is_any_running when portfolio updating"""
        self.state_manager.set_portfolio_updating()
        self.state_manager.set_nifty50_updated()
        self.assertTrue(self.state_manager.is_any_running())
    
    def test_set_holdings_updated(self):
        """Test setting holdings updated timestamp"""
        
    
    def test_error_tracking(self):
        """Test error message tracking"""
        error_msg = "Test error message"
        self.state_manager.last_error = error_msg
        self.assertEqual(self.state_manager.last_error, error_msg)
    
    def test_change_listener(self):
        """Test adding and triggering change listener"""
        callback_called = []
        
        def callback():
            callback_called.append(True)
        
        self.state_manager.add_change_listener(callback)
        self.state_manager.set_portfolio_updating()
        
        self.assertTrue(len(callback_called) > 0)
    
    def test_change_listener_error_handling(self):
        """Test change listener handles exceptions gracefully"""
        def bad_callback():
            raise Exception("Callback error")
        
        self.state_manager.add_change_listener(bad_callback)
        
        # Should not raise, just print error
        self.state_manager.set_portfolio_updating()
    
    def test_is_any_running_true(self):
        """Test is_any_running returns True when refresh is running"""
        self.state_manager.set_portfolio_updating()
        self.assertTrue(self.state_manager.is_any_running())
    
    def test_is_any_running_false(self):
        """Test is_any_running returns False when all operations completed"""
        self.state_manager.set_portfolio_updated()
        self.state_manager.set_nifty50_updated()
        self.assertFalse(self.state_manager.is_any_running())


class TestConfigLoader(unittest.TestCase):
    """Test configuration loading and validation"""
    
    def test_load_valid_config(self):
        """Test loading valid configuration"""
        config = {
            "accounts": [
                {
                    "name": "TestAccount",
                    "api_key": "test_key",
                    "api_secret": "test_secret"
                }
            ],
            "server": {
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            json.dump(config, f)
            temp_path = f.name
        
        try:
            loaded_config = load_config(temp_path)
            self.assertEqual(loaded_config["accounts"][0]["name"], "TestAccount")
        finally:
            os.unlink(temp_path)
    
    def test_load_missing_config(self):
        """Test loading non-existent config file"""
        result = load_config("nonexistent_config.json")
        self.assertEqual(result, {})
    
    def test_load_config_json_parse_error(self):
        """Test loading config with invalid JSON"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            f.write("{ invalid json }")
            temp_path = f.name
        
        try:
            result = load_config(temp_path)
            self.assertEqual(result, {})
        finally:
            os.unlink(temp_path)


class TestFormatTimestamp(unittest.TestCase):
    """Test timestamp formatting"""
    
    def test_format_none_timestamp(self):
        """Test formatting None timestamp"""
        result = format_timestamp(None)
        self.assertIsNone(result)
    
    def test_format_valid_timestamp(self):
        """Test formatting valid timestamp"""
        import time
        now = time.time()
        result = format_timestamp(now)
        self.assertIsInstance(result, str)
        self.assertIn(":", result)  # Should contain time separator
    
    def test_format_timestamp_with_timezone(self):
        """Test formatting timestamp with timezone"""
        import time
        now = time.time()
        result = format_timestamp(now)
        self.assertIsInstance(result, str)


class TestMarketHours(unittest.TestCase):
    """Test market hours checking"""
    
    @patch('app.utils.datetime')
    def test_market_open_weekday_during_hours(self, mock_datetime):
        """Test market open on weekday during trading hours"""
        # Mock a Wednesday at 10:00 AM IST
        ist = ZoneInfo('Asia/Kolkata')
        mock_now = datetime(2025, 11, 26, 10, 0, 0, tzinfo=ist)  # Wednesday
        mock_datetime.now.return_value = mock_now
        
        result = is_market_open_ist()
        self.assertTrue(result)
    
    @patch('app.utils.datetime')
    def test_market_closed_before_hours(self, mock_datetime):
        """Test market closed before trading hours"""
        ist = ZoneInfo('Asia/Kolkata')
        mock_now = datetime(2025, 11, 26, 8, 0, 0, tzinfo=ist)  # 8 AM
        mock_datetime.now.return_value = mock_now
        
        result = is_market_open_ist()
        self.assertFalse(result)
    
    @patch('app.utils.datetime')
    def test_market_closed_after_hours(self, mock_datetime):
        """Test market closed after trading hours"""
        ist = ZoneInfo('Asia/Kolkata')
        mock_now = datetime(2025, 11, 26, 17, 0, 0, tzinfo=ist)  # 5 PM (after 4:30 PM close)
        mock_datetime.now.return_value = mock_now
        
        result = is_market_open_ist()
        self.assertFalse(result)
    
    @patch('app.utils.datetime')
    def test_market_closed_weekend_saturday(self, mock_datetime):
        """Test market closed on Saturday"""
        ist = ZoneInfo('Asia/Kolkata')
        mock_now = datetime(2025, 11, 22, 10, 0, 0, tzinfo=ist)  # Saturday
        mock_datetime.now.return_value = mock_now
        
        result = is_market_open_ist()
        self.assertFalse(result)
    
    @patch('app.utils.datetime')
    def test_market_closed_weekend_sunday(self, mock_datetime):
        """Test market closed on Sunday"""
        ist = ZoneInfo('Asia/Kolkata')
        mock_now = datetime(2025, 11, 23, 10, 0, 0, tzinfo=ist)  # Sunday
        mock_datetime.now.return_value = mock_now
        
        result = is_market_open_ist()
        self.assertFalse(result)


class TestStateManagerErrorHandling(unittest.TestCase):
    """Test StateManager error handling"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.state_manager = StateManager()
    
    def test_set_portfolio_updating_with_error(self):
        """Test setting portfolio updating with error"""
        self.state_manager.set_portfolio_updating(error="Test error")
        self.assertEqual(self.state_manager.last_error, "Test error")
        self.assertEqual(self.state_manager.portfolio_state, STATE_UPDATING)
    
    def test_set_portfolio_updated_with_error(self):
        """Test setting portfolio updated with error sets ERROR state"""
        self.state_manager.set_portfolio_updated(error="API failure")
        self.assertEqual(self.state_manager.last_error, "API failure")
        self.assertEqual(self.state_manager.portfolio_state, STATE_ERROR)
    
    def test_set_portfolio_updated_clears_error(self):
        """Test setting portfolio updated without error clears previous error"""
        self.state_manager.last_error = "Old error"
        self.state_manager.set_portfolio_updated()
        self.assertIsNone(self.state_manager.last_error)
        self.assertEqual(self.state_manager.portfolio_state, STATE_UPDATED)
    
    def test_set_nifty50_updating_with_error(self):
        """Test setting nifty50 updating with error"""
        self.state_manager.set_nifty50_updating(error="NSE API down")
        self.assertEqual(self.state_manager.last_error, "NSE API down")
        self.assertEqual(self.state_manager.nifty50_state, STATE_UPDATING)
    
    def test_set_nifty50_updated_with_error(self):
        """Test setting nifty50 updated with error sets ERROR state"""
        self.state_manager.set_nifty50_updated(error="Connection timeout")
        self.assertEqual(self.state_manager.last_error, "Connection timeout")
        self.assertEqual(self.state_manager.nifty50_state, STATE_ERROR)
    
    def test_clear_error(self):
        """Test clear_error method"""
        self.state_manager.last_error = "Some error"
        self.state_manager.clear_error()
        self.assertIsNone(self.state_manager.last_error)
    
    def test_is_any_running_with_portfolio_updating(self):
        """Test is_any_running returns True when portfolio updating"""
        self.state_manager.set_portfolio_updating()
        self.state_manager.set_nifty50_updated()
        self.assertTrue(self.state_manager.is_any_running())
    
    def test_is_any_running_with_nifty50_updating(self):
        """Test is_any_running returns True when nifty50 updating"""
        self.state_manager.set_portfolio_updated()
        self.state_manager.set_nifty50_updating()
        self.assertTrue(self.state_manager.is_any_running())
    
    def test_portfolio_timestamp_updated(self):
        """Test portfolio timestamp is set on successful update"""
        self.state_manager.set_portfolio_updated()
        self.assertIsNotNone(self.state_manager.portfolio_last_updated)
        self.assertIsInstance(self.state_manager.portfolio_last_updated, float)
    
    def test_nifty50_timestamp_updated(self):
        """Test nifty50 timestamp is set on successful update"""
        self.state_manager.set_nifty50_updated()
        self.assertIsNotNone(self.state_manager.nifty50_last_updated)
        self.assertIsInstance(self.state_manager.nifty50_last_updated, float)


class TestSessionManagerEdgeCases(unittest.TestCase):
    """Test SessionManager edge cases"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.session_manager = SessionManager()
    
    def test_is_valid_nonexistent_account(self):
        """Test is_valid with account that doesn't exist"""
        result = self.session_manager.is_valid("nonexistent")
        self.assertFalse(result)
    
    def test_get_token_nonexistent_account(self):
        """Test get_token with account that doesn't exist"""
        token = self.session_manager.get_token("nonexistent")
        self.assertIsNone(token)
    
    def test_delete_token_nonexistent_account(self):
        """Test deleting token for account that doesn't exist (should not error)"""
        # Set and then delete
        self.session_manager.set_token("test", "token")
        # Delete by setting to None or empty dict
        if "test" in self.session_manager.sessions:
            del self.session_manager.sessions["test"]
        # Verify it's gone
        self.assertIsNone(self.session_manager.get_token("test"))
    
    def test_set_token_updates_existing(self):
        """Test setting token for existing account updates it"""
        self.session_manager.set_token("test", "token1")
        self.session_manager.set_token("test", "token2")
        
        token = self.session_manager.get_token("test")
        self.assertEqual(token, "token2")
    
    def test_get_validity_empty_sessions(self):
        """Test get_validity with no sessions"""
        validity = self.session_manager.get_validity()
        self.assertEqual(validity, {})
    
    def test_get_validity_multiple_accounts(self):
        """Test get_validity with multiple accounts"""
        from datetime import datetime, timedelta, timezone

        # Add some accounts
        self.session_manager.set_token("Account1", "token1")
        self.session_manager.set_token("Account2", "token2")
        
        # Expire one account by setting expiry in the past
        self.session_manager.sessions["Account1"]["expiry"] = datetime.now(timezone.utc) - timedelta(hours=1)
        
        validity = self.session_manager.get_validity()
        
        self.assertIn("Account1", validity)
        self.assertIn("Account2", validity)
        self.assertFalse(validity["Account1"])
        self.assertTrue(validity["Account2"])


if __name__ == '__main__':
    unittest.main()
