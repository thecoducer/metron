"""
Unit tests for services.py (service instances and status helpers).
"""
import json
import unittest
from unittest.mock import PropertyMock, patch, MagicMock

from app.services import (_build_status_response,
                          ensure_user_loaded, get_user_accounts,
                          get_authenticated_accounts)


class TestBuildStatusResponse(unittest.TestCase):
    """Test the _build_status_response helper."""

    def test_returns_expected_fields_with_google_id(self):
        """Status response scoped to a specific user."""
        with patch('app.services.state_manager') as mock_state, \
             patch('app.services.session_manager') as mock_session, \
             patch('app.services.format_timestamp') as mock_format, \
             patch('app.services.is_market_open_ist') as mock_market, \
             patch('app.services.get_user_accounts', return_value=[
                 {"name": "Account1", "api_key": "key1"}
             ]):
            mock_state.last_error = None
            mock_state.get_portfolio_state.return_value = 'updated'
            mock_state.get_portfolio_last_updated.return_value = 1234567890.0
            mock_state.get_user_last_error.return_value = None
            mock_state.get_manual_ltp_state.return_value = None
            mock_state.get_manual_ltp_last_updated.return_value = None
            mock_state.nifty50_state = 'updating'
            mock_state.nifty50_last_updated = None
            mock_state.physical_gold_state = None
            mock_state.physical_gold_last_updated = None
            mock_state.fixed_deposits_state = None
            mock_state.fixed_deposits_last_updated = None

            mock_format.side_effect = lambda x: f"formatted_{x}" if x else None
            mock_session.is_valid.return_value = True
            mock_market.return_value = True

            response = _build_status_response("user123")

            self.assertIsNone(response['last_error'])
            self.assertEqual(response['portfolio_state'], 'updated')
            self.assertEqual(response['nifty50_state'], 'updating')
            self.assertEqual(response['portfolio_last_updated'], 'formatted_1234567890.0')
            self.assertIsNone(response['nifty50_last_updated'])
            self.assertTrue(response['market_open'])
            self.assertTrue(response['has_zerodha_accounts'])
            self.assertEqual(response['authenticated_accounts'], ['Account1'])
            self.assertEqual(response['unauthenticated_accounts'], [])
            self.assertEqual(response['session_validity'], {"Account1": True})
            self.assertIn('login_urls', response)

    def test_returns_empty_when_no_google_id(self):
        """Status response without a user should have no accounts."""
        with patch('app.services.state_manager') as mock_state, \
             patch('app.services.session_manager'), \
             patch('app.services.format_timestamp', return_value=None), \
             patch('app.services.is_market_open_ist', return_value=False):
            mock_state.last_error = None
            mock_state.nifty50_state = None
            mock_state.nifty50_last_updated = None
            mock_state.physical_gold_state = None
            mock_state.physical_gold_last_updated = None
            mock_state.fixed_deposits_state = None
            mock_state.fixed_deposits_last_updated = None

            response = _build_status_response()

            self.assertFalse(response['has_zerodha_accounts'])
            self.assertEqual(response['authenticated_accounts'], [])
            self.assertIsNone(response['portfolio_state'])


class TestEnsureUserLoaded(unittest.TestCase):
    """Test ensure_user_loaded idempotency."""

    @patch('app.services._loaded_users', new_callable=set)
    @patch('app.services.session_manager')
    @patch('app.services.run_background_fetch', create=True)
    def test_first_call_loads_sessions(self, mock_fetch, mock_session, mock_loaded):
        with patch('app.services._loaded_users', set()):
            with patch('app.services.session_manager') as mock_sm:
                # Reset module state for clean test
                import app.services as svc
                original = svc._loaded_users.copy()
                svc._loaded_users.clear()
                try:
                    ensure_user_loaded("testuser")
                    mock_sm.load_user.assert_called_once_with("testuser")
                finally:
                    svc._loaded_users = original

    def test_empty_google_id_noop(self):
        """Should not raise or do anything with empty string."""
        ensure_user_loaded("")
        ensure_user_loaded(None)

    def test_force_reloads(self):
        """force=True should reload even if user was previously loaded."""
        import app.services as svc
        original = svc._loaded_users.copy()
        svc._loaded_users.add("forceuser")
        try:
            with patch('app.services.session_manager') as mock_sm:
                ensure_user_loaded("forceuser", force=True)
                mock_sm.load_user.assert_called_once()
        finally:
            svc._loaded_users = original


