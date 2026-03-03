"""
Unit tests for services.py (service instances and status helpers).
"""
import json
import unittest
from unittest.mock import PropertyMock, patch, MagicMock

from app.services import (_build_status_response, broadcast_state_change,
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


class TestBroadcastStateChange(unittest.TestCase):
    """Test broadcast_state_change sends to correct SSE clients."""

    def test_user_specific_broadcast(self):
        """When google_id is given, broadcast only to that user."""
        with patch('app.services.sse_manager') as mock_sse, \
             patch('app.services.state_manager') as mock_state, \
             patch('app.services.session_manager') as mock_session, \
             patch('app.services.format_timestamp', return_value=None), \
             patch('app.services.is_market_open_ist', return_value=True), \
             patch('app.services.get_user_accounts', return_value=[]):
            mock_state.last_error = None
            mock_state.get_portfolio_state.return_value = 'updated'
            mock_state.get_portfolio_last_updated.return_value = None
            mock_state.get_user_last_error.return_value = None
            mock_state.nifty50_state = 'updated'
            mock_state.nifty50_last_updated = None
            mock_state.physical_gold_state = None
            mock_state.physical_gold_last_updated = None
            mock_state.fixed_deposits_state = None
            mock_state.fixed_deposits_last_updated = None

            broadcast_state_change(google_id="user123")

            mock_sse.broadcast_to_user.assert_called_once()
            call_args = mock_sse.broadcast_to_user.call_args
            self.assertEqual(call_args[0][0], "user123")
            message = json.loads(call_args[0][1])
            self.assertEqual(message['portfolio_state'], 'updated')

    def test_global_broadcast_sends_to_all_connected(self):
        """When no google_id, broadcast to every connected user."""
        with patch('app.services.sse_manager') as mock_sse, \
             patch('app.services.state_manager') as mock_state, \
             patch('app.services.session_manager') as mock_session, \
             patch('app.services.format_timestamp', return_value=None), \
             patch('app.services.is_market_open_ist', return_value=True), \
             patch('app.services.get_user_accounts', return_value=[]):
            mock_state.last_error = None
            mock_state.get_portfolio_state.return_value = None
            mock_state.get_portfolio_last_updated.return_value = None
            mock_state.get_user_last_error.return_value = None
            mock_state.nifty50_state = 'updated'
            mock_state.nifty50_last_updated = None
            mock_state.physical_gold_state = None
            mock_state.physical_gold_last_updated = None
            mock_state.fixed_deposits_state = None
            mock_state.fixed_deposits_last_updated = None

            mock_sse.connected_user_ids.return_value = {"userA", "userB"}

            broadcast_state_change()

            # Should call broadcast_to_user for each connected user
            self.assertEqual(mock_sse.broadcast_to_user.call_count, 2)


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


class TestGetUserAccounts(unittest.TestCase):
    """Test get_user_accounts helper."""

    @patch('app.services.get_zerodha_accounts', create=True)
    def test_returns_accounts_for_user(self, mock_get):
        mock_get.return_value = [{"name": "Acc1"}, {"name": "Acc2"}]
        with patch('app.firebase_store.get_zerodha_accounts', mock_get):
            result = get_user_accounts("user123")
            self.assertEqual(len(result), 2)

    def test_returns_empty_for_no_google_id(self):
        self.assertEqual(get_user_accounts(""), [])
        self.assertEqual(get_user_accounts(None), [])


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


if __name__ == '__main__':
    unittest.main()
