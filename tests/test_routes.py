"""
Unit tests for routes.py (Flask route definitions).
"""
import json
import unittest
from unittest.mock import Mock, PropertyMock, patch

from app.routes import _create_json_response_no_cache, app_callback, app_ui


class TestCallbackServer(unittest.TestCase):
    """Test callback server endpoints."""

    def setUp(self):
        self.client = app_callback.test_client()
        app_callback.testing = True

    def test_callback_success_direct_login(self):
        """Test OAuth callback completing auth directly."""
        mock_kite_cls = Mock()
        mock_kite = Mock()
        mock_kite_cls.return_value = mock_kite
        mock_kite.generate_session.return_value = {"access_token": "new_token"}

        with patch('app.services.state_manager') as mock_state, \
             patch('app.services.session_manager') as mock_session, \
             patch('app.routes.get_active_accounts', return_value=[
                 {"name": "Mine", "api_key": "key1", "api_secret": "sec1"}
             ]), \
             patch('app.routes.fetch_in_progress') as mock_fetch_event, \
             patch('kiteconnect.KiteConnect', mock_kite_cls):
            mock_session.is_valid.return_value = False
            mock_fetch_event.is_set.return_value = False

            response = self.client.get('/callback?request_token=test_token_123')

            self.assertEqual(response.status_code, 200)
            self.assertIn(b'success', response.data.lower())
            mock_session.set_token.assert_called_once_with("Mine", "new_token")
            mock_session.save.assert_called_once()

    def test_callback_error(self):
        """Test OAuth callback without request token."""
        response = self.client.get('/callback')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'error', response.data.lower())


