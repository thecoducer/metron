"""
Unit tests for services.py (service instances and status helpers).
"""
import json
import unittest
from unittest.mock import PropertyMock, patch

from app.services import _build_status_response, broadcast_state_change


class TestBuildStatusResponse(unittest.TestCase):
    """Test the _build_status_response helper."""

    def test_returns_expected_fields(self):
        with patch('app.services.state_manager') as mock_state, \
             patch('app.services.session_manager') as mock_session, \
             patch('app.services.format_timestamp') as mock_format, \
             patch('app.services.is_market_open_ist') as mock_market, \
             patch('app.services.get_active_accounts', return_value=[
                 {"name": "Account1", "api_key": "key1", "api_key_env": "K1"}
             ]):
            mock_state.last_error = "Test error"
            mock_state.portfolio_state = 'updated'
            mock_state.nifty50_state = 'updating'
            mock_state.portfolio_last_updated = 1234567890.0
            mock_state.nifty50_last_updated = None
            mock_state.physical_gold_state = None
            mock_state.physical_gold_last_updated = None
            mock_state.fixed_deposits_state = None
            mock_state.fixed_deposits_last_updated = None

            mock_format.side_effect = lambda x: f"formatted_{x}" if x else None
            mock_session.is_valid.return_value = True
            mock_market.return_value = True

            response = _build_status_response()

            self.assertEqual(response['last_error'], "Test error")
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


class TestBroadcastStateChange(unittest.TestCase):
    """Test broadcast_state_change sends to all SSE clients."""

    def test_messages_sent_to_clients(self):
        with patch('app.services.sse_manager') as mock_sse, \
             patch('app.services.state_manager') as mock_state, \
             patch('app.services.session_manager') as mock_session, \
             patch('app.services.format_timestamp') as mock_format, \
             patch('app.services.is_market_open_ist') as mock_market, \
             patch('app.services.get_active_accounts', return_value=[]):
            type(mock_state).last_error = PropertyMock(return_value=None)
            type(mock_state).portfolio_state = PropertyMock(return_value='updated')
            type(mock_state).nifty50_state = PropertyMock(return_value='updated')
            type(mock_state).physical_gold_state = PropertyMock(return_value='updated')
            type(mock_state).fixed_deposits_state = PropertyMock(return_value='updated')
            type(mock_state).portfolio_last_updated = PropertyMock(return_value=None)
            type(mock_state).nifty50_last_updated = PropertyMock(return_value=None)
            type(mock_state).physical_gold_last_updated = PropertyMock(return_value=None)
            type(mock_state).fixed_deposits_last_updated = PropertyMock(return_value=None)

            mock_session.get_validity.return_value = {}
            mock_session.is_valid.return_value = True
            mock_format.return_value = None
            mock_market.return_value = True

            broadcast_state_change()

            mock_sse.broadcast.assert_called_once()
            message = json.loads(mock_sse.broadcast.call_args[0][0])
            self.assertEqual(message['portfolio_state'], 'updated')


if __name__ == '__main__':
    unittest.main()
