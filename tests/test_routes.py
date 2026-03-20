"""
Unit tests for routes.py (Flask route definitions) — multi-tenant version.
"""

import json
import unittest
from unittest.mock import Mock, patch

from app.cache import UserPortfolioData
from app.constants import APP_REQUEST_HEADER, APP_REQUEST_HEADER_VALUE
from app.routes import _json_response, app_ui

# Reusable test user dict (simulates Flask session["user"])
_TEST_USER = {
    "google_id": "test123",
    "email": "test@example.com",
    "name": "Test User",
    "picture": "",
    "spreadsheet_id": "sheet_abc",
    "google_credentials": {},
}

# Standard header dict for simulating an app-originated request
_APP_HEADERS = {APP_REQUEST_HEADER: APP_REQUEST_HEADER_VALUE}


def _inject_user(client, user=None):
    """Inject a user into the Flask session for authenticated requests."""
    u = user or _TEST_USER
    with client.session_transaction() as sess:
        sess["user"] = u
        sess["pin_verified"] = True
    # Also store a PIN in server memory so pin_required decorator passes
    from app.services import session_manager

    session_manager.set_pin(u["google_id"], "test01")


class TestUIServerRoutes(unittest.TestCase):
    """Test UI server endpoints."""

    def setUp(self):
        self.client = app_ui.test_client()
        app_ui.testing = True

    def test_status_endpoint(self):
        """Test /api/status endpoint returns correct structure."""
        with (
            patch("app.services.state_manager") as mock_state,
            patch("app.services.session_manager") as mock_session,
            patch("app.services.format_timestamp") as mock_format,
            patch("app.services.is_market_open_ist") as mock_market,
            patch("app.services.get_user_accounts", return_value=[]),
        ):
            mock_state.last_error = None
            mock_state.get_portfolio_state.return_value = "updated"
            mock_state.get_portfolio_last_updated.return_value = None
            mock_state.get_user_last_error.return_value = None
            mock_state.get_manual_ltp_state.return_value = None
            mock_state.get_manual_ltp_last_updated.return_value = None
            mock_state.get_sheets_state.return_value = None
            mock_state.get_sheets_last_updated.return_value = None
            mock_state.nifty50_state = "updated"
            mock_state.nifty50_last_updated = None
            mock_state.physical_gold_state = "updated"
            mock_state.physical_gold_last_updated = None
            mock_state.fixed_deposits_state = "updated"
            mock_state.fixed_deposits_last_updated = None

            mock_session.is_valid.return_value = True
            mock_format.return_value = None
            mock_market.return_value = False

            _inject_user(self.client)
            response = self.client.get("/api/status", headers=_APP_HEADERS)

            self.assertEqual(response.status_code, 200)
            data = json.loads(response.data)
            self.assertIn("portfolio_state", data)
            self.assertIn("session_validity", data)
            self.assertIn("has_zerodha_accounts", data)
            self.assertIn("authenticated_accounts", data)
            self.assertIn("unauthenticated_accounts", data)
            self.assertEqual(
                response.headers.get("Cache-Control"),
                "no-cache, no-store, must-revalidable" if False else "no-cache, no-store, must-revalidate",
            )

    def test_stocks_data_endpoint_authenticated(self):
        """Authenticated user gets their own stocks."""
        with patch("app.routes.portfolio_cache") as mock_pcache:
            mock_data = UserPortfolioData(
                stocks=[
                    {"tradingsymbol": "INFY", "quantity": 10},
                    {"tradingsymbol": "TCS", "quantity": 5},
                ],
                connected_accounts={"test"},
            )
            mock_pcache.get.return_value = mock_data

            _inject_user(self.client)
            response = self.client.get("/api/stocks_data", headers=_APP_HEADERS)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["tradingsymbol"], "INFY")

    def test_stocks_data_unauthenticated(self):
        """Unauthenticated user gets 401."""
        response = self.client.get("/api/stocks_data", headers=_APP_HEADERS)
        self.assertEqual(response.status_code, 401)

    def test_mf_holdings_data_endpoint(self):
        """Authenticated user gets their MF holdings."""
        with patch("app.routes.portfolio_cache") as mock_pcache:
            mock_data = UserPortfolioData(
                mf_holdings=[
                    {"tradingsymbol": "MF2", "fund": "Fund B"},
                    {"tradingsymbol": "MF1", "fund": "Fund A"},
                ],
                connected_accounts={"test"},
            )
            mock_pcache.get.return_value = mock_data

            _inject_user(self.client)
            response = self.client.get("/api/mf_holdings_data", headers=_APP_HEADERS)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["fund"], "Fund A")

    def test_sips_data_endpoint(self):
        """Authenticated user gets their SIPs."""
        with patch("app.routes.portfolio_cache") as mock_pcache:
            mock_data = UserPortfolioData(
                sips=[
                    {"tradingsymbol": "SIP2", "status": "inactive"},
                    {"tradingsymbol": "SIP1", "status": "active"},
                ],
                connected_accounts={"test"},
            )
            mock_pcache.get.return_value = mock_data

            _inject_user(self.client)
            response = self.client.get("/api/sips_data", headers=_APP_HEADERS)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["status"], "active")

    def test_nifty50_data_endpoint(self):
        """Nifty 50 is global — no user context needed."""
        with patch("app.routes.market_cache") as mock_mc:
            mock_mc.nifty50 = [{"symbol": "TCS", "ltp": 3500}]
            response = self.client.get("/api/nifty50_data", headers=_APP_HEADERS)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data[0]["symbol"], "TCS")

    def test_portfolio_page_unauthenticated(self):
        """Root page renders landing page when not signed in."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Continue with Google", response.data)

    def test_portfolio_page_authenticated(self):
        """Root page renders portfolio dashboard when signed in."""
        with (
            patch("app.routes.portfolio_cache") as mock_pcache,
            patch("app.routes.ensure_user_loaded"),
            patch("app.routes._build_status_response", return_value={}),
            patch("app.firebase_store.has_pin", return_value=False),
            patch("app.routes.user_sheets_cache") as mock_usc,
        ):
            mock_pcache.get.return_value = UserPortfolioData()
            mock_usc.is_fully_cached.return_value = False
            _inject_user(self.client)
            response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"html", response.data.lower())
        # ensure gold section displays subtitle and rhythm strip
        self.assertIn(b"(ETFs + Physical + SGBs)", response.data)
        self.assertIn(b"gold-rhythm", response.data)
        self.assertIn(b"gold_proportion_bar", response.data)

    def test_nifty50_page(self):
        response = self.client.get("/nifty50")
        self.assertEqual(response.status_code, 401)
        self.assertIn(b'{"error":"authentication required"}\n', response.data.lower())

    def test_refresh_route_success(self):
        """Test /api/refresh endpoint triggers per-user refresh."""
        with (
            patch("app.routes.portfolio_cache") as mock_pcache,
            patch("app.routes.ensure_user_loaded"),
            patch("app.routes.user_sheets_cache"),
            patch("app.routes.get_authenticated_accounts", return_value=[{"name": "test"}]),
            patch("app.fetchers.run_background_fetch") as mock_fetch,
        ):
            mock_pcache.is_fetch_in_progress.return_value = False

            _inject_user(self.client)
            response = self.client.post("/api/refresh", headers=_APP_HEADERS)

        self.assertEqual(response.status_code, 202)
        data = json.loads(response.data)
        self.assertEqual(data["status"], "started")
        mock_fetch.assert_called_once_with(
            is_manual=True, accounts=[{"name": "test"}], google_id="test123", manual_symbols=[]
        )

    def test_refresh_route_conflict(self):
        """Test /api/refresh returns conflict when fetch in progress for this user."""
        with patch("app.routes.portfolio_cache") as mock_pcache:
            mock_pcache.is_fetch_in_progress.return_value = True

            _inject_user(self.client)
            response = self.client.post("/api/refresh", headers=_APP_HEADERS)

        self.assertEqual(response.status_code, 409)
        data = json.loads(response.data)
        self.assertIn("error", data)

    def test_refresh_route_no_authenticated_accounts(self):
        """Refresh still triggers (gold/nifty) even without authenticated accounts."""
        with (
            patch("app.routes.portfolio_cache") as mock_pcache,
            patch("app.routes.ensure_user_loaded"),
            patch("app.routes.user_sheets_cache"),
            patch("app.routes.get_authenticated_accounts", return_value=[]),
            patch("app.fetchers.run_background_fetch") as mock_fetch,
        ):
            mock_pcache.is_fetch_in_progress.return_value = False

            _inject_user(self.client)
            response = self.client.post("/api/refresh", headers=_APP_HEADERS)

        self.assertEqual(response.status_code, 202)
        data = json.loads(response.data)
        self.assertEqual(data["status"], "started")
        mock_fetch.assert_called_once_with(is_manual=True, accounts=[], google_id="test123", manual_symbols=[])

    def test_remove_zerodha_account_success(self):
        """Deleting a Zerodha account clears session and portfolio cache."""
        with (
            patch("app.firebase_store.remove_zerodha_account") as mock_remove,
            patch("app.routes.session_manager") as mock_session,
            patch("app.routes.portfolio_cache") as mock_pcache,
            patch("app.broker_sync.delete_account_from_sheets") as mock_delete_sheets,
        ):
            _inject_user(self.client)
            response = self.client.delete("/api/settings/zerodha/MyAccount", headers=_APP_HEADERS)

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data["status"], "removed")
        mock_remove.assert_called_once_with("test123", "MyAccount")
        mock_session.invalidate.assert_called_once_with("test123", "MyAccount")
        mock_pcache.clear.assert_called_once_with("test123")
        mock_delete_sheets.assert_called_once_with("test123", "MyAccount")

    def test_remove_zerodha_account_not_found(self):
        """Deleting a non-existent account returns 404."""
        with patch("app.firebase_store.remove_zerodha_account", side_effect=ValueError("Account 'Bad' not found")):
            _inject_user(self.client)
            response = self.client.delete("/api/settings/zerodha/Bad", headers=_APP_HEADERS)

        self.assertEqual(response.status_code, 404)
        data = json.loads(response.data)
        self.assertIn("error", data)


class TestJsonResponse(unittest.TestCase):
    """Test the _json_response helper."""

    def test_without_sorting(self):
        data = [{"name": "B"}, {"name": "A"}, {"name": "C"}]
        with app_ui.app_context():
            response = _json_response(data)
        self.assertEqual(
            response.headers.get("Cache-Control"),
            "no-cache, no-store, must-revalidate",
        )

    def test_with_sorting(self):
        data = [{"name": "B"}, {"name": "A"}, {"name": "C"}]
        with app_ui.app_context():
            response = _json_response(data, sort_key="name")
        result_data = json.loads(response.data)
        self.assertEqual(result_data[0]["name"], "A")
        self.assertEqual(result_data[2]["name"], "C")


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# PIN Verify Rate Limiting Integration Tests
# ---------------------------------------------------------------------------


class TestPinVerifyRateLimiting(unittest.TestCase):
    """Integration tests for the rate-limited /api/pin/verify endpoint."""

    def setUp(self):
        self.client = app_ui.test_client()
        app_ui.testing = True

    def _inject_user(self, pin_verified=False):
        with self.client.session_transaction() as sess:
            sess["user"] = _TEST_USER
            if pin_verified:
                sess["pin_verified"] = True

    def _verify(self, pin="abc123"):
        return self.client.post(
            "/api/pin/verify",
            headers={**_APP_HEADERS, "Content-Type": "application/json"},
            data=json.dumps({"pin": pin}),
        )

    @patch("app.routes.verify_user_pin", return_value=False)
    @patch("app.routes.pin_rate_limiter")
    def test_lockout_returns_429(self, mock_limiter, mock_verify_pin):
        """When user is locked out, endpoint returns 429 with retry_after."""
        mock_limiter.check.return_value = (False, 900)
        self._inject_user()
        resp = self._verify()
        self.assertEqual(resp.status_code, 429)
        data = json.loads(resp.data)
        self.assertTrue(data["locked"])
        self.assertEqual(data["retry_after"], 900)
        self.assertEqual(resp.headers.get("Retry-After"), "900")

    @patch("app.routes.ensure_user_loaded")
    @patch("app.routes.session_manager")
    @patch("app.routes.verify_user_pin", return_value=True)
    @patch("app.routes.pin_rate_limiter")
    def test_success_clears_limiter(self, mock_limiter, mock_verify_pin, mock_sm, mock_eul):
        """Successful verify calls record_success to clear rate state."""
        mock_limiter.check.return_value = (True, None)
        self._inject_user()
        resp = self._verify()
        self.assertEqual(resp.status_code, 200)
        mock_limiter.record_success.assert_called_once_with(_TEST_USER["google_id"])

    @patch("app.routes.verify_user_pin", return_value=False)
    @patch("app.routes.pin_rate_limiter")
    def test_failure_records_attempt(self, mock_limiter, mock_verify_pin):
        """Failed verify calls record_failure."""
        mock_limiter.check.return_value = (True, None)
        mock_limiter.record_failure.return_value = (3, None)
        self._inject_user()
        resp = self._verify()
        self.assertEqual(resp.status_code, 401)
        data = json.loads(resp.data)
        self.assertEqual(data["attempts"], 3)
        mock_limiter.record_failure.assert_called_once_with(_TEST_USER["google_id"])

    @patch("app.routes.verify_user_pin", return_value=False)
    @patch("app.routes.pin_rate_limiter")
    def test_failure_at_threshold_returns_429(self, mock_limiter, mock_verify_pin):
        """When record_failure returns a lockout, endpoint returns 429."""
        mock_limiter.check.return_value = (True, None)
        mock_limiter.record_failure.return_value = (5, 900)
        self._inject_user()
        resp = self._verify()
        self.assertEqual(resp.status_code, 429)
        data = json.loads(resp.data)
        self.assertTrue(data["locked"])
        self.assertEqual(data["retry_after"], 900)

    @patch("app.routes.reset_zerodha_data")
    @patch("app.routes.pin_rate_limiter")
    @patch("app.routes.session_manager")
    @patch("app.routes.portfolio_cache")
    def test_pin_reset_clears_rate_limiter(self, mock_pcache, mock_sm, mock_limiter, mock_reset):
        """PIN reset must clear the rate limiter for the user."""
        self._inject_user(pin_verified=True)
        resp = self.client.post("/api/pin/reset", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 200)
        mock_limiter.clear.assert_called_once_with(_TEST_USER["google_id"])


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------


class TestAuthRoutes(unittest.TestCase):
    def setUp(self):
        self.client = app_ui.test_client()
        app_ui.testing = True

    def test_auth_me_unauthenticated(self):
        resp = self.client.get("/api/auth/me")
        self.assertEqual(resp.status_code, 401)
        data = json.loads(resp.data)
        self.assertFalse(data["authenticated"])

    def test_auth_me_authenticated(self):
        _inject_user(self.client)
        resp = self.client.get("/api/auth/me")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertTrue(data["authenticated"])
        self.assertEqual(data["email"], _TEST_USER["email"])

    @patch("app.api.google_auth.build_oauth_flow")
    def test_google_login_redirect(self, mock_flow_builder):
        mock_flow = Mock()
        mock_flow.authorization_url.return_value = ("https://accounts.google.com/auth", "state123")
        mock_flow_builder.return_value = mock_flow
        resp = self.client.get("/api/auth/google/login")
        self.assertEqual(resp.status_code, 302)
        mock_flow.authorization_url.assert_called_once_with(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )

    @patch("app.api.google_auth.build_oauth_flow", side_effect=FileNotFoundError("no config"))
    def test_google_login_no_config(self, mock_flow_builder):
        resp = self.client.get("/api/auth/google/login")
        self.assertEqual(resp.status_code, 500)

    @patch("app.api.google_auth.build_oauth_flow", side_effect=RuntimeError("boom"))
    def test_google_login_error(self, mock_flow_builder):
        resp = self.client.get("/api/auth/google/login")
        self.assertEqual(resp.status_code, 500)

    def test_google_callback_no_code(self):
        resp = self.client.get("/api/auth/google/callback")
        self.assertEqual(resp.status_code, 400)

    @patch("app.firebase_store.upsert_user")
    @patch("app.firebase_store.get_user", return_value={"spreadsheet_id": "sid"})
    @patch("app.api.google_auth.get_user_info", return_value={"id": "g1", "email": "e", "name": "N", "picture": ""})
    @patch("app.api.google_auth.credentials_to_dict", return_value={"token": "t"})
    @patch("app.api.google_auth.exchange_code_for_credentials")
    def test_google_callback_success(self, mock_exchange, mock_creds, mock_info, mock_get, mock_upsert):
        mock_upsert.return_value = {}
        resp = self.client.get("/api/auth/google/callback?code=authcode")
        self.assertEqual(resp.status_code, 302)  # redirect to /

    @patch("app.api.google_auth.exchange_code_for_credentials", side_effect=RuntimeError("x"))
    def test_google_callback_error(self, mock_exchange):
        resp = self.client.get("/api/auth/google/callback?code=bad")
        self.assertEqual(resp.status_code, 500)

    @patch("app.routes.session_manager")
    def test_logout(self, mock_sm):
        _inject_user(self.client)
        resp = self.client.post("/api/auth/logout", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["status"], "logged_out")


# ---------------------------------------------------------------------------
# PIN routes
# ---------------------------------------------------------------------------


class TestPinRoutes(unittest.TestCase):
    def setUp(self):
        self.client = app_ui.test_client()
        app_ui.testing = True

    @patch("app.firebase_store.get_zerodha_account_names", return_value=["Acc1"])
    @patch("app.firebase_store.has_pin", return_value=True)
    def test_pin_status(self, mock_has_pin, mock_names):
        _inject_user(self.client)
        resp = self.client.get("/api/pin/status", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertTrue(data["has_pin"])
        self.assertTrue(data["has_zerodha_accounts"])
        # pin_verified is True because _inject_user sets it
        self.assertFalse(data["needs_pin"])

    @patch("app.routes.ensure_user_loaded")
    @patch("app.firebase_store.has_pin", return_value=False)
    @patch("app.firebase_store.store_pin_check")
    def test_pin_setup(self, mock_store, mock_has_pin, mock_eul):
        _inject_user(self.client)
        resp = self.client.post(
            "/api/pin/setup",
            headers={**_APP_HEADERS, "Content-Type": "application/json"},
            data=json.dumps({"pin": "abc123"}),
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["status"], "pin_created")

    @patch("app.firebase_store.has_pin", return_value=True)
    def test_pin_setup_already_exists(self, mock_has_pin):
        _inject_user(self.client)
        resp = self.client.post(
            "/api/pin/setup",
            headers={**_APP_HEADERS, "Content-Type": "application/json"},
            data=json.dumps({"pin": "abc123"}),
        )
        self.assertEqual(resp.status_code, 409)

    def test_pin_setup_invalid_format(self):
        _inject_user(self.client)
        resp = self.client.post(
            "/api/pin/setup",
            headers={**_APP_HEADERS, "Content-Type": "application/json"},
            data=json.dumps({"pin": "12"}),  # too short
        )
        self.assertEqual(resp.status_code, 400)

    @patch("app.routes.verify_user_pin", return_value=False)
    @patch("app.routes.pin_rate_limiter")
    def test_pin_verify_invalid_format(self, mock_limiter, mock_verify):
        mock_limiter.check.return_value = (True, None)
        _inject_user(self.client)
        resp = self.client.post(
            "/api/pin/verify",
            headers={**_APP_HEADERS, "Content-Type": "application/json"},
            data=json.dumps({"pin": "ab"}),  # too short
        )
        self.assertEqual(resp.status_code, 400)


# ---------------------------------------------------------------------------
# Data routes (physical gold, FD, all_data, market indices)
# ---------------------------------------------------------------------------


class TestDataRoutes(unittest.TestCase):
    def setUp(self):
        self.client = app_ui.test_client()
        app_ui.testing = True

    @patch("app.routes._build_gold_data", return_value=[{"date": "2024-01-01"}])
    def test_physical_gold_data(self, mock_build):
        _inject_user(self.client)
        resp = self.client.get("/api/physical_gold_data", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 200)

    @patch("app.routes._build_fd_data", return_value=[{"bank_name": "SBI"}])
    def test_fixed_deposits_data(self, mock_build):
        _inject_user(self.client)
        resp = self.client.get("/api/fixed_deposits_data", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 200)

    def test_fd_summary_data(self):
        _inject_user(self.client)
        resp = self.client.get("/api/fd_summary_data", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data, [])

    @patch("app.routes._build_stocks_data", return_value=[])
    @patch("app.routes._build_mf_data", return_value=[])
    @patch("app.routes._build_sips_data", return_value=[])
    @patch("app.routes._build_gold_data", return_value=[])
    @patch("app.routes._build_fd_data", return_value=[])
    @patch("app.routes._build_status_response", return_value={})
    def test_all_data(self, mock_status, mock_fd, mock_gold, mock_sips, mock_mf, mock_stocks):
        _inject_user(self.client)
        resp = self.client.get("/api/all_data", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertIn("stocks", data)
        self.assertIn("mfHoldings", data)
        self.assertIn("physicalGold", data)

    @patch("app.routes._build_stocks_data", return_value=[{"tradingsymbol": "RELIANCE"}])
    @patch("app.routes._build_mf_data", return_value=[])
    @patch("app.routes._build_sips_data", return_value=[])
    @patch("app.routes._build_status_response", return_value={"portfolio_state": "updated"})
    def test_portfolio_data(self, mock_status, mock_sips, mock_mf, mock_stocks):
        _inject_user(self.client)
        resp = self.client.get("/api/data/portfolio", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertIn("stocks", data)
        self.assertIn("mfHoldings", data)
        self.assertIn("sips", data)
        self.assertIn("status", data)
        self.assertNotIn("physicalGold", data)
        self.assertNotIn("fixedDeposits", data)

    @patch("app.routes._build_gold_data", return_value=[{"date": "2024-01-01"}])
    @patch("app.routes._build_fd_data", return_value=[])
    @patch("app.routes._build_status_response", return_value={"sheets_state": "updated"})
    def test_sheets_data(self, mock_status, mock_fd, mock_gold):
        _inject_user(self.client)
        resp = self.client.get("/api/data/sheets", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertIn("physicalGold", data)
        self.assertIn("fixedDeposits", data)
        self.assertIn("status", data)
        self.assertNotIn("stocks", data)
        self.assertNotIn("mfHoldings", data)

    @patch("app.routes.market_cache")
    def test_market_indices_fresh(self, mock_mc):
        mock_mc.market_indices = {}
        _inject_user(self.client)
        resp = self.client.get("/api/market_indices", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(json.loads(resp.data), {})

    @patch("app.routes.market_cache")
    def test_market_indices_cached(self, mock_mc):
        mock_mc.market_indices = {"nifty50": {"value": 100}}
        _inject_user(self.client)
        resp = self.client.get("/api/market_indices", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(json.loads(resp.data), {"nifty50": {"value": 100}})


# ---------------------------------------------------------------------------
# Healthz, other routes
# ---------------------------------------------------------------------------


class TestMiscRoutes(unittest.TestCase):
    def setUp(self):
        self.client = app_ui.test_client()
        app_ui.testing = True

    def test_healthz(self):
        resp = self.client.get("/healthz")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["status"], "ok")

    def test_privacy_page(self):
        resp = self.client.get("/privacy")
        self.assertEqual(resp.status_code, 200)

    def test_terms_page(self):
        resp = self.client.get("/terms")
        self.assertEqual(resp.status_code, 200)

    def test_contact_page(self):
        resp = self.client.get("/contact")
        self.assertEqual(resp.status_code, 200)

    def test_details_page_valid(self):
        _inject_user(self.client)
        resp = self.client.get("/details/stocks")
        self.assertEqual(resp.status_code, 200)

    def test_details_page_invalid_key(self):
        _inject_user(self.client)
        resp = self.client.get("/details/invalid")
        self.assertEqual(resp.status_code, 302)  # redirect to /


# ---------------------------------------------------------------------------
# Settings routes
# ---------------------------------------------------------------------------


class TestSettingsRoutes(unittest.TestCase):
    def setUp(self):
        self.client = app_ui.test_client()
        app_ui.testing = True

    @patch("app.routes.session_manager")
    @patch("app.firebase_store.get_zerodha_accounts", return_value=[{"name": "Acc1", "api_key": "k1"}])
    def test_get_settings(self, mock_accs, mock_sm):
        mock_sm.get_pin.return_value = "123456"
        mock_sm.is_valid.return_value = True
        mock_sm.get_validity.return_value = {"Acc1": True}
        _inject_user(self.client)
        resp = self.client.get("/api/settings", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertIn("zerodha_accounts", data)

    @patch("app.routes.session_manager")
    @patch("app.firebase_store.add_zerodha_account")
    def test_add_zerodha(self, mock_add, mock_sm):
        mock_sm.get_pin.return_value = "123456"
        _inject_user(self.client)
        resp = self.client.post(
            "/api/settings/zerodha",
            headers={**_APP_HEADERS, "Content-Type": "application/json"},
            data=json.dumps({"account_name": "Test", "api_key": "k", "api_secret": "s"}),
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["status"], "saved")

    @patch("app.routes.session_manager")
    def test_add_zerodha_missing_fields(self, mock_sm):
        mock_sm.get_pin.return_value = "123456"
        _inject_user(self.client)
        resp = self.client.post(
            "/api/settings/zerodha",
            headers={**_APP_HEADERS, "Content-Type": "application/json"},
            data=json.dumps({"account_name": ""}),
        )
        self.assertEqual(resp.status_code, 400)

    @patch("app.routes.session_manager")
    def test_add_zerodha_no_pin(self, mock_sm):
        mock_sm.get_pin.return_value = None
        _inject_user(self.client)
        resp = self.client.post(
            "/api/settings/zerodha",
            headers={**_APP_HEADERS, "Content-Type": "application/json"},
            data=json.dumps({"account_name": "T", "api_key": "k", "api_secret": "s"}),
        )
        self.assertEqual(resp.status_code, 403)

    @patch("app.routes.session_manager")
    @patch("app.firebase_store.add_zerodha_account", side_effect=ValueError("dup"))
    def test_add_zerodha_duplicate(self, mock_add, mock_sm):
        mock_sm.get_pin.return_value = "123456"
        _inject_user(self.client)
        resp = self.client.post(
            "/api/settings/zerodha",
            headers={**_APP_HEADERS, "Content-Type": "application/json"},
            data=json.dumps({"account_name": "T", "api_key": "k", "api_secret": "s"}),
        )
        self.assertEqual(resp.status_code, 409)


# ---------------------------------------------------------------------------
# Sheets CRUD routes
# ---------------------------------------------------------------------------


class TestSheetsCRUD(unittest.TestCase):
    def setUp(self):
        self.client = app_ui.test_client()
        app_ui.testing = True

    def _inject(self):
        _inject_user(self.client)

    @patch("app.routes._get_sheets_client")
    def test_sheets_list(self, mock_get_client):
        mock_client = Mock()
        mock_client.ensure_sheet_tab.return_value = None
        mock_client.fetch_sheet_data_until_blank.return_value = [
            ["Symbol", "Qty", "AvgPrice", "Exchange", "Account"],
            ["INFY", "10", "1500", "NSE", "Manual"],
        ]
        mock_get_client.return_value = (mock_client, "sid", None)
        self._inject()
        resp = self.client.get("/api/sheets/stocks", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(len(data), 1)

    def test_sheets_list_unknown_type(self):
        self._inject()
        resp = self.client.get("/api/sheets/unknown", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 400)

    @patch("app.routes._get_sheets_client")
    def test_sheets_list_error(self, mock_get_client):
        mock_get_client.return_value = (None, None, "no creds")
        self._inject()
        resp = self.client.get("/api/sheets/stocks", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 400)

    @patch("app.routes._fetch_uncached_manual_ltps")
    @patch("app.routes._refresh_single_sheet_cache")
    @patch("app.routes._build_data_for_type", return_value={})
    @patch("app.routes._validate_nse_symbol", return_value={"ltp": 100})
    @patch("app.routes.manual_ltp_cache")
    @patch("app.routes._get_sheets_client")
    def test_sheets_add_stocks(self, mock_get_client, mock_ltp, mock_validate, mock_build, mock_refresh, mock_uncached):
        mock_client = Mock()
        mock_client.ensure_sheet_tab.return_value = None
        mock_client.append_row.return_value = 5
        mock_get_client.return_value = (mock_client, "sid", None)
        self._inject()
        resp = self.client.post(
            "/api/sheets/stocks",
            headers={**_APP_HEADERS, "Content-Type": "application/json"},
            data=json.dumps({"symbol": "INFY", "qty": "10", "avg_price": "1500", "exchange": "NSE", "account": "A"}),
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["status"], "added")

    @patch("app.routes._validate_nse_symbol", return_value=None)
    @patch("app.routes._get_sheets_client")
    def test_sheets_add_invalid_symbol(self, mock_get_client, mock_validate):
        mock_get_client.return_value = (Mock(), "sid", None)
        self._inject()
        resp = self.client.post(
            "/api/sheets/stocks",
            headers={**_APP_HEADERS, "Content-Type": "application/json"},
            data=json.dumps({"symbol": "FAKE", "qty": "10", "avg_price": "100", "exchange": "NSE", "account": "A"}),
        )
        self.assertEqual(resp.status_code, 400)

    @patch("app.routes._refresh_single_sheet_cache")
    @patch("app.routes._build_data_for_type", return_value={})
    @patch("app.routes._get_sheets_client")
    def test_sheets_update(self, mock_get_client, mock_build, mock_refresh):
        mock_client = Mock()
        mock_get_client.return_value = (mock_client, "sid", None)
        self._inject()
        resp = self.client.put(
            "/api/sheets/mutual_funds/5",
            headers={**_APP_HEADERS, "Content-Type": "application/json"},
            data=json.dumps({"fund": "AXIS", "qty": "100", "avg_nav": "50", "account": "X"}),
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["status"], "updated")

    def test_sheets_update_header_row(self):
        self._inject()
        resp = self.client.put(
            "/api/sheets/stocks/1",
            headers={**_APP_HEADERS, "Content-Type": "application/json"},
            data=json.dumps({"symbol": "X"}),
        )
        self.assertEqual(resp.status_code, 400)

    @patch("app.routes._refresh_single_sheet_cache")
    @patch("app.routes._build_data_for_type", return_value={})
    @patch("app.routes._get_sheets_client")
    def test_sheets_delete(self, mock_get_client, mock_build, mock_refresh):
        mock_client = Mock()
        mock_get_client.return_value = (mock_client, "sid", None)
        self._inject()
        resp = self.client.delete(
            "/api/sheets/sips/3",
            headers=_APP_HEADERS,
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["status"], "deleted")

    def test_sheets_delete_header_row(self):
        self._inject()
        resp = self.client.delete(
            "/api/sheets/stocks/1",
            headers=_APP_HEADERS,
        )
        self.assertEqual(resp.status_code, 400)

    def test_sheets_delete_unknown_type(self):
        self._inject()
        resp = self.client.delete(
            "/api/sheets/bad/5",
            headers=_APP_HEADERS,
        )
        self.assertEqual(resp.status_code, 400)

    @patch("app.routes._get_sheets_client")
    def test_sheets_list_refresh_error_returns_401(self, mock_get_client):
        """RefreshError on list should return 401 with re-auth message."""
        mock_client = Mock()
        mock_client.ensure_sheet_tab.side_effect = type("RefreshError", (Exception,), {})("creds expired")
        mock_get_client.return_value = (mock_client, "sid", None)
        self._inject()
        resp = self.client.get("/api/sheets/stocks", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 401)
        self.assertIn("sign in", json.loads(resp.data)["error"].lower())

    @patch("app.routes._fetch_uncached_manual_ltps")
    @patch("app.routes._refresh_single_sheet_cache")
    @patch("app.routes._build_data_for_type", return_value={})
    @patch("app.routes._get_sheets_client")
    def test_sheets_add_refresh_error_returns_401(self, mock_get_client, mock_build, mock_refresh, mock_uncached):
        mock_client = Mock()
        mock_client.ensure_sheet_tab.side_effect = type("RefreshError", (Exception,), {})("expired")
        mock_get_client.return_value = (mock_client, "sid", None)
        self._inject()
        resp = self.client.post(
            "/api/sheets/mutual_funds",
            data=json.dumps({"fund_name": "Test"}),
            content_type="application/json",
            headers=_APP_HEADERS,
        )
        self.assertEqual(resp.status_code, 401)

    @patch("app.routes._build_data_for_type", return_value={})
    @patch("app.routes._refresh_single_sheet_cache")
    @patch("app.routes._get_sheets_client")
    def test_sheets_delete_refresh_error_returns_401(self, mock_get_client, mock_refresh, mock_build):
        mock_client = Mock()
        mock_client.delete_row.side_effect = type("RefreshError", (Exception,), {})("expired")
        mock_get_client.return_value = (mock_client, "sid", None)
        self._inject()
        resp = self.client.delete("/api/sheets/stocks/3", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 401)


# ---------------------------------------------------------------------------
# Route helpers (unit tests)
# ---------------------------------------------------------------------------


class TestRouteHelpers(unittest.TestCase):
    """Test internal route helper functions."""

    def test_get_user_fetch_lock(self):
        from app.fetchers import _get_user_fetch_lock

        lock1 = _get_user_fetch_lock("user1")
        lock2 = _get_user_fetch_lock("user1")
        self.assertIs(lock1, lock2)  # same lock for same user
        lock3 = _get_user_fetch_lock("user2")
        self.assertIsNot(lock1, lock3)

    @patch("app.firebase_store.get_google_credentials", return_value=None)
    def test_get_sheets_client_no_creds(self, mock_get_creds):
        from app.routes import _get_sheets_client, app_ui

        with app_ui.test_request_context("/"):
            from flask import session

            session["user"] = {"google_id": "g1"}
            client, sid, err = _get_sheets_client()
            self.assertIsNone(client)
            self.assertIsNotNone(err)

    @patch("app.routes._fetch_user_sheets_data", return_value=([{"a": 1}], None))
    @patch("app.routes.enrich_holdings_with_prices", return_value=[{"a": 1}])
    @patch("app.routes.market_cache")
    def test_build_gold_data(self, mock_mc, mock_enrich, mock_fetch):
        from app.routes import _build_gold_data

        mock_mc.gold_prices = {}
        result = _build_gold_data({"google_id": "g1"})
        self.assertEqual(len(result), 1)

    @patch("app.routes._fetch_user_sheets_data", return_value=(None, None))
    def test_build_gold_data_none(self, mock_fetch):
        from app.routes import _build_gold_data

        result = _build_gold_data({"google_id": "g1"})
        self.assertEqual(result, [])

    @patch("app.routes._fetch_user_sheets_data", return_value=(None, [{"deposited_on": "2024-01-01"}]))
    def test_build_fd_data(self, mock_fetch):
        from app.routes import _build_fd_data

        result = _build_fd_data({"google_id": "g1"})
        self.assertEqual(len(result), 1)

    @patch("app.routes._fetch_user_sheets_data", return_value=(None, None))
    def test_build_fd_data_none(self, mock_fetch):
        from app.routes import _build_fd_data

        result = _build_fd_data({"google_id": "g1"})
        self.assertEqual(result, [])

    @patch("app.routes._fetch_manual_entries", return_value=[])
    @patch("app.routes.portfolio_cache")
    def test_build_mf_data(self, mock_pc, mock_manual):
        from app.cache import UserPortfolioData
        from app.routes import _build_mf_data

        mock_pc.get.return_value = UserPortfolioData(
            mf_holdings=[{"fund": "A", "tradingsymbol": "A"}], connected_accounts={"test"}
        )
        result = _build_mf_data({"google_id": "g1"})
        self.assertEqual(len(result), 1)

    @patch(
        "app.routes._fetch_manual_entries",
        return_value=[
            {
                "fund": "B",
                "qty": "10",
                "amount": "500",
                "frequency": "MONTHLY",
                "installments": "12",
                "completed": "3",
                "status": "ACTIVE",
                "next_due": "2025-01-01",
                "account": "Manual",
                "row_number": 2,
            }
        ],
    )
    @patch("app.routes.portfolio_cache")
    def test_build_sips_data_with_manual(self, mock_pc, mock_manual):
        from app.cache import UserPortfolioData
        from app.routes import _build_sips_data

        mock_pc.get.return_value = UserPortfolioData(sips=[])
        result = _build_sips_data({"google_id": "g1"})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["fund"], "B")

    @patch("app.routes._enrich_manual_entries_with_ltp")
    @patch("app.routes._fetch_manual_entries")
    @patch("app.routes.portfolio_cache")
    def test_build_stocks_data_with_manual(self, mock_pc, mock_manual, mock_enrich):
        from app.cache import UserPortfolioData
        from app.routes import _build_stocks_data

        mock_pc.get.return_value = UserPortfolioData(stocks=[])
        mock_manual.side_effect = [
            [{"symbol": "INFY", "qty": "10", "avg_price": "1500", "exchange": "NSE", "account": "A", "row_number": 2}],
            [],
        ]
        result = _build_stocks_data({"google_id": "g1"})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["tradingsymbol"], "INFY")

    @patch("app.routes._enrich_manual_entries_with_ltp")
    @patch("app.routes._fetch_manual_entries")
    @patch("app.routes.portfolio_cache")
    def test_build_stocks_data_broker_offline_uses_sheet_fallback(self, mock_pc, mock_manual, mock_enrich):
        """When no accounts connected, cached broker stocks are ignored and
        zerodha-sourced sheet entries serve as fallback."""
        from app.cache import UserPortfolioData
        from app.routes import _build_stocks_data

        # Cache has stale broker data, but no accounts connected
        mock_pc.get.return_value = UserPortfolioData(
            stocks=[{"tradingsymbol": "STALE", "quantity": 99}],
            connected_accounts=set(),
        )
        mock_manual.side_effect = [
            [
                {
                    "symbol": "INFY",
                    "qty": "5",
                    "avg_price": "1000",
                    "exchange": "NSE",
                    "source": "zerodha",
                    "account": "Z1",
                    "row_number": 2,
                }
            ],
            [],
        ]
        result = _build_stocks_data({"google_id": "g1"})
        # Stale cached data must NOT appear; only sheet fallback
        symbols = [r["tradingsymbol"] for r in result]
        self.assertNotIn("STALE", symbols)
        self.assertIn("INFY", symbols)
        self.assertEqual(result[0]["source"], "zerodha")

    @patch("app.routes._enrich_manual_entries_with_ltp")
    @patch("app.routes._fetch_manual_entries")
    @patch("app.routes.portfolio_cache")
    def test_build_stocks_data_broker_online_skips_sheet_zerodha(self, mock_pc, mock_manual, mock_enrich):
        """When account is connected, zerodha-sourced sheet rows for that
        account are skipped and live broker data is used instead."""
        from app.cache import UserPortfolioData
        from app.routes import _build_stocks_data

        mock_pc.get.return_value = UserPortfolioData(
            stocks=[{"tradingsymbol": "INFY", "quantity": 10}],
            connected_accounts={"Z1"},
        )
        mock_manual.side_effect = [
            [
                {
                    "symbol": "INFY",
                    "qty": "5",
                    "avg_price": "1000",
                    "exchange": "NSE",
                    "source": "zerodha",
                    "account": "Z1",
                    "row_number": 2,
                }
            ],
            [],
        ]
        result = _build_stocks_data({"google_id": "g1"})
        # Only live broker entry, sheet zerodha row skipped
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["quantity"], 10)

    @patch("app.routes._fetch_manual_entries", return_value=[])
    @patch("app.routes.portfolio_cache")
    def test_build_mf_data_broker_offline_uses_sheet_fallback(self, mock_pc, mock_manual):
        """When no accounts connected, cached broker MF data is ignored."""
        from app.cache import UserPortfolioData
        from app.routes import _build_mf_data

        mock_pc.get.return_value = UserPortfolioData(
            mf_holdings=[{"fund": "STALE", "tradingsymbol": "STALE"}],
            connected_accounts=set(),
        )
        result = _build_mf_data({"google_id": "g1"})
        self.assertEqual(len(result), 0)

    @patch("app.routes._fetch_manual_entries", return_value=[])
    @patch("app.routes.portfolio_cache")
    def test_build_sips_data_broker_offline_uses_sheet_fallback(self, mock_pc, mock_manual):
        """When no accounts connected, cached broker SIP data is ignored."""
        from app.cache import UserPortfolioData
        from app.routes import _build_sips_data

        mock_pc.get.return_value = UserPortfolioData(
            sips=[{"tradingsymbol": "STALE", "status": "ACTIVE"}],
            connected_accounts=set(),
        )
        result = _build_sips_data({"google_id": "g1"})
        self.assertEqual(len(result), 0)

    @patch("app.routes.manual_ltp_cache")
    def test_enrich_manual_entries_with_ltp(self, mock_cache):
        from app.routes import _enrich_manual_entries_with_ltp

        mock_cache.get.return_value = {"ltp": 1600, "change": 5, "pChange": 0.3}
        entries = [{"tradingsymbol": "INFY", "last_price": 1500, "day_change": 0, "day_change_percentage": 0}]
        _enrich_manual_entries_with_ltp(entries)
        self.assertEqual(entries[0]["last_price"], 1600)

    @patch("app.routes.manual_ltp_cache")
    def test_enrich_manual_entries_no_ltp(self, mock_cache):
        from app.routes import _enrich_manual_entries_with_ltp

        mock_cache.get.return_value = None
        entries = [{"tradingsymbol": "UNKNOWN", "last_price": 100, "day_change": 0, "day_change_percentage": 0}]
        _enrich_manual_entries_with_ltp(entries)
        self.assertEqual(entries[0]["last_price"], 100)  # unchanged

    def test_enrich_manual_entries_empty(self):
        from app.routes import _enrich_manual_entries_with_ltp

        _enrich_manual_entries_with_ltp([])  # should not raise

    @patch("app.api.market_data.MarketDataClient")
    def test_validate_nse_symbol_valid(self, mock_client_cls):
        from app.routes import _validate_nse_symbol

        mock_client_cls.return_value.fetch_stock_quote.return_value = {"ltp": 1500}
        result = _validate_nse_symbol("INFY")
        self.assertIsNotNone(result)
        mock_client_cls.return_value.fetch_stock_quote.assert_called_once_with("INFY")

    @patch("app.api.market_data.MarketDataClient")
    def test_validate_nse_symbol_invalid(self, mock_client_cls):
        from app.routes import _validate_nse_symbol

        mock_client_cls.return_value.fetch_stock_quote.return_value = {"ltp": 0}
        result = _validate_nse_symbol("FAKE")
        self.assertIsNone(result)
        mock_client_cls.return_value.fetch_stock_quote.assert_called_once_with("FAKE")

    @patch("app.api.market_data.MarketDataClient")
    def test_validate_nse_symbol_exception(self, mock_client_cls):
        from app.routes import _validate_nse_symbol

        mock_client_cls.return_value.fetch_stock_quote.side_effect = Exception("err")
        result = _validate_nse_symbol("FAIL")
        self.assertIsNone(result)

    @patch("app.routes._build_stocks_data", return_value=[{"s": 1}])
    def test_build_data_for_type_stocks(self, mock_build):
        from app.routes import _build_data_for_type

        result = _build_data_for_type({"google_id": "g1"}, "stocks")
        self.assertIn("stocks", result)

    def test_build_data_for_type_unknown(self):
        from app.routes import _build_data_for_type

        result = _build_data_for_type({"google_id": "g1"}, "unknown")
        self.assertEqual(result, {})

    @patch("app.routes.user_sheets_cache")
    def test_refresh_single_sheet_cache_gold(self, mock_usc):
        from app.routes import _refresh_single_sheet_cache

        mock_client = Mock()
        mock_client.fetch_sheet_data_until_blank.return_value = [["H"], ["A"]]
        with patch("app.api.google_sheets_client.PhysicalGoldService") as mock_gold_svc:
            mock_gold_svc.return_value._parse_batch_data.return_value = [{"g": 1}]
            _refresh_single_sheet_cache(mock_client, "sid", "g1", "physical_gold")
        mock_usc.put.assert_called_once()

    @patch("app.routes.user_sheets_cache")
    def test_refresh_single_sheet_cache_fd(self, mock_usc):
        from app.routes import _refresh_single_sheet_cache

        mock_client = Mock()
        mock_client.fetch_sheet_data_until_blank.return_value = [["H"], ["A"]]
        with (
            patch("app.api.google_sheets_client.FixedDepositsService") as mock_fd_svc,
            patch("app.api.fixed_deposits.calculate_current_value", return_value=[{"fd": 1}]),
        ):
            mock_fd_svc.return_value._parse_batch_data.return_value = [{"fd": 1}]
            _refresh_single_sheet_cache(mock_client, "sid", "g1", "fixed_deposits")
        mock_usc.put.assert_called_once()

    @patch("app.routes.user_sheets_cache")
    def test_refresh_single_sheet_cache_manual(self, mock_usc):
        from app.routes import _refresh_single_sheet_cache

        mock_client = Mock()
        mock_client.fetch_sheet_data_until_blank.return_value = [
            ["Symbol", "Qty", "AvgPrice", "Exchange", "Account"],
            ["INFY", "10", "1500", "NSE", "Manual"],
        ]
        _refresh_single_sheet_cache(mock_client, "sid", "g1", "stocks")
        mock_usc.put_manual.assert_called_once()

    @patch("app.routes.user_sheets_cache")
    def test_refresh_single_sheet_cache_error(self, mock_usc):
        from app.routes import _refresh_single_sheet_cache

        mock_client = Mock()
        mock_client.fetch_sheet_data_until_blank.side_effect = Exception("fail")
        _refresh_single_sheet_cache(mock_client, "sid", "g1", "stocks")
        mock_usc.invalidate.assert_called_once_with("g1")

    @patch("app.fetchers.user_sheets_cache")
    @patch("app.fetchers.get_google_creds_dict", return_value={"token": "t"})
    def test_prefetch_all_user_sheets_already_cached(self, mock_creds, mock_usc):
        from app.routes import _prefetch_all_user_sheets

        mock_usc.is_fully_cached.return_value = True
        _prefetch_all_user_sheets({"google_id": "g1", "spreadsheet_id": "sid"})
        # Should return early, no batch fetch

    @patch("app.fetchers.user_sheets_cache")
    @patch("app.fetchers.get_google_creds_dict", return_value=None)
    def test_prefetch_no_creds_noop(self, mock_creds, mock_usc):
        from app.routes import _prefetch_all_user_sheets

        _prefetch_all_user_sheets({"google_id": "g1", "spreadsheet_id": "sid"})

    @patch("app.routes._get_google_creds_dict", return_value=None)
    def test_fetch_manual_entries_no_creds(self, mock_creds):
        from app.routes import _fetch_manual_entries

        result = _fetch_manual_entries({"google_id": "g1"}, "stocks")
        self.assertEqual(result, [])

    def test_sync_spreadsheet_id_no_user(self):
        """before_request handler should not error when no user in session."""
        client = app_ui.test_client()
        resp = client.get("/healthz")
        self.assertEqual(resp.status_code, 200)

    @patch("app.firebase_store.get_user", return_value={"spreadsheet_id": "new_sid"})
    def test_sync_spreadsheet_id_fills_missing(self, mock_get_user):
        from app.routes import app_ui

        client = app_ui.test_client()
        with client.session_transaction() as sess:
            sess["user"] = {
                "google_id": "g1",
                "email": "e",
                "name": "N",
                "picture": "",
                "spreadsheet_id": "",
                "google_credentials": {},
            }
            sess["pin_verified"] = True
        from app.services import session_manager

        session_manager.set_pin("g1", "test01")
        # Any request triggers before_request
        resp = client.get("/healthz")
        self.assertEqual(resp.status_code, 200)

    @patch("app.routes.manual_ltp_cache")
    @patch("app.api.market_data.MarketDataClient")
    @patch("app.routes._fetch_manual_entries", return_value=[{"symbol": "INFY"}])
    def test_fetch_uncached_manual_ltps(self, mock_manual, mock_client_cls, mock_cache):
        from app.routes import _fetch_uncached_manual_ltps

        mock_cache.get.return_value = None
        mock_cache.is_negative.return_value = False
        mock_client_cls.return_value.fetch_stock_quotes.return_value = {"INFY": {"ltp": 100}}
        _fetch_uncached_manual_ltps({"google_id": "g1"}, "INFY")


# ---------------------------------------------------------------------------
# Zerodha callback
# ---------------------------------------------------------------------------


class TestZerodhaCallback(unittest.TestCase):
    def setUp(self):
        self.client = app_ui.test_client()
        app_ui.testing = True

    def test_callback_no_token(self):
        resp = self.client.get("/api/callback")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"html", resp.data.lower())

    def test_callback_no_session(self):
        resp = self.client.get("/api/callback?request_token=tok123")
        self.assertEqual(resp.status_code, 200)
        # renders callback_error.html

    @patch("app.routes.portfolio_cache")
    @patch("app.routes.ensure_user_loaded")
    @patch("app.routes.get_user_accounts", return_value=[{"name": "Acc1", "api_key": "k1", "api_secret": "s1"}])
    @patch("app.routes.session_manager")
    def test_callback_success(self, mock_sm, mock_accs, mock_eul, mock_pc):
        mock_sm.get_pin.return_value = "123456"
        mock_sm.is_valid.side_effect = [False, True]  # not valid initially, then valid
        mock_pc.is_fetch_in_progress.return_value = False

        with patch("kiteconnect.KiteConnect") as mock_kite_cls, patch("app.fetchers.run_background_fetch"):
            mock_kite = Mock()
            mock_kite.generate_session.return_value = {"access_token": "tok_abc"}
            mock_kite_cls.return_value = mock_kite

            _inject_user(self.client)
            resp = self.client.get("/api/callback?request_token=tok123")

        self.assertEqual(resp.status_code, 200)  # callback_success.html

    @patch("app.routes.ensure_user_loaded")
    @patch("app.routes.get_user_accounts", return_value=[])
    @patch("app.routes.session_manager")
    def test_callback_no_accounts(self, mock_sm, mock_accs, mock_eul):
        mock_sm.get_pin.return_value = "123456"
        _inject_user(self.client)
        resp = self.client.get("/api/callback?request_token=tok123")
        self.assertEqual(resp.status_code, 200)  # callback_error.html

    @patch("app.routes.session_manager")
    def test_callback_no_pin(self, mock_sm):
        mock_sm.get_pin.return_value = None
        _inject_user(self.client)
        resp = self.client.get("/api/callback?request_token=tok123")
        self.assertEqual(resp.status_code, 200)  # callback_error.html


# ---------------------------------------------------------------------------
# Prefetch, batch-fetch, refresh, portfolio_page, etc.
# ---------------------------------------------------------------------------


class TestRoutePrefetchAndBatchFetch(unittest.TestCase):
    """Cover _prefetch_all_user_sheets full path and related helpers."""

    def setUp(self):
        self.client = app_ui.test_client()
        app_ui.testing = True

    @patch("app.fetchers.user_sheets_cache")
    @patch("app.fetchers.get_google_creds_dict", return_value={"token": "t"})
    @patch("app.api.google_auth.credentials_from_dict")
    @patch("app.api.google_sheets_client.GoogleSheetsClient")
    @patch("app.api.google_sheets_client.PhysicalGoldService")
    @patch("app.api.google_sheets_client.FixedDepositsService")
    @patch("app.api.fixed_deposits.calculate_current_value", return_value=[])
    def test_prefetch_full_batch(
        self, mock_calc, mock_fd_svc, mock_gold_svc, mock_gsc, mock_creds, mock_get_creds, mock_usc
    ):
        from app.routes import _prefetch_all_user_sheets

        mock_usc.is_fully_cached.return_value = False
        mock_client = Mock()
        mock_gsc.return_value = mock_client
        mock_client.batch_fetch_sheet_data_until_blank.return_value = {
            "Gold": [["H"], ["r1"]],
            "FixedDeposits": [["H"], ["r1"]],
            "Stocks": [["Symbol", "Qty", "AvgPrice", "Exchange", "Account"], ["INFY", "10", "1500", "NSE", "Manual"]],
            "ETFs": [],
            "MutualFunds": [],
            "SIPs": [],
        }
        mock_gold_svc.return_value._parse_batch_data.return_value = [{"g": 1}]
        mock_fd_svc.return_value._parse_batch_data.return_value = [{"fd": 1}]

        _prefetch_all_user_sheets({"google_id": "g1234567", "spreadsheet_id": "sid"})
        mock_usc.put_all.assert_called_once()

    @patch("app.fetchers.user_sheets_cache")
    @patch("app.fetchers.get_google_creds_dict", return_value={"token": "t"})
    @patch("app.api.google_auth.credentials_from_dict", side_effect=Exception("boom"))
    def test_prefetch_exception(self, mock_creds, mock_get_creds, mock_usc):
        from app.routes import _prefetch_all_user_sheets

        mock_usc.is_fully_cached.return_value = False
        _prefetch_all_user_sheets({"google_id": "g1234567", "spreadsheet_id": "sid"})
        # Should not raise

    @patch("app.fetchers.user_sheets_cache")
    @patch("app.fetchers.get_google_creds_dict", return_value={"token": "t"})
    @patch(
        "app.api.google_auth.credentials_from_dict", side_effect=type("RefreshError", (Exception,), {})("creds expired")
    )
    def test_prefetch_refresh_error_logs_warning(self, mock_creds, mock_get_creds, mock_usc):
        """RefreshError is caught gracefully with a warning, not a full traceback."""
        from app.routes import _prefetch_all_user_sheets

        mock_usc.is_fully_cached.return_value = False
        # Should not raise
        _prefetch_all_user_sheets({"google_id": "g1234567", "spreadsheet_id": "sid"})
        mock_usc.put_all.assert_not_called()

    def test_is_google_auth_error(self):
        from app.routes import _is_google_auth_error

        self.assertTrue(_is_google_auth_error(type("RefreshError", (Exception,), {})("bad")))
        self.assertTrue(_is_google_auth_error(type("InvalidGrantError", (Exception,), {})("revoked")))
        self.assertFalse(_is_google_auth_error(ValueError("nope")))

    @patch("app.routes._current_user", return_value=None)
    def test_get_google_creds_dict_none_user(self, mock_cu):
        from app.routes import _get_google_creds_dict

        with app_ui.test_request_context():
            result = _get_google_creds_dict(None)
            self.assertIsNone(result)

    def test_get_google_creds_dict_dict_value(self):
        from app.routes import _get_google_creds_dict

        user = {"google_credentials": {"token": "t"}}
        result = _get_google_creds_dict(user)
        self.assertEqual(result, {"token": "t"})

    @patch("app.firebase_store.get_google_credentials", return_value={"token": "stored"})
    def test_get_google_creds_dict_fallback(self, mock_get):
        from app.routes import _get_google_creds_dict

        user = {"google_id": "g1", "google_credentials": "encrypted_str"}
        result = _get_google_creds_dict(user)
        self.assertEqual(result, {"token": "stored"})

    @patch("app.routes.user_sheets_cache")
    def test_fetch_user_sheets_data_cached(self, mock_usc):
        from app.routes import _fetch_user_sheets_data

        cached_entry = Mock(physical_gold=[{"g": 1}], fixed_deposits=[{"fd": 1}])
        mock_usc.get.return_value = cached_entry
        user = {"google_id": "g1", "spreadsheet_id": "sid", "google_credentials": {"token": "t"}}
        gold, fds = _fetch_user_sheets_data(user)
        self.assertEqual(gold, [{"g": 1}])

    @patch("app.routes.user_sheets_cache")
    def test_fetch_user_sheets_data_no_cache(self, mock_usc):
        from app.routes import _fetch_user_sheets_data

        mock_usc.get.return_value = None
        gold, fds = _fetch_user_sheets_data({"google_id": "g1"})
        self.assertIsNone(gold)
        self.assertIsNone(fds)

    def test_fetch_lock_eviction(self):
        from app.fetchers import _get_user_fetch_lock, _user_fetch_locks

        _user_fetch_locks.clear()
        for i in range(600):
            _get_user_fetch_lock(f"user_{i}")
        self.assertLess(len(_user_fetch_locks), 600)


class TestRefreshRoute(unittest.TestCase):
    def setUp(self):
        self.client = app_ui.test_client()
        app_ui.testing = True

    @patch("app.fetchers.run_background_fetch")
    @patch("app.fetchers.collect_manual_symbols", return_value=["INFY"])
    @patch("app.routes.get_authenticated_accounts", return_value=[])
    @patch("app.routes.user_sheets_cache")
    @patch("app.routes.manual_ltp_cache")
    @patch("app.routes.portfolio_cache")
    @patch("app.routes.ensure_user_loaded")
    def test_refresh_success(self, mock_eul, mock_pc, mock_ltp, mock_usc, mock_auth, mock_collect, mock_bg):
        mock_pc.is_fetch_in_progress.return_value = False
        _inject_user(self.client)
        resp = self.client.post("/api/refresh", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 202)

    @patch("app.routes.portfolio_cache")
    def test_refresh_already_in_progress(self, mock_pc):
        mock_pc.is_fetch_in_progress.return_value = True
        _inject_user(self.client)
        resp = self.client.post("/api/refresh", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 409)


class TestPortfolioPage(unittest.TestCase):
    def setUp(self):
        self.client = app_ui.test_client()
        app_ui.testing = True

    def test_unauthenticated_landing(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)

    @patch("app.firebase_store.has_pin", return_value=True)
    @patch("app.routes.user_sheets_cache")
    @patch("app.routes.ensure_user_loaded")
    def test_authenticated_dashboard(self, mock_eul, mock_usc, mock_has_pin):
        mock_usc.is_fully_cached.return_value = False
        _inject_user(self.client)
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)

    @patch("app.firebase_store.has_pin", return_value=True)
    @patch("app.routes._build_status_response", return_value={})
    @patch("app.routes._build_fd_data", return_value=[])
    @patch("app.routes._build_gold_data", return_value=[])
    @patch("app.routes._build_sips_data", return_value=[])
    @patch("app.routes._build_mf_data", return_value=[])
    @patch("app.routes._build_stocks_data", return_value=[])
    @patch("app.routes.user_sheets_cache")
    @patch("app.routes.ensure_user_loaded")
    def test_authenticated_with_inlined_data(
        self, mock_eul, mock_usc, mock_stocks, mock_mf, mock_sips, mock_gold, mock_fd, mock_status, mock_has_pin
    ):
        mock_usc.is_fully_cached.return_value = True
        _inject_user(self.client)
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)


class TestPinVerifyRoute(unittest.TestCase):
    def setUp(self):
        self.client = app_ui.test_client()
        app_ui.testing = True

    @patch("app.routes.ensure_user_loaded")
    @patch("app.routes.verify_user_pin", return_value=True)
    @patch("app.routes.pin_rate_limiter")
    @patch("app.firebase_store.has_pin", return_value=True)
    @patch("app.firebase_store.store_pin_check")
    def test_pin_verify_success(self, mock_store, mock_has, mock_limiter, mock_verify, mock_eul):
        mock_limiter.check.return_value = (True, None)
        _inject_user(self.client)
        resp = self.client.post(
            "/api/pin/verify",
            headers={**_APP_HEADERS, "Content-Type": "application/json"},
            data=json.dumps({"pin": "abc123"}),
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["status"], "verified")

    @patch("app.routes.verify_user_pin", return_value=False)
    @patch("app.routes.pin_rate_limiter")
    @patch("app.firebase_store.store_pin_check")
    def test_pin_verify_wrong_pin(self, mock_store, mock_limiter, mock_verify):
        mock_limiter.check.return_value = (True, None)
        mock_limiter.record_failure.return_value = (1, None)
        _inject_user(self.client)
        resp = self.client.post(
            "/api/pin/verify",
            headers={**_APP_HEADERS, "Content-Type": "application/json"},
            data=json.dumps({"pin": "wrong1"}),
        )
        self.assertEqual(resp.status_code, 401)


class TestPinResetRoute(unittest.TestCase):
    def setUp(self):
        self.client = app_ui.test_client()
        app_ui.testing = True

    @patch("app.routes.session_manager")
    @patch("app.routes.portfolio_cache")
    @patch("app.routes.user_sheets_cache")
    @patch("app.routes.reset_zerodha_data")
    def test_pin_reset(self, mock_reset, mock_usc, mock_pc, mock_sm):
        _inject_user(self.client)
        resp = self.client.post(
            "/api/pin/reset",
            headers={**_APP_HEADERS, "Content-Type": "application/json"},
            data=json.dumps({"pin": "abc123"}),
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["status"], "reset_complete")


class TestNifty50Page(unittest.TestCase):
    def setUp(self):
        self.client = app_ui.test_client()
        app_ui.testing = True

    def test_nifty50_page(self):
        resp = self.client.get("/nifty50")
        self.assertEqual(resp.status_code, 401)


class TestNifty50DataRoute(unittest.TestCase):
    def setUp(self):
        self.client = app_ui.test_client()
        app_ui.testing = True

    @patch("app.routes.market_cache")
    def test_nifty50_data(self, mock_mc):
        mock_mc.nifty50 = [{"symbol": "INFY", "ltp": 1500}]
        resp = self.client.get("/api/nifty50_data", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 200)

    @patch("app.routes.market_cache")
    def test_nifty50_data_empty(self, mock_mc):
        mock_mc.nifty50 = []
        resp = self.client.get("/api/nifty50_data", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 200)


class TestStocksDataRoute(unittest.TestCase):
    def setUp(self):
        self.client = app_ui.test_client()
        app_ui.testing = True

    @patch("app.routes._build_stocks_data", return_value=[{"s": 1}])
    def test_stocks_data(self, mock_build):
        _inject_user(self.client)
        resp = self.client.get("/api/stocks_data", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 200)


class TestMFDataRoute(unittest.TestCase):
    def setUp(self):
        self.client = app_ui.test_client()
        app_ui.testing = True

    @patch("app.routes._build_mf_data", return_value=[{"f": 1}])
    def test_mf_data(self, mock_build):
        _inject_user(self.client)
        resp = self.client.get("/api/mf_holdings_data", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 200)


class TestSIPsDataRoute(unittest.TestCase):
    def setUp(self):
        self.client = app_ui.test_client()
        app_ui.testing = True

    @patch("app.routes._build_sips_data", return_value=[{"s": 1}])
    def test_sips_data(self, mock_build):
        _inject_user(self.client)
        resp = self.client.get("/api/sips_data", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 200)


class TestRemoveZerodha(unittest.TestCase):
    def setUp(self):
        self.client = app_ui.test_client()
        app_ui.testing = True

    @patch("app.broker_sync.delete_account_from_sheets")
    @patch("app.routes.session_manager")
    @patch("app.firebase_store.remove_zerodha_account")
    def test_remove(self, mock_remove, mock_sm, mock_delete_sheets):
        mock_sm.get_pin.return_value = "123456"
        _inject_user(self.client)
        resp = self.client.delete("/api/settings/zerodha/TestAcc", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 200)
        mock_delete_sheets.assert_called_once_with("test123", "TestAcc")

    @patch("app.firebase_store.remove_zerodha_account", side_effect=ValueError("not found"))
    @patch("app.routes.session_manager")
    def test_remove_not_found(self, mock_sm, mock_remove):
        mock_sm.get_pin.return_value = "123456"
        _inject_user(self.client)
        resp = self.client.delete("/api/settings/zerodha/TestAcc", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 404)


class TestSettingsGetRoute(unittest.TestCase):
    def setUp(self):
        self.client = app_ui.test_client()
        app_ui.testing = True

    @patch("kiteconnect.KiteConnect")
    @patch("app.routes.session_manager")
    @patch("app.firebase_store.get_zerodha_accounts")
    def test_settings_with_unauthenticated_accounts(self, mock_accs, mock_sm, mock_kite_cls):
        mock_accs.return_value = [{"name": "Acc1", "api_key": "k1"}]
        mock_sm.get_pin.return_value = "123456"
        mock_sm.is_valid.return_value = False
        mock_sm.get_validity.return_value = {"Acc1": False}
        mock_kite_cls.return_value.login_url.return_value = "https://kite.zerodha.com"
        _inject_user(self.client)
        resp = self.client.get("/api/settings", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertIn("login_urls", data)

    @patch("kiteconnect.KiteConnect")
    @patch("app.routes.session_manager")
    @patch("app.firebase_store.get_zerodha_accounts")
    def test_settings_login_url_exception(self, mock_accs, mock_sm, mock_kite_cls):
        """Cover the try/except pass inside settings login_urls loop."""
        mock_accs.return_value = [{"name": "Acc1", "api_key": "k1"}]
        mock_sm.get_pin.return_value = "123456"
        mock_sm.is_valid.return_value = False
        mock_sm.get_validity.return_value = {"Acc1": False}
        mock_kite_cls.return_value.login_url.side_effect = Exception("nope")
        _inject_user(self.client)
        resp = self.client.get("/api/settings", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["login_urls"], {})


# ---------------------------------------------------------------------------
# _fetch_manual_entries, _enrich_manual_entries_with_ltp, helpers
# ---------------------------------------------------------------------------


class TestFetchManualEntries(unittest.TestCase):
    def setUp(self):
        self.client = app_ui.test_client()
        app_ui.testing = True

    @patch("app.routes.user_sheets_cache")
    def test_fetch_manual_entries_unknown_type(self, mock_usc):
        from app.routes import _fetch_manual_entries

        mock_usc.get_manual.return_value = None
        result = _fetch_manual_entries({"google_id": "g1"}, "nonexistent")
        self.assertEqual(result, [])

    @patch("app.routes.user_sheets_cache")
    def test_fetch_manual_entries_no_cache(self, mock_usc):
        from app.routes import _fetch_manual_entries

        mock_usc.get_manual.return_value = None
        result = _fetch_manual_entries({"google_id": "g1", "spreadsheet_id": "sid"}, "stocks")
        self.assertEqual(result, [])

    @patch("app.routes.user_sheets_cache")
    def test_fetch_manual_entries_cached(self, mock_usc):
        from app.routes import _fetch_manual_entries

        mock_usc.get_manual.return_value = [{"symbol": "INFY"}]
        result = _fetch_manual_entries({"google_id": "g1", "spreadsheet_id": "sid"}, "stocks")
        self.assertEqual(result, [{"symbol": "INFY"}])


class TestEnrichManualEntriesWithLtp(unittest.TestCase):
    @patch("app.routes.manual_ltp_cache")
    def test_enrich_with_cached_ltp(self, mock_cache):
        from app.routes import _enrich_manual_entries_with_ltp

        mock_cache.get.return_value = {"ltp": 1500, "change": 10, "pChange": 0.67}
        entries = [{"tradingsymbol": "INFY", "last_price": 0, "day_change": 0, "day_change_percentage": 0}]
        _enrich_manual_entries_with_ltp(entries)
        self.assertEqual(entries[0]["last_price"], 1500)

    @patch("app.routes.manual_ltp_cache")
    def test_enrich_no_symbols(self, mock_cache):
        from app.routes import _enrich_manual_entries_with_ltp

        entries = [{"tradingsymbol": "", "last_price": 0}]
        _enrich_manual_entries_with_ltp(entries)
        self.assertEqual(entries[0]["last_price"], 0)

    @patch("app.routes.manual_ltp_cache")
    def test_enrich_all_uncached(self, mock_cache):
        from app.routes import _enrich_manual_entries_with_ltp

        mock_cache.get.return_value = None
        entries = [{"tradingsymbol": "XYZ", "last_price": 0}]
        _enrich_manual_entries_with_ltp(entries)
        self.assertEqual(entries[0]["last_price"], 0)


class TestRefreshSingleSheetCache(unittest.TestCase):
    @patch("app.routes.user_sheets_cache")
    @patch("app.api.google_sheets_client.PhysicalGoldService")
    def test_refresh_physical_gold(self, mock_gold_svc, mock_usc):
        from app.routes import _refresh_single_sheet_cache

        mock_client = Mock()
        mock_client.fetch_sheet_data_until_blank.return_value = [["H"], ["r1"]]
        mock_gold_svc.return_value._parse_batch_data.return_value = [{"g": 1}]
        _refresh_single_sheet_cache(mock_client, "sid", "g1234567", "physical_gold")
        mock_usc.put.assert_called_once()

    @patch("app.routes.user_sheets_cache")
    @patch("app.api.google_sheets_client.FixedDepositsService")
    @patch("app.api.fixed_deposits.calculate_current_value", return_value=[])
    def test_refresh_fixed_deposits(self, mock_calc, mock_fd_svc, mock_usc):
        from app.routes import _refresh_single_sheet_cache

        mock_client = Mock()
        mock_client.fetch_sheet_data_until_blank.return_value = [["H"], ["r1"]]
        mock_fd_svc.return_value._parse_batch_data.return_value = [{"fd": 1}]
        _refresh_single_sheet_cache(mock_client, "sid", "g1234567", "fixed_deposits")
        mock_usc.put.assert_called_once()

    @patch("app.routes.user_sheets_cache")
    def test_refresh_manual_type(self, mock_usc):
        from app.routes import _refresh_single_sheet_cache

        mock_client = Mock()
        mock_client.fetch_sheet_data_until_blank.return_value = [
            ["Symbol", "Qty", "AvgPrice", "Exchange", "Account"],
            ["INFY", "10", "1500", "NSE", "Manual"],
        ]
        _refresh_single_sheet_cache(mock_client, "sid", "g1234567", "stocks")
        mock_usc.put_manual.assert_called_once()

    @patch("app.routes.user_sheets_cache")
    def test_refresh_exception(self, mock_usc):
        from app.routes import _refresh_single_sheet_cache

        mock_client = Mock()
        mock_client.fetch_sheet_data_until_blank.side_effect = Exception("fail")
        _refresh_single_sheet_cache(mock_client, "sid", "g1234567", "stocks")
        mock_usc.invalidate.assert_called_once_with("g1234567")

    def test_refresh_unknown_type(self):
        from app.routes import _refresh_single_sheet_cache

        _refresh_single_sheet_cache(Mock(), "sid", "g1234567", "unknown")
        # Should return early


class TestBuildDataForType(unittest.TestCase):
    @patch("app.routes._build_stocks_data", return_value=[{"s": 1}])
    def test_build_data_for_stocks(self, mock_build):
        from app.routes import _build_data_for_type

        result = _build_data_for_type({"google_id": "g1"}, "stocks")
        self.assertEqual(result, {"stocks": [{"s": 1}]})

    def test_build_data_unknown_type(self):
        from app.routes import _build_data_for_type

        result = _build_data_for_type({"google_id": "g1"}, "nonexistent")
        self.assertEqual(result, {})

    @patch("app.routes._build_stocks_data", side_effect=Exception("boom"))
    def test_build_data_exception(self, mock_build):
        from app.routes import _build_data_for_type

        result = _build_data_for_type({"google_id": "g1"}, "stocks")
        self.assertEqual(result, {})


# ---------------------------------------------------------------------------
# CRUD routes: sheets_list, sheets_add, sheets_update, sheets_delete
# ---------------------------------------------------------------------------


class TestSheetsListRoute(unittest.TestCase):
    def setUp(self):
        self.client = app_ui.test_client()
        app_ui.testing = True

    @patch("app.routes._get_sheets_client")
    def test_list_unknown_type(self, mock_gsc):
        _inject_user(self.client)
        resp = self.client.get("/api/sheets/nonexistent", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 400)

    @patch("app.routes._get_sheets_client")
    def test_list_no_creds(self, mock_gsc):
        mock_gsc.return_value = (None, None, "Google credentials not available")
        _inject_user(self.client)
        resp = self.client.get("/api/sheets/stocks", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 400)

    @patch("app.routes._get_sheets_client")
    def test_list_success(self, mock_gsc):
        mock_client = Mock()
        mock_client.fetch_sheet_data_until_blank.return_value = [
            ["Symbol", "Qty", "AvgPrice", "Exchange", "Account"],
            ["INFY", "10", "1500", "NSE", "Manual"],
        ]
        mock_gsc.return_value = (mock_client, "sid", None)
        _inject_user(self.client)
        resp = self.client.get("/api/sheets/stocks", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["symbol"], "INFY")

    @patch("app.routes._get_sheets_client")
    def test_list_empty(self, mock_gsc):
        mock_client = Mock()
        mock_client.fetch_sheet_data_until_blank.return_value = []
        mock_gsc.return_value = (mock_client, "sid", None)
        _inject_user(self.client)
        resp = self.client.get("/api/sheets/stocks", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data, [])

    @patch("app.routes._get_sheets_client")
    def test_list_exception(self, mock_gsc):
        mock_client = Mock()
        mock_client.ensure_sheet_tab.side_effect = Exception("api error")
        mock_gsc.return_value = (mock_client, "sid", None)
        _inject_user(self.client)
        resp = self.client.get("/api/sheets/stocks", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 500)


class TestSheetsAddRoute(unittest.TestCase):
    def setUp(self):
        self.client = app_ui.test_client()
        app_ui.testing = True

    @patch("app.routes._build_data_for_type", return_value={})
    @patch("app.routes._refresh_single_sheet_cache")
    @patch("app.routes._get_sheets_client")
    def test_add_success(self, mock_gsc, mock_refresh, mock_build):
        mock_client = Mock()
        mock_client.append_row.return_value = 5
        mock_gsc.return_value = (mock_client, "sid", None)
        _inject_user(self.client)
        resp = self.client.post(
            "/api/sheets/mutual_funds",
            headers={**_APP_HEADERS, "Content-Type": "application/json"},
            data=json.dumps({"fund": "HDFC", "qty": "10", "avg_nav": "100"}),
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["status"], "added")

    @patch("app.routes._validate_nse_symbol", return_value=None)
    @patch("app.routes._get_sheets_client")
    def test_add_invalid_nse_symbol(self, mock_gsc, mock_validate):
        mock_gsc.return_value = (Mock(), "sid", None)
        _inject_user(self.client)
        resp = self.client.post(
            "/api/sheets/stocks",
            headers={**_APP_HEADERS, "Content-Type": "application/json"},
            data=json.dumps({"symbol": "FAKE", "qty": "10"}),
        )
        self.assertEqual(resp.status_code, 400)

    @patch("app.routes._validate_nse_symbol", return_value={"ltp": 1500})
    @patch("app.routes._fetch_uncached_manual_ltps")
    @patch("app.routes._build_data_for_type", return_value={"stocks": []})
    @patch("app.routes._refresh_single_sheet_cache")
    @patch("app.routes._get_sheets_client")
    def test_add_stock_with_ltp(self, mock_gsc, mock_refresh, mock_build, mock_fetch_ltps, mock_validate):
        mock_client = Mock()
        mock_client.append_row.return_value = 5
        mock_gsc.return_value = (mock_client, "sid", None)
        _inject_user(self.client)
        resp = self.client.post(
            "/api/sheets/stocks",
            headers={**_APP_HEADERS, "Content-Type": "application/json"},
            data=json.dumps(
                {"symbol": "INFY", "qty": "10", "avg_price": "1500", "exchange": "NSE", "account": "Manual"}
            ),
        )
        self.assertEqual(resp.status_code, 200)

    @patch("app.routes._get_sheets_client")
    def test_add_exception(self, mock_gsc):
        mock_client = Mock()
        mock_client.ensure_sheet_tab.side_effect = Exception("api error")
        mock_gsc.return_value = (mock_client, "sid", None)
        _inject_user(self.client)
        resp = self.client.post(
            "/api/sheets/stocks",
            headers={**_APP_HEADERS, "Content-Type": "application/json"},
            data=json.dumps({"symbol": "", "qty": "10"}),
        )
        self.assertEqual(resp.status_code, 500)

    def test_add_unknown_type(self):
        """Line 1518: sheets_add with unknown sheet type."""
        _inject_user(self.client)
        resp = self.client.post(
            "/api/sheets/nonexistent",
            headers={**_APP_HEADERS, "Content-Type": "application/json"},
            data=json.dumps({"symbol": "X"}),
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Unknown sheet type", json.loads(resp.data)["error"])

    @patch("app.routes._get_sheets_client")
    def test_add_client_error(self, mock_gsc):
        """Line 1522: sheets_add when _get_sheets_client returns error."""
        mock_gsc.return_value = (None, None, "Google credentials not available")
        _inject_user(self.client)
        resp = self.client.post(
            "/api/sheets/stocks",
            headers={**_APP_HEADERS, "Content-Type": "application/json"},
            data=json.dumps({"symbol": "INFY"}),
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Google credentials", json.loads(resp.data)["error"])

    @patch("app.routes._build_data_for_type", return_value={})
    @patch("app.routes._refresh_single_sheet_cache")
    @patch("app.routes._get_sheets_client")
    def test_update_success(self, mock_gsc, mock_refresh, mock_build):
        mock_client = Mock()
        mock_gsc.return_value = (mock_client, "sid", None)
        _inject_user(self.client)
        resp = self.client.put(
            "/api/sheets/mutual_funds/3",
            headers={**_APP_HEADERS, "Content-Type": "application/json"},
            data=json.dumps({"fund": "HDFC", "qty": "20", "avg_nav": "100"}),
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["status"], "updated")

    @patch("app.routes._get_sheets_client")
    def test_update_header_row(self, mock_gsc):
        mock_gsc.return_value = (Mock(), "sid", None)
        _inject_user(self.client)
        resp = self.client.put(
            "/api/sheets/stocks/1",
            headers={**_APP_HEADERS, "Content-Type": "application/json"},
            data=json.dumps({"symbol": "INFY"}),
        )
        self.assertEqual(resp.status_code, 400)

    @patch("app.routes._validate_nse_symbol", return_value={"ltp": 1500})
    @patch("app.routes._build_data_for_type", return_value={"stocks": []})
    @patch("app.routes._refresh_single_sheet_cache")
    @patch("app.routes._get_sheets_client")
    def test_update_stock_with_validation(self, mock_gsc, mock_refresh, mock_build, mock_validate):
        mock_client = Mock()
        mock_gsc.return_value = (mock_client, "sid", None)
        _inject_user(self.client)
        resp = self.client.put(
            "/api/sheets/stocks/3",
            headers={**_APP_HEADERS, "Content-Type": "application/json"},
            data=json.dumps({"symbol": "INFY", "qty": "10"}),
        )
        self.assertEqual(resp.status_code, 200)

    @patch("app.routes._get_sheets_client")
    def test_update_exception(self, mock_gsc):
        mock_client = Mock()
        mock_client.update_row.side_effect = Exception("api err")
        mock_gsc.return_value = (mock_client, "sid", None)
        _inject_user(self.client)
        resp = self.client.put(
            "/api/sheets/mutual_funds/3",
            headers={**_APP_HEADERS, "Content-Type": "application/json"},
            data=json.dumps({"fund": "HDFC"}),
        )
        self.assertEqual(resp.status_code, 500)

    def test_update_unknown_type(self):
        """Line 1567: sheets_update with unknown sheet type."""
        _inject_user(self.client)
        resp = self.client.put(
            "/api/sheets/nonexistent/3",
            headers={**_APP_HEADERS, "Content-Type": "application/json"},
            data=json.dumps({"symbol": "X"}),
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Unknown sheet type", json.loads(resp.data)["error"])

    @patch("app.routes._get_sheets_client")
    def test_update_client_error(self, mock_gsc):
        """Line 1574: sheets_update when _get_sheets_client returns error."""
        mock_gsc.return_value = (None, None, "No spreadsheet linked")
        _inject_user(self.client)
        resp = self.client.put(
            "/api/sheets/stocks/3",
            headers={**_APP_HEADERS, "Content-Type": "application/json"},
            data=json.dumps({"symbol": "INFY"}),
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("No spreadsheet", json.loads(resp.data)["error"])


class TestSheetsDeleteRoute(unittest.TestCase):
    def setUp(self):
        self.client = app_ui.test_client()
        app_ui.testing = True

    @patch("app.routes._build_data_for_type", return_value={})
    @patch("app.routes._refresh_single_sheet_cache")
    @patch("app.routes._get_sheets_client")
    def test_delete_success(self, mock_gsc, mock_refresh, mock_build):
        mock_client = Mock()
        mock_gsc.return_value = (mock_client, "sid", None)
        _inject_user(self.client)
        resp = self.client.delete("/api/sheets/stocks/3", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["status"], "deleted")

    @patch("app.routes._get_sheets_client")
    def test_delete_header_row(self, mock_gsc):
        mock_gsc.return_value = (Mock(), "sid", None)
        _inject_user(self.client)
        resp = self.client.delete("/api/sheets/stocks/1", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 400)

    @patch("app.routes._get_sheets_client")
    def test_delete_exception(self, mock_gsc):
        mock_client = Mock()
        mock_client.delete_row.side_effect = Exception("api err")
        mock_gsc.return_value = (mock_client, "sid", None)
        _inject_user(self.client)
        resp = self.client.delete("/api/sheets/stocks/3", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 500)

    @patch("app.routes._get_sheets_client")
    def test_delete_unknown_type(self, mock_gsc):
        _inject_user(self.client)
        resp = self.client.delete("/api/sheets/nonexistent/3", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 400)

    @patch("app.routes._get_sheets_client")
    def test_delete_client_error(self, mock_gsc):
        """Line 1619: sheets_delete when _get_sheets_client returns error."""
        mock_gsc.return_value = (None, None, "Google credentials not available")
        _inject_user(self.client)
        resp = self.client.delete("/api/sheets/stocks/3", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Google credentials", json.loads(resp.data)["error"])


# ---------------------------------------------------------------------------
# _validate_nse_symbol, _fetch_uncached_manual_ltps
# ---------------------------------------------------------------------------


class TestValidateNseSymbol(unittest.TestCase):
    @patch("app.api.market_data.MarketDataClient")
    def test_valid_symbol(self, mock_mdc):
        from app.routes import _validate_nse_symbol

        mock_inst = mock_mdc.return_value
        mock_inst.fetch_stock_quote.return_value = {"ltp": 1500}
        result = _validate_nse_symbol("INFY")
        self.assertEqual(result, {"ltp": 1500})
        mock_inst.fetch_stock_quote.assert_called_once_with("INFY")

    @patch("app.api.market_data.MarketDataClient")
    def test_invalid_symbol(self, mock_mdc):
        from app.routes import _validate_nse_symbol

        mock_inst = mock_mdc.return_value
        mock_inst.fetch_stock_quote.return_value = None
        result = _validate_nse_symbol("FAKE")
        self.assertIsNone(result)

    @patch("app.api.market_data.MarketDataClient", side_effect=Exception("err"))
    def test_exception(self, mock_mdc):
        from app.routes import _validate_nse_symbol

        result = _validate_nse_symbol("FAIL")
        self.assertIsNone(result)


class TestFetchUncachedManualLtps(unittest.TestCase):
    @patch("app.api.market_data.MarketDataClient")
    @patch("app.routes.manual_ltp_cache")
    @patch("app.routes._fetch_manual_entries", return_value=[{"symbol": "INFY"}])
    def test_fetch_and_cache(self, mock_entries, mock_cache, mock_mdc):
        from app.routes import _fetch_uncached_manual_ltps

        mock_cache.get.return_value = None
        mock_cache.is_negative.return_value = False
        mock_mdc.return_value.fetch_stock_quotes.return_value = {"INFY": {"ltp": 1500}}
        _fetch_uncached_manual_ltps({"google_id": "g1", "spreadsheet_id": "sid"}, "TCS")
        mock_cache.put_batch.assert_called()

    @patch("app.routes.manual_ltp_cache")
    @patch("app.routes._fetch_manual_entries", return_value=[])
    def test_nothing_to_fetch(self, mock_entries, mock_cache):
        from app.routes import _fetch_uncached_manual_ltps

        mock_cache.get.return_value = {"ltp": 100}
        _fetch_uncached_manual_ltps({"google_id": "g1", "spreadsheet_id": "sid"})


class TestZerodhaCallbackEdgeCases(unittest.TestCase):
    def setUp(self):
        self.client = app_ui.test_client()
        app_ui.testing = True

    @patch("app.routes.get_user_accounts")
    @patch("app.routes.ensure_user_loaded")
    @patch("app.routes.session_manager")
    def test_callback_already_valid_account(self, mock_sm, mock_eul, mock_accs):
        """Cover the 'skipping already-valid account' debug branch."""
        mock_sm.get_pin.return_value = "123456"
        mock_sm.is_valid.return_value = True
        mock_accs.return_value = [{"name": "Acc1", "api_key": "k1", "api_secret": "s1"}]
        _inject_user(self.client)
        resp = self.client.get("/api/callback?request_token=tok123")
        # No account authenticated → renders error
        self.assertEqual(resp.status_code, 200)

    @patch("kiteconnect.KiteConnect")
    @patch("app.routes.get_user_accounts")
    @patch("app.routes.ensure_user_loaded")
    @patch("app.routes.session_manager")
    def test_callback_session_generation_exception(self, mock_sm, mock_eul, mock_accs, mock_kite):
        """Cover the except branch when kite.generate_session fails."""
        mock_sm.get_pin.return_value = "123456"
        mock_sm.is_valid.return_value = False
        mock_accs.return_value = [{"name": "Acc1", "api_key": "k1", "api_secret": "s1"}]
        mock_kite.return_value.generate_session.side_effect = Exception("network error")
        _inject_user(self.client)
        resp = self.client.get("/api/callback?request_token=tok123")
        self.assertEqual(resp.status_code, 200)  # callback_error.html


class TestGoogleCallbackEdgeCases(unittest.TestCase):
    def setUp(self):
        self.client = app_ui.test_client()
        app_ui.testing = True

    @patch("threading.Thread")
    @patch("app.firebase_store.update_spreadsheet_id")
    @patch("app.firebase_store.upsert_user")
    @patch("app.firebase_store.get_user", return_value=None)
    @patch("app.api.google_auth.credentials_to_dict", return_value={"token": "t"})
    @patch(
        "app.api.google_auth.get_user_info",
        return_value={"id": "g1234567890", "email": "test@example.com", "name": "Test", "picture": "http://pic.jpg"},
    )
    @patch("app.api.google_auth.exchange_code_for_credentials")
    def test_callback_no_spreadsheet_creates_bg(
        self, mock_exchange, mock_info, mock_creds_dict, mock_get_user, mock_upsert, mock_update_sid, mock_thread
    ):
        """Cover the background sheet creation branch (no spreadsheet_id)."""
        mock_exchange.return_value = Mock()
        resp = self.client.get("/api/auth/google/callback?code=abc123")
        mock_thread.assert_called_once()
        self.assertEqual(resp.status_code, 302)


class TestPortfolioPageEdgeCases(unittest.TestCase):
    def setUp(self):
        self.client = app_ui.test_client()
        app_ui.testing = True

    @patch("app.firebase_store.has_pin", return_value=True)
    @patch("app.routes._build_status_response", side_effect=Exception("boom"))
    @patch("app.routes.user_sheets_cache")
    @patch("app.routes.ensure_user_loaded")
    def test_initial_data_exception(self, mock_eul, mock_usc, mock_status, mock_has_pin):
        """Cover the except branch when building initial_data fails."""
        mock_usc.is_fully_cached.return_value = True
        _inject_user(self.client)
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)


# ---------------------------------------------------------------------------
# Cover remaining uncovered lines
# ---------------------------------------------------------------------------


class TestFetchUserSheetsDataCacheMiss(unittest.TestCase):
    """Cache miss returns None, None."""

    @patch("app.routes.user_sheets_cache")
    def test_cache_miss_returns_none(self, mock_usc):
        from app.routes import _fetch_user_sheets_data

        mock_usc.get.return_value = None  # cache miss
        user = {"google_id": "g1", "spreadsheet_id": "sid", "google_credentials": {"token": "t"}}
        gold, fds = _fetch_user_sheets_data(user)
        self.assertIsNone(gold)
        self.assertIsNone(fds)


class TestPrefetchDoubleCheckAfterLock(unittest.TestCase):
    """Line 284: double-check returns early inside lock."""

    @patch("app.fetchers.user_sheets_cache")
    @patch("app.fetchers.get_google_creds_dict", return_value={"token": "t"})
    def test_lock_double_check_returns_early(self, mock_creds, mock_usc):
        from app.routes import _prefetch_all_user_sheets

        # First call: not cached; inside lock: cached
        mock_usc.is_fully_cached.side_effect = [False, True]
        _prefetch_all_user_sheets({"google_id": "g1234567", "spreadsheet_id": "sid"})
        mock_usc.put_all.assert_not_called()


class TestPrefetchBlankRowBreak(unittest.TestCase):
    """Line 335: break on blank row in manual tab during batch-fetch."""

    @patch("app.fetchers.user_sheets_cache")
    @patch("app.fetchers.get_google_creds_dict", return_value={"token": "t"})
    @patch("app.api.google_auth.credentials_from_dict")
    @patch("app.api.google_sheets_client.GoogleSheetsClient")
    @patch("app.api.google_sheets_client.PhysicalGoldService")
    @patch("app.api.google_sheets_client.FixedDepositsService")
    @patch("app.api.fixed_deposits.calculate_current_value", return_value=[])
    def test_blank_row_in_manual_tab(
        self, mock_calc, mock_fd_svc, mock_gold_svc, mock_gsc, mock_creds, mock_get_creds, mock_usc
    ):
        from app.routes import _prefetch_all_user_sheets

        mock_usc.is_fully_cached.return_value = False
        mock_client = Mock()
        mock_gsc.return_value = mock_client
        mock_client.batch_fetch_sheet_data_until_blank.return_value = {
            "Gold": [],
            "FixedDeposits": [],
            "Stocks": [
                ["Symbol", "Qty", "AvgPrice", "Exchange", "Account"],
                ["INFY", "10", "1500", "NSE", "Manual"],
                ["", "", "", "", ""],  # blank row triggers break
                ["SHOULD_NOT_APPEAR", "1", "1", "NSE", "X"],
            ],
            "ETFs": [],
            "MutualFunds": [],
            "SIPs": [],
        }
        mock_gold_svc.return_value._parse_batch_data.return_value = []
        mock_fd_svc.return_value._parse_batch_data.return_value = []

        _prefetch_all_user_sheets({"google_id": "g1234567", "spreadsheet_id": "sid"})
        call_args = mock_usc.put_all.call_args
        manual = call_args.kwargs.get("manual") or call_args[1].get("manual")
        # Stocks should have 1 row (blank row stopped parsing)
        self.assertEqual(len(manual.get("stocks", [])), 1)


class TestBackgroundSheetCreation(unittest.TestCase):
    """Lines 438-443: inner _create_sheet_bg function body."""

    @patch("app.api.user_sheets.create_portfolio_sheet", return_value="new_sid")
    @patch("app.firebase_store.update_spreadsheet_id")
    @patch("app.firebase_store.upsert_user")
    @patch("app.firebase_store.get_user", return_value=None)
    @patch("app.api.google_auth.credentials_to_dict", return_value={"token": "t"})
    @patch(
        "app.api.google_auth.get_user_info",
        return_value={"id": "g1234567890", "email": "test@example.com", "name": "Test", "picture": "http://pic.jpg"},
    )
    @patch("app.api.google_auth.exchange_code_for_credentials")
    def test_create_sheet_bg_success(
        self, mock_exchange, mock_info, mock_creds_dict, mock_get_user, mock_upsert, mock_update_sid, mock_create_sheet
    ):
        """Execute the background thread function synchronously."""
        mock_exchange.return_value = Mock()
        captured = {}

        def capture_thread(*args, **kwargs):
            captured["target"] = kwargs.get("target")
            captured["args"] = kwargs.get("args")
            mock_t = Mock()
            return mock_t

        with patch("threading.Thread", side_effect=capture_thread):
            client = app_ui.test_client()
            resp = client.get("/api/auth/google/callback?code=abc123")

        self.assertEqual(resp.status_code, 302)
        # Now call the captured function to cover lines 438-443
        self.assertIn("target", captured)
        captured["target"](*captured["args"])
        mock_create_sheet.assert_called_once()
        mock_update_sid.assert_called_once()

    @patch("app.api.user_sheets.create_portfolio_sheet", side_effect=Exception("fail"))
    @patch("app.firebase_store.update_spreadsheet_id")
    @patch("app.firebase_store.upsert_user")
    @patch("app.firebase_store.get_user", return_value=None)
    @patch("app.api.google_auth.credentials_to_dict", return_value={"token": "t"})
    @patch(
        "app.api.google_auth.get_user_info",
        return_value={"id": "g1234567890", "email": "test@example.com", "name": "Test", "picture": "http://pic.jpg"},
    )
    @patch("app.api.google_auth.exchange_code_for_credentials")
    def test_create_sheet_bg_exception(
        self, mock_exchange, mock_info, mock_creds_dict, mock_get_user, mock_upsert, mock_update_sid, mock_create_sheet
    ):
        """Cover except branch inside _create_sheet_bg."""
        mock_exchange.return_value = Mock()
        captured = {}

        def capture_thread(*args, **kwargs):
            captured["target"] = kwargs.get("target")
            captured["args"] = kwargs.get("args")
            return Mock()

        with patch("threading.Thread", side_effect=capture_thread):
            client = app_ui.test_client()
            resp = client.get("/api/auth/google/callback?code=abc123")

        self.assertEqual(resp.status_code, 302)
        # Execute the captured bg function — exception is caught internally
        captured["target"](*captured["args"])


class TestFetchUncachedLTPsException(unittest.TestCase):
    """Lines 920-921: _fetch_uncached_manual_ltps exception path."""

    @patch("app.routes.manual_ltp_cache")
    @patch("app.api.market_data.MarketDataClient", side_effect=Exception("network"))
    @patch("app.routes._fetch_manual_entries", return_value=[{"symbol": "INFY"}])
    def test_exception_caught(self, mock_entries, mock_client_cls, mock_cache):
        from app.routes import _fetch_uncached_manual_ltps

        mock_cache.get.return_value = None
        mock_cache.is_negative.return_value = False
        # Should not raise despite MarketDataClient failing
        _fetch_uncached_manual_ltps({"google_id": "g1"}, "INFY")


class TestFetchUncachedLTPsNegativeBatch(unittest.TestCase):
    """Cover negative batch path in _fetch_uncached_manual_ltps."""

    @patch("app.routes.manual_ltp_cache")
    @patch("app.api.market_data.MarketDataClient")
    @patch("app.routes._fetch_manual_entries", return_value=[{"symbol": "MISS"}])
    def test_missed_symbols_negative_cached(self, mock_entries, mock_client_cls, mock_cache):
        from app.routes import _fetch_uncached_manual_ltps

        mock_cache.get.return_value = None
        mock_cache.is_negative.return_value = False
        mock_client_cls.return_value.fetch_stock_quotes.return_value = {}  # nothing fetched
        _fetch_uncached_manual_ltps({"google_id": "g1"}, "MISS")
        mock_cache.put_negative_batch.assert_called_once()


class TestBuildMfDataWithManual(unittest.TestCase):
    """Lines 955-957: _build_mf_data loop body with manual entries."""

    @patch(
        "app.routes._fetch_manual_entries",
        return_value=[{"fund": "AXIS", "qty": "100", "avg_nav": "50", "account": "Manual", "row_number": 2}],
    )
    @patch("app.routes.portfolio_cache")
    def test_manual_entries_merged(self, mock_pc, mock_manual):
        from app.cache import UserPortfolioData
        from app.routes import _build_mf_data

        mock_pc.get.return_value = UserPortfolioData(mf_holdings=[])
        result = _build_mf_data({"google_id": "g1"})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["fund"], "AXIS")
        self.assertEqual(result[0]["quantity"], 100.0)


class TestGetSheetsClientNoSpreadsheet(unittest.TestCase):
    """Lines 1380-1385: _get_sheets_client when user has no spreadsheet_id."""

    @patch("app.api.google_auth.credentials_from_dict")
    @patch("app.api.google_sheets_client.GoogleSheetsClient")
    def test_no_spreadsheet_id(self, mock_gsc, mock_creds):
        from app.routes import _get_sheets_client, app_ui

        with app_ui.test_request_context("/"):
            from flask import session

            session["user"] = {
                "google_id": "g1",
                "email": "e",
                "name": "N",
                "picture": "",
                "spreadsheet_id": "",
                "google_credentials": {"token": "t"},
            }
            client, sid, err = _get_sheets_client()
            self.assertIsNone(client)
            self.assertEqual(err, "No spreadsheet linked")

    @patch("app.api.google_auth.credentials_from_dict")
    @patch("app.api.google_sheets_client.GoogleSheetsClient")
    def test_success(self, mock_gsc_cls, mock_creds):
        """Line 1385: _get_sheets_client success return."""
        from app.routes import _get_sheets_client, app_ui

        mock_creds.return_value = Mock()
        mock_client_instance = Mock()
        mock_gsc_cls.return_value = mock_client_instance
        with app_ui.test_request_context("/"):
            from flask import session

            session["user"] = {
                "google_id": "g1",
                "email": "e",
                "name": "N",
                "picture": "",
                "spreadsheet_id": "sheet123",
                "google_credentials": {"token": "t"},
            }
            client, sid, err = _get_sheets_client()
            self.assertEqual(client, mock_client_instance)
            self.assertEqual(sid, "sheet123")
            self.assertIsNone(err)


class TestRefreshSingleSheetCacheBlankRow(unittest.TestCase):
    """Line 1438: break on blank row in _refresh_single_sheet_cache manual path."""

    @patch("app.routes.user_sheets_cache")
    def test_manual_blank_row_break(self, mock_usc):
        from app.routes import _refresh_single_sheet_cache

        mock_client = Mock()
        mock_client.fetch_sheet_data_until_blank.return_value = [
            ["Symbol", "Qty", "AvgPrice", "Exchange", "Account"],
            ["INFY", "10", "1500", "NSE", "Manual"],
            ["", "", "", "", ""],  # blank row → break
            ["TCS", "5", "3000", "NSE", "Manual"],
        ]
        _refresh_single_sheet_cache(mock_client, "sid", "g1", "stocks")
        call_args = mock_usc.put_manual.call_args
        # put_manual(google_id, sheet_type, rows)
        self.assertEqual(len(call_args[0][2]), 1)  # only 1 row before blank


class TestBuildDataForTypeSuccess(unittest.TestCase):
    """Line 1465: builder(user) success path in _build_data_for_type."""

    @patch("app.routes._build_mf_data", return_value=[{"fund": "A"}])
    def test_mf_builder_success(self, mock_build):
        from app.routes import _build_data_for_type

        result = _build_data_for_type({"google_id": "g1"}, "mutual_funds")
        self.assertIn("mfHoldings", result)
        self.assertEqual(result["mfHoldings"], [{"fund": "A"}])

    @patch("app.routes._build_gold_data", return_value=[{"g": 1}])
    def test_gold_builder_success(self, mock_build):
        from app.routes import _build_data_for_type

        result = _build_data_for_type({"google_id": "g1"}, "physical_gold")
        self.assertIn("physicalGold", result)

    @patch("app.routes._build_fd_data", side_effect=Exception("fail"))
    def test_builder_exception(self, mock_build):
        from app.routes import _build_data_for_type

        result = _build_data_for_type({"google_id": "g1"}, "fixed_deposits")
        self.assertEqual(result, {})


class TestSheetsListEmptyData(unittest.TestCase):
    """Line 1502: sheets_list returns empty JSON when raw has < 2 rows."""

    def setUp(self):
        self.client = app_ui.test_client()
        app_ui.testing = True

    @patch("app.routes._get_sheets_client")
    def test_empty_sheet(self, mock_get_client):
        mock_client = Mock()
        mock_client.ensure_sheet_tab.return_value = None
        mock_client.fetch_sheet_data_until_blank.return_value = [["Header"]]
        mock_get_client.return_value = (mock_client, "sid", None)
        _inject_user(self.client)
        resp = self.client.get("/api/sheets/stocks", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(json.loads(resp.data), [])

    @patch("app.routes._get_sheets_client")
    def test_blank_row_break(self, mock_get_client):
        """Line 1502: blank row triggers break in sheets_list loop."""
        mock_client = Mock()
        mock_client.fetch_sheet_data_until_blank.return_value = [
            ["Symbol", "Qty", "AvgPrice", "Exchange", "Account"],
            ["INFY", "10", "1500", "NSE", "Manual"],
            ["", "", "", "", ""],  # blank row → break
            ["TCS", "5", "3000", "NSE", "Manual"],
        ]
        mock_get_client.return_value = (mock_client, "sid", None)
        _inject_user(self.client)
        resp = self.client.get("/api/sheets/stocks", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(len(data), 1)  # only INFY; TCS after blank skipped


class TestSheetsAddSuccessPaths(unittest.TestCase):
    """Lines 1518, 1522: sheets_add inner success with stocks/etfs."""

    def setUp(self):
        self.client = app_ui.test_client()
        app_ui.testing = True

    @patch("app.routes._build_data_for_type", return_value={"stocks": [{"s": 1}]})
    @patch("app.routes._fetch_uncached_manual_ltps")
    @patch("app.routes._refresh_single_sheet_cache")
    @patch("app.routes._validate_nse_symbol", return_value={"ltp": 100})
    @patch("app.routes.manual_ltp_cache")
    @patch("app.routes._get_sheets_client")
    def test_add_stock_with_data_refresh(
        self, mock_get_client, mock_ltp, mock_validate, mock_refresh, mock_uncached, mock_build
    ):
        mock_client = Mock()
        mock_client.append_row.return_value = 3
        mock_get_client.return_value = (mock_client, "sid", None)
        _inject_user(self.client)
        resp = self.client.post(
            "/api/sheets/stocks",
            headers={**_APP_HEADERS, "Content-Type": "application/json"},
            data=json.dumps({"symbol": "TCS", "qty": "5", "avg_price": "3000", "exchange": "NSE", "account": "A"}),
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertIn("data", data)
        mock_uncached.assert_called_once()

    @patch("app.routes._build_data_for_type", return_value={})
    @patch("app.routes._refresh_single_sheet_cache")
    @patch("app.routes._get_sheets_client")
    def test_add_mutual_fund_no_validation(self, mock_get_client, mock_refresh, mock_build):
        """Add mutual_fund type — no NSE validation, no _fetch_uncached_manual_ltps."""
        mock_client = Mock()
        mock_client.append_row.return_value = 2
        mock_get_client.return_value = (mock_client, "sid", None)
        _inject_user(self.client)
        resp = self.client.post(
            "/api/sheets/mutual_funds",
            headers={**_APP_HEADERS, "Content-Type": "application/json"},
            data=json.dumps({"fund": "AXIS", "qty": "100", "avg_nav": "50", "account": "X"}),
        )
        self.assertEqual(resp.status_code, 200)

    @patch("app.routes._get_sheets_client")
    def test_add_exception(self, mock_get_client):
        mock_client = Mock()
        mock_client.ensure_sheet_tab.side_effect = Exception("boom")
        mock_get_client.return_value = (mock_client, "sid", None)
        _inject_user(self.client)
        resp = self.client.post(
            "/api/sheets/sips",
            headers={**_APP_HEADERS, "Content-Type": "application/json"},
            data=json.dumps({"fund": "A"}),
        )
        self.assertEqual(resp.status_code, 500)


class TestSheetsUpdateSuccessPaths(unittest.TestCase):
    """Lines 1567, 1574, 1583: sheets_update inner success paths."""

    def setUp(self):
        self.client = app_ui.test_client()
        app_ui.testing = True

    @patch("app.routes._build_data_for_type", return_value={"stocks": [{"s": 1}]})
    @patch("app.routes._refresh_single_sheet_cache")
    @patch("app.routes._validate_nse_symbol", return_value={"ltp": 200})
    @patch("app.routes.manual_ltp_cache")
    @patch("app.routes._get_sheets_client")
    def test_update_stock_with_validation(self, mock_get_client, mock_ltp, mock_validate, mock_refresh, mock_build):
        mock_client = Mock()
        mock_get_client.return_value = (mock_client, "sid", None)
        _inject_user(self.client)
        resp = self.client.put(
            "/api/sheets/stocks/3",
            headers={**_APP_HEADERS, "Content-Type": "application/json"},
            data=json.dumps({"symbol": "INFY", "qty": "20", "avg_price": "1600", "exchange": "NSE", "account": "B"}),
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertIn("data", data)
        mock_validate.assert_called_once()

    @patch("app.routes._validate_nse_symbol", return_value=None)
    @patch("app.routes._get_sheets_client")
    def test_update_stock_invalid_symbol(self, mock_get_client, mock_validate):
        mock_get_client.return_value = (Mock(), "sid", None)
        _inject_user(self.client)
        resp = self.client.put(
            "/api/sheets/etfs/3",
            headers={**_APP_HEADERS, "Content-Type": "application/json"},
            data=json.dumps({"symbol": "FAKE", "qty": "10", "avg_price": "100", "exchange": "NSE", "account": "A"}),
        )
        self.assertEqual(resp.status_code, 400)

    @patch("app.routes._get_sheets_client")
    def test_update_exception(self, mock_get_client):
        mock_client = Mock()
        mock_client.update_row.side_effect = Exception("fail")
        mock_get_client.return_value = (mock_client, "sid", None)
        _inject_user(self.client)
        resp = self.client.put(
            "/api/sheets/stocks/3",
            headers={**_APP_HEADERS, "Content-Type": "application/json"},
            data=json.dumps({"symbol": "INFY"}),
        )
        self.assertEqual(resp.status_code, 500)


class TestSheetsDeleteSuccessPaths(unittest.TestCase):
    """Lines 1619, 1634: sheets_delete inner success paths."""

    def setUp(self):
        self.client = app_ui.test_client()
        app_ui.testing = True

    @patch("app.routes._build_data_for_type", return_value={"stocks": []})
    @patch("app.routes._refresh_single_sheet_cache")
    @patch("app.routes._get_sheets_client")
    def test_delete_with_data_refresh(self, mock_get_client, mock_refresh, mock_build):
        mock_client = Mock()
        mock_get_client.return_value = (mock_client, "sid", None)
        _inject_user(self.client)
        resp = self.client.delete("/api/sheets/stocks/5", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertIn("data", data)

    @patch("app.routes._get_sheets_client")
    def test_delete_exception(self, mock_get_client):
        mock_client = Mock()
        mock_client.delete_row.side_effect = Exception("fail")
        mock_get_client.return_value = (mock_client, "sid", None)
        _inject_user(self.client)
        resp = self.client.delete("/api/sheets/stocks/5", headers=_APP_HEADERS)
        self.assertEqual(resp.status_code, 500)