class TestGetUserAccounts(unittest.TestCase):
    """Test get_user_accounts helper."""

    @patch('app.services.session_manager')
    @patch('app.services.get_zerodha_accounts', create=True)
    def test_returns_accounts_for_user(self, mock_get, mock_sm):
        mock_sm.get_pin.return_value = "123456"
        mock_get.return_value = [{"name": "Acc1"}, {"name": "Acc2"}]
        with patch('app.firebase_store.get_zerodha_accounts', mock_get):
            result = get_user_accounts("user123")
            self.assertEqual(len(result), 2)

    def test_returns_empty_for_no_google_id(self):
        self.assertEqual(get_user_accounts(""), [])
        self.assertEqual(get_user_accounts(None), [])

    @patch('app.services.session_manager')
    def test_returns_empty_when_no_pin(self, mock_sm):
        mock_sm.get_pin.return_value = None
        result = get_user_accounts("user123")
        self.assertEqual(result, [])

    @patch('app.services.session_manager')
    def test_returns_empty_on_exception(self, mock_sm):
        mock_sm.get_pin.return_value = "123456"
        with patch('app.firebase_store.get_zerodha_accounts', side_effect=Exception("db error")):
            result = get_user_accounts("user123")
            self.assertEqual(result, [])


class TestBuildStatusResponseUnauthenticated(unittest.TestCase):
    """Test _build_status_response with unauthenticated accounts (KiteConnect)."""

    @patch('kiteconnect.KiteConnect')
    @patch('app.services.state_manager')
    @patch('app.services.session_manager')
    @patch('app.services.format_timestamp', return_value=None)
    @patch('app.services.is_market_open_ist', return_value=True)
    @patch('app.services.get_user_accounts')
    def test_unauthenticated_shows_login_url(self, mock_accs, mock_mkt,
                                              mock_fmt, mock_sm, mock_state,
                                              mock_kite_cls):
        mock_accs.return_value = [{"name": "Acc1", "api_key": "k1"}]
        mock_sm.is_valid.return_value = False
        mock_kite_cls.return_value.login_url.return_value = "https://kite.zerodha.com/login"
        mock_state.last_error = None
        mock_state.get_portfolio_state.return_value = None
        mock_state.get_portfolio_last_updated.return_value = None
        mock_state.get_user_last_error.return_value = None
        mock_state.get_manual_ltp_state.return_value = None
        mock_state.get_manual_ltp_last_updated.return_value = None
        mock_state.nifty50_state = None
        mock_state.nifty50_last_updated = None
        mock_state.physical_gold_state = None
        mock_state.physical_gold_last_updated = None
        mock_state.fixed_deposits_state = None
        mock_state.fixed_deposits_last_updated = None

        result = _build_status_response("user1")
        self.assertEqual(len(result["unauthenticated_accounts"]), 1)
        self.assertIn("login_url", result["unauthenticated_accounts"][0])


class TestGetAuthenticatedAccounts(unittest.TestCase):
    """Test get_authenticated_accounts helper."""

    @patch('app.services.session_manager')
    @patch('app.services.get_user_accounts')
    def test_filters_to_valid_sessions(self, mock_accounts, mock_session):
        mock_accounts.return_value = [
            {"name": "Acc1"},
            {"name": "Acc2"},
        ]
        mock_session.is_valid.side_effect = lambda gid, name: name == "Acc1"

        result = get_authenticated_accounts("user123")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Acc1")


class TestEnsureUserLoadedAlreadyLoaded(unittest.TestCase):
    """Test ensure_user_loaded skips when user already loaded and force=False."""

    def test_already_loaded_skips(self):
        import app.services as svc
        original = svc._loaded_users.copy()
        svc._loaded_users.add("existinguser")
        try:
            with patch('app.services.session_manager') as mock_sm:
                ensure_user_loaded("existinguser", force=False)
                mock_sm.load_user.assert_not_called()
        finally:
            svc._loaded_users = original


class TestBuildStatusKiteConnectException(unittest.TestCase):
    """Test _build_status_response when KiteConnect() raises an exception."""

    @patch('app.services.state_manager')
    @patch('app.services.session_manager')
    @patch('app.services.format_timestamp', return_value=None)
    @patch('app.services.is_market_open_ist', return_value=True)
    @patch('app.services.get_user_accounts')
    def test_kiteconnect_exception_gives_none_url(self, mock_accs, mock_mkt,
                                                   mock_fmt, mock_sm, mock_state):
        mock_accs.return_value = [{"name": "Acc1", "api_key": "k1"}]
        mock_sm.is_valid.return_value = False
        mock_state.last_error = None
        mock_state.get_portfolio_state.return_value = None
        mock_state.get_portfolio_last_updated.return_value = None
        mock_state.get_user_last_error.return_value = None
        mock_state.get_manual_ltp_state.return_value = None
        mock_state.get_manual_ltp_last_updated.return_value = None
        mock_state.nifty50_state = None
        mock_state.nifty50_last_updated = None
        mock_state.physical_gold_state = None
        mock_state.physical_gold_last_updated = None
        mock_state.fixed_deposits_state = None
        mock_state.fixed_deposits_last_updated = None

        with patch('kiteconnect.KiteConnect', side_effect=Exception("import fail")):
            result = _build_status_response("user1")
        self.assertEqual(len(result["unauthenticated_accounts"]), 1)
        self.assertIsNone(result["unauthenticated_accounts"][0]["login_url"])
        self.assertIsNone(result["login_urls"]["Acc1"])


if __name__ == '__main__':
    unittest.main()