class TestUIServerRoutes(unittest.TestCase):
    """Test UI server endpoints."""

    def setUp(self):
        self.client = app_ui.test_client()
        app_ui.testing = True

    def test_status_endpoint(self):
        """Test /status endpoint returns correct structure."""
        with patch('app.services.state_manager') as mock_state, \
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

            mock_session.is_valid.return_value = True
            mock_format.return_value = None
            mock_market.return_value = False

            response = self.client.get('/status')

            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertIn('portfolio_state', data)
            self.assertIn('session_validity', data)
            self.assertIn('has_zerodha_accounts', data)
            self.assertIn('authenticated_accounts', data)
            self.assertIn('unauthenticated_accounts', data)
            self.assertEqual(response.headers.get('Cache-Control'), 'no-cache, no-store, must-revalidate')

    def test_stocks_data_endpoint(self):
        """Test /stocks_data endpoint returns sorted stocks."""
        from app.cache import cache
        original = cache.stocks
        try:
            cache.stocks = [
                {"tradingsymbol": "INFY", "quantity": 10},
                {"tradingsymbol": "TCS", "quantity": 5},
            ]
            response = self.client.get('/stocks_data')

            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(len(data), 2)
            self.assertEqual(data[0]["tradingsymbol"], "INFY")
        finally:
            cache.stocks = original

    def test_mf_holdings_data_endpoint(self):
        """Test /mf_holdings_data endpoint returns sorted MF holdings."""
        from app.cache import cache
        original = cache.mf_holdings
        try:
            cache.mf_holdings = [
                {"tradingsymbol": "MF2", "fund": "Fund B", "quantity": 100},
                {"tradingsymbol": "MF1", "fund": "Fund A", "quantity": 200},
            ]
            response = self.client.get('/mf_holdings_data')

            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(len(data), 2)
            self.assertEqual(data[0]["fund"], "Fund A")
        finally:
            cache.mf_holdings = original

    def test_sips_data_endpoint(self):
        """Test /sips_data endpoint returns sorted SIPs."""
        from app.cache import cache
        original = cache.sips
        try:
            cache.sips = [
                {"tradingsymbol": "SIP2", "status": "inactive"},
                {"tradingsymbol": "SIP1", "status": "active"},
            ]
            response = self.client.get('/sips_data')

            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertEqual(len(data), 2)
            self.assertEqual(data[0]["status"], "active")
        finally:
            cache.sips = original

    def test_portfolio_page(self):
        """Test root page renders landing page when not signed in."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'html', response.data.lower())
        # Landing page should contain sign-in prompt
        self.assertIn(b'Continue with Google', response.data)

    def test_portfolio_page_authenticated(self):
        """Test root page renders portfolio when signed in."""
        with self.client.session_transaction() as sess:
            sess['user'] = {
                'google_id': 'test123',
                'email': 'test@example.com',
                'name': 'Test User',
                'picture': '',
                'spreadsheet_id': 'sheet_abc',
                'google_credentials': {},
            }
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'html', response.data.lower())
        # ensure gold card displays subtitle and clickable drawer trigger
        self.assertIn(b'(ETFs + Physical + SGBs)', response.data)
        # ensure silver card includes ETFs subtitle
        self.assertIn(b'Silver <span class="card-subtitle">(ETFs)</span>', response.data)
        self.assertIn(b'id="gold_breakdown_drawer"', response.data)
        # ensure gold card is clickable with chevron indicator
        self.assertIn(b'card--clickable', response.data)
        self.assertIn(b'class="gold-chevron"', response.data)
        # toggle should no longer be an emoji
        self.assertNotIn(b'\xf0\x9f\x94\x80', response.data)  # not 🔀 or 📊 etc

    def test_nifty50_page(self):
        """Test /nifty50 page renders."""
        response = self.client.get('/nifty50')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'html', response.data.lower())

    def test_refresh_route_success(self):
        """Test /refresh endpoint triggers refresh."""
        with patch('app.cache.fetch_in_progress') as mock_event, \
             patch('app.fetchers.run_background_fetch') as mock_fetch, \
             patch('app.routes.get_authenticated_accounts', return_value=[{"name": "test"}]):

            mock_event.is_set.return_value = False

            response = self.client.post('/refresh')

            self.assertEqual(response.status_code, 202)
            data = json.loads(response.data)
            self.assertEqual(data['status'], 'started')
            mock_fetch.assert_called_once_with(is_manual=True, accounts=[{"name": "test"}])

    def test_refresh_route_conflict(self):
        """Test /refresh returns conflict when fetch in progress."""
        from app.cache import fetch_in_progress
        fetch_in_progress.set()
        try:
            response = self.client.post('/refresh')

            self.assertEqual(response.status_code, 409)
            data = json.loads(response.data)
            self.assertIn('error', data)
        finally:
            fetch_in_progress.clear()

    def test_refresh_route_no_authenticated_accounts(self):
        """Test /refresh still triggers refresh (gold/nifty) even with no authenticated accounts."""
        with patch('app.cache.fetch_in_progress') as mock_event, \
             patch('app.fetchers.run_background_fetch') as mock_fetch, \
             patch('app.routes.get_authenticated_accounts', return_value=[]):

            mock_event.is_set.return_value = False

            response = self.client.post('/refresh')

            self.assertEqual(response.status_code, 202)
            data = json.loads(response.data)
            self.assertEqual(data['status'], 'started')
            mock_fetch.assert_called_once_with(is_manual=True, accounts=[])


class TestSSE(unittest.TestCase):
    """Test Server-Sent Events functionality."""

    def setUp(self):
        self.client = app_ui.test_client()
        app_ui.testing = True

    def test_events_endpoint(self):
        """Test /events SSE endpoint."""
        with patch('app.services.state_manager') as mock_state, \
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

            mock_session.is_valid.return_value = True
            mock_format.return_value = None
            mock_market.return_value = True

            response = self.client.get('/events')

            self.assertEqual(response.status_code, 200)
            self.assertIn('text/event-stream', response.content_type)
            self.assertEqual(response.headers.get('Cache-Control'), 'no-cache')


class TestCreateJsonResponseNoCache(unittest.TestCase):
    """Test the _create_json_response_no_cache helper."""

    def test_without_sorting(self):
        data = [
            {"name": "B", "value": 2},
            {"name": "A", "value": 1},
            {"name": "C", "value": 3},
        ]

        with app_ui.app_context():
            response = _create_json_response_no_cache(data)
            self.assertEqual(response.headers.get('Cache-Control'), 'no-cache, no-store, must-revalidate')

    def test_with_sorting(self):
        data = [
            {"name": "B", "value": 2},
            {"name": "A", "value": 1},
            {"name": "C", "value": 3},
        ]

        with app_ui.app_context():
            response = _create_json_response_no_cache(data, sort_key="name")
            result_data = json.loads(response.data)
            self.assertEqual(result_data[0]["name"], "A")
            self.assertEqual(result_data[1]["name"], "B")
            self.assertEqual(result_data[2]["name"], "C")


if __name__ == '__main__':
    unittest.main()
