"""
Unit tests for routes.py (Flask route definitions) — multi-tenant version.
"""
import json
import unittest
from unittest.mock import Mock, PropertyMock, patch, MagicMock

from app.routes import _json_response, app_ui
from app.cache import PortfolioCacheManager, MarketCache, UserPortfolioData

# Reusable test user dict (simulates Flask session["user"])
_TEST_USER = {
    "google_id": "test123",
    "email": "test@example.com",
    "name": "Test User",
    "picture": "",
    "spreadsheet_id": "sheet_abc",
    "google_credentials": {},
}


def _inject_user(client, user=None):
    """Inject a user into the Flask session for authenticated requests."""
    with client.session_transaction() as sess:
        sess["user"] = user or _TEST_USER


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
             patch('app.services.get_user_accounts', return_value=[]):
            mock_state.last_error = None
            mock_state.get_portfolio_state.return_value = 'updated'
            mock_state.get_portfolio_last_updated.return_value = None
            mock_state.get_user_last_error.return_value = None
            mock_state.nifty50_state = 'updated'
            mock_state.nifty50_last_updated = None
            mock_state.physical_gold_state = 'updated'
            mock_state.physical_gold_last_updated = None
            mock_state.fixed_deposits_state = 'updated'
            mock_state.fixed_deposits_last_updated = None

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
            self.assertEqual(
                response.headers.get('Cache-Control'),
                'no-cache, no-store, must-revalidable'
                if False else 'no-cache, no-store, must-revalidate',
            )

    def test_stocks_data_endpoint_authenticated(self):
        """Authenticated user gets their own stocks."""
        with patch('app.routes.portfolio_cache') as mock_pcache:
            mock_data = UserPortfolioData(
                stocks=[
                    {"tradingsymbol": "INFY", "quantity": 10},
                    {"tradingsymbol": "TCS", "quantity": 5},
                ],
            )
            mock_pcache.get.return_value = mock_data

            _inject_user(self.client)
            response = self.client.get('/stocks_data')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["tradingsymbol"], "INFY")

    def test_stocks_data_unauthenticated(self):
        """Unauthenticated user gets empty list."""
        response = self.client.get('/stocks_data')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data, [])

    def test_mf_holdings_data_endpoint(self):
        """Authenticated user gets their MF holdings."""
        with patch('app.routes.portfolio_cache') as mock_pcache:
            mock_data = UserPortfolioData(
                mf_holdings=[
                    {"tradingsymbol": "MF2", "fund": "Fund B"},
                    {"tradingsymbol": "MF1", "fund": "Fund A"},
                ],
            )
            mock_pcache.get.return_value = mock_data

            _inject_user(self.client)
            response = self.client.get('/mf_holdings_data')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["fund"], "Fund A")

    def test_sips_data_endpoint(self):
        """Authenticated user gets their SIPs."""
        with patch('app.routes.portfolio_cache') as mock_pcache:
            mock_data = UserPortfolioData(
                sips=[
                    {"tradingsymbol": "SIP2", "status": "inactive"},
                    {"tradingsymbol": "SIP1", "status": "active"},
                ],
            )
            mock_pcache.get.return_value = mock_data

            _inject_user(self.client)
            response = self.client.get('/sips_data')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["status"], "active")

    def test_nifty50_data_endpoint(self):
        """Nifty 50 is global — no user context needed."""
        with patch('app.routes.market_cache') as mock_mc:
            mock_mc.nifty50 = [{"symbol": "TCS", "ltp": 3500}]
            response = self.client.get('/nifty50_data')

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data[0]["symbol"], "TCS")

    def test_portfolio_page_unauthenticated(self):
        """Root page renders landing page when not signed in."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Continue with Google', response.data)

    def test_portfolio_page_authenticated(self):
        """Root page renders portfolio dashboard when signed in."""
        with patch('app.routes.portfolio_cache') as mock_pcache, \
             patch('app.routes.ensure_user_loaded'), \
             patch('app.routes._build_status_response', return_value={}):
            mock_pcache.get.return_value = UserPortfolioData()
            _inject_user(self.client)
            response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'html', response.data.lower())
        # ensure gold card displays subtitle and clickable drawer trigger
        self.assertIn(b'(ETFs + Physical + SGBs)', response.data)
        self.assertIn(b'id="gold_breakdown_drawer"', response.data)
        self.assertIn(b'card--clickable', response.data)

    def test_nifty50_page(self):
        response = self.client.get('/nifty50')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'html', response.data.lower())

    def test_refresh_route_success(self):
        """Test /refresh endpoint triggers per-user refresh."""
        with patch('app.routes.portfolio_cache') as mock_pcache, \
             patch('app.routes.ensure_user_loaded'), \
             patch('app.routes.user_sheets_cache') as mock_usc, \
             patch('app.routes.get_authenticated_accounts', return_value=[{"name": "test"}]), \
             patch('app.fetchers.run_background_fetch') as mock_fetch:

            mock_pcache.is_fetch_in_progress.return_value = False

            _inject_user(self.client)
            response = self.client.post('/refresh')

        self.assertEqual(response.status_code, 202)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'started')
        mock_fetch.assert_called_once_with(
            is_manual=True, accounts=[{"name": "test"}], google_id="test123"
        )

    def test_refresh_route_conflict(self):
        """Test /refresh returns conflict when fetch in progress for this user."""
        with patch('app.routes.portfolio_cache') as mock_pcache:
            mock_pcache.is_fetch_in_progress.return_value = True

            _inject_user(self.client)
            response = self.client.post('/refresh')

        self.assertEqual(response.status_code, 409)
        data = json.loads(response.data)
        self.assertIn('error', data)

    def test_refresh_route_no_authenticated_accounts(self):
        """Refresh still triggers (gold/nifty) even without authenticated accounts."""
        with patch('app.routes.portfolio_cache') as mock_pcache, \
             patch('app.routes.ensure_user_loaded'), \
             patch('app.routes.user_sheets_cache') as mock_usc, \
             patch('app.routes.get_authenticated_accounts', return_value=[]), \
             patch('app.fetchers.run_background_fetch') as mock_fetch:

            mock_pcache.is_fetch_in_progress.return_value = False

            _inject_user(self.client)
            response = self.client.post('/refresh')

        self.assertEqual(response.status_code, 202)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'started')
        mock_fetch.assert_called_once_with(
            is_manual=True, accounts=[], google_id="test123"
        )


class TestSSE(unittest.TestCase):
    """Test Server-Sent Events functionality."""

    def setUp(self):
        self.client = app_ui.test_client()
        app_ui.testing = True

    def test_events_endpoint(self):
        """Test /events SSE endpoint returns text/event-stream."""
        with patch('app.services.state_manager') as mock_state, \
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
            mock_state.physical_gold_state = 'updated'
            mock_state.physical_gold_last_updated = None
            mock_state.fixed_deposits_state = 'updated'
            mock_state.fixed_deposits_last_updated = None

            mock_session.is_valid.return_value = True

            response = self.client.get('/events')

        self.assertEqual(response.status_code, 200)
        self.assertIn('text/event-stream', response.content_type)
        self.assertEqual(response.headers.get('Cache-Control'), 'no-cache')


class TestJsonResponse(unittest.TestCase):
    """Test the _json_response helper."""

    def test_without_sorting(self):
        data = [{"name": "B"}, {"name": "A"}, {"name": "C"}]
        with app_ui.app_context():
            response = _json_response(data)
        self.assertEqual(
            response.headers.get('Cache-Control'),
            'no-cache, no-store, must-revalidate',
        )

    def test_with_sorting(self):
        data = [{"name": "B"}, {"name": "A"}, {"name": "C"}]
        with app_ui.app_context():
            response = _json_response(data, sort_key="name")
        result_data = json.loads(response.data)
        self.assertEqual(result_data[0]["name"], "A")
        self.assertEqual(result_data[2]["name"], "C")


if __name__ == '__main__':
    unittest.main()
