"""
Unit tests for app.middleware – API security decorators.
"""

import json
import unittest
from unittest.mock import patch

from app.middleware import (
    _is_app_request,
    _is_authenticated,
    app_only,
    login_required,
    protected_api,
)
from app.constants import APP_REQUEST_HEADER, APP_REQUEST_HEADER_VALUE
from app.routes import app_ui

# Reusable session user dict
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


class TestLoginRequired(unittest.TestCase):
    """Tests for the @login_required decorator."""

    def setUp(self):
        self.app = app_ui
        self.app.testing = True
        self.client = self.app.test_client()

    def test_unauthenticated_returns_401(self):
        """Unauthenticated request to a protected endpoint returns 401."""
        response = self.client.get(
            "/api/stocks_data",
            headers=_APP_HEADERS,
        )
        self.assertEqual(response.status_code, 401)
        data = json.loads(response.data)
        self.assertEqual(data["error"], "Authentication required")

    def test_authenticated_passes(self):
        """Authenticated request is allowed through @login_required."""
        with patch("app.routes.portfolio_cache") as mock_pcache:
            from app.cache import UserPortfolioData

            mock_pcache.get.return_value = UserPortfolioData(
                stocks=[{"tradingsymbol": "INFY", "quantity": 10}],
            )
            _inject_user(self.client)
            response = self.client.get(
                "/api/stocks_data",
                headers=_APP_HEADERS,
            )

        self.assertEqual(response.status_code, 200)


class TestAppOnly(unittest.TestCase):
    """Tests for the @app_only decorator."""

    def setUp(self):
        self.app = app_ui
        self.app.testing = True
        self.client = self.app.test_client()
        # Ensure browser API access is disabled for tests
        from app.config import app_config

        app_config.features["allow_browser_api_access"] = False

    def test_no_header_returns_403(self):
        """Request without X-Requested-With header returns 403."""
        response = self.client.get("/api/nifty50_data")
        self.assertEqual(response.status_code, 403)
        data = json.loads(response.data)
        self.assertEqual(data["error"], "Forbidden")

    def test_wrong_header_value_returns_403(self):
        """Request with wrong X-Requested-With value returns 403."""
        response = self.client.get(
            "/api/nifty50_data",
            headers={APP_REQUEST_HEADER: "SomeOtherApp"},
        )
        self.assertEqual(response.status_code, 403)

    def test_correct_header_passes(self):
        """Request with correct X-Requested-With header passes."""
        with patch("app.routes.market_cache") as mock_mc:
            mock_mc.nifty50 = [{"symbol": "TCS", "ltp": 3500}]
            response = self.client.get(
                "/api/nifty50_data",
                headers=_APP_HEADERS,
            )

        self.assertEqual(response.status_code, 200)

    def test_sec_fetch_mode_same_origin_passes(self):
        """Request with Sec-Fetch-Mode: same-origin passes without custom header."""
        with patch("app.routes.market_cache") as mock_mc:
            mock_mc.nifty50 = [{"symbol": "TCS", "ltp": 3500}]
            response = self.client.get(
                "/api/nifty50_data",
                headers={"Sec-Fetch-Mode": "same-origin"},
            )

        self.assertEqual(response.status_code, 200)

    def test_sec_fetch_mode_cors_passes(self):
        """Request with Sec-Fetch-Mode: cors passes."""
        with patch("app.routes.market_cache") as mock_mc:
            mock_mc.nifty50 = [{"symbol": "TCS", "ltp": 3500}]
            response = self.client.get(
                "/api/nifty50_data",
                headers={"Sec-Fetch-Mode": "cors"},
            )

        self.assertEqual(response.status_code, 200)

    def test_sec_fetch_mode_navigate_blocked(self):
        """Request with Sec-Fetch-Mode: navigate is blocked (direct browser access)."""
        response = self.client.get(
            "/api/nifty50_data",
            headers={"Sec-Fetch-Mode": "navigate"},
        )
        self.assertEqual(response.status_code, 403)

    @patch("app.middleware.app_config")
    def test_debug_flag_bypasses_check(self, mock_config):
        """When allow_browser_api_access is True, direct access is allowed."""
        mock_config.features = {"allow_browser_api_access": True}
        with patch("app.routes.market_cache") as mock_mc:
            mock_mc.nifty50 = [{"symbol": "TCS", "ltp": 3500}]
            # No special headers — simulates direct browser access
            response = self.client.get("/api/nifty50_data")

        self.assertEqual(response.status_code, 200)

    @patch("app.middleware.app_config")
    def test_debug_flag_false_enforces_check(self, mock_config):
        """When allow_browser_api_access is False, direct access is blocked."""
        mock_config.features = {"allow_browser_api_access": False}
        response = self.client.get("/api/nifty50_data")
        self.assertEqual(response.status_code, 403)


class TestProtectedApi(unittest.TestCase):
    """Tests for the @protected_api decorator (auth + app-only combined)."""

    def setUp(self):
        self.app = app_ui
        self.app.testing = True
        self.client = self.app.test_client()
        from app.config import app_config

        app_config.features["allow_browser_api_access"] = False

    def test_unauthenticated_without_header_returns_401(self):
        """Auth check runs first — 401 before 403."""
        response = self.client.get("/api/stocks_data")
        self.assertEqual(response.status_code, 401)

    def test_unauthenticated_with_header_returns_401(self):
        """Even with the app header, unauthenticated gets 401."""
        response = self.client.get(
            "/api/stocks_data",
            headers=_APP_HEADERS,
        )
        self.assertEqual(response.status_code, 401)

    def test_authenticated_without_header_returns_403(self):
        """Authenticated but without app header gets 403."""
        _inject_user(self.client)
        response = self.client.get("/api/stocks_data")
        self.assertEqual(response.status_code, 403)

    def test_authenticated_with_header_passes(self):
        """Authenticated + app header → success."""
        with patch("app.routes.portfolio_cache") as mock_pcache:
            from app.cache import UserPortfolioData

            mock_pcache.get.return_value = UserPortfolioData(
                stocks=[{"tradingsymbol": "INFY", "quantity": 10}],
            )
            _inject_user(self.client)
            response = self.client.get(
                "/api/stocks_data",
                headers=_APP_HEADERS,
            )

        self.assertEqual(response.status_code, 200)

    @patch("app.middleware.app_config")
    def test_authenticated_debug_flag_bypasses_app_only(self, mock_config):
        """Debug flag bypasses app-only but still requires auth."""
        mock_config.features = {"allow_browser_api_access": True}
        with patch("app.routes.portfolio_cache") as mock_pcache:
            from app.cache import UserPortfolioData

            mock_pcache.get.return_value = UserPortfolioData(
                stocks=[{"tradingsymbol": "INFY", "quantity": 10}],
            )
            _inject_user(self.client)
            # No X-Requested-With header, simulating browser access
            response = self.client.get("/api/stocks_data")

        self.assertEqual(response.status_code, 200)

    @patch("app.middleware.app_config")
    def test_unauthenticated_debug_flag_still_requires_auth(self, mock_config):
        """Debug flag does NOT bypass authentication."""
        mock_config.features = {"allow_browser_api_access": True}
        response = self.client.get("/api/stocks_data")
        self.assertEqual(response.status_code, 401)


class TestProtectedEndpoints(unittest.TestCase):
    """Smoke tests to verify all protected endpoints reject unauthenticated requests."""

    def setUp(self):
        self.app = app_ui
        self.app.testing = True
        self.client = self.app.test_client()
        from app.config import app_config

        app_config.features["allow_browser_api_access"] = False

    def test_protected_get_endpoints_require_auth(self):
        """All user-data GET endpoints return 401 without session."""
        protected_gets = [
            "/api/stocks_data",
            "/api/mf_holdings_data",
            "/api/sips_data",
            "/api/physical_gold_data",
            "/api/fixed_deposits_data",
            "/api/fd_summary_data",
            "/api/status",
            "/api/settings",
        ]
        for endpoint in protected_gets:
            response = self.client.get(endpoint, headers=_APP_HEADERS)
            self.assertEqual(
                response.status_code,
                401,
                f"{endpoint} should return 401 when unauthenticated",
            )

    def test_protected_post_endpoints_require_auth(self):
        """POST endpoints return 401 without session."""
        response = self.client.post("/api/refresh", headers=_APP_HEADERS)
        self.assertEqual(response.status_code, 401)

        response = self.client.post(
            "/api/settings/zerodha",
            headers={**_APP_HEADERS, "Content-Type": "application/json"},
            data=json.dumps({"account_name": "x", "api_key": "k", "api_secret": "s"}),
        )
        self.assertEqual(response.status_code, 401)

    def test_protected_delete_endpoint_requires_auth(self):
        """DELETE endpoint returns 401 without session."""
        response = self.client.delete(
            "/api/settings/zerodha/test",
            headers=_APP_HEADERS,
        )
        self.assertEqual(response.status_code, 401)

    def test_app_only_endpoints_reject_direct_access(self):
        """Market data endpoints reject requests without app header."""
        app_only_endpoints = [
            "/api/nifty50_data",
            "/api/market_indices",
        ]
        for endpoint in app_only_endpoints:
            response = self.client.get(endpoint)
            self.assertEqual(
                response.status_code,
                403,
                f"{endpoint} should return 403 without app header",
            )


class TestPinRequired(unittest.TestCase):
    """Tests for the @pin_required decorator."""

    def setUp(self):
        self.app = app_ui
        self.app.testing = True
        self.client = self.app.test_client()

    def test_unauthenticated_returns_401(self):
        """pin_required returns 401 when user not in session."""
        response = self.client.get(
            "/api/stocks_data",
            headers=_APP_HEADERS,
        )
        self.assertEqual(response.status_code, 401)

    def test_non_app_request_returns_403(self):
        """pin_required returns 403 for direct browser access."""
        _inject_user(self.client)
        # No app header → direct access
        response = self.client.get("/api/stocks_data")
        self.assertEqual(response.status_code, 403)

    def test_pin_not_verified_returns_403(self):
        """pin_required returns 403 when pin_verified is False."""
        with self.client.session_transaction() as sess:
            sess["user"] = _TEST_USER
            sess["pin_verified"] = False
        response = self.client.get(
            "/api/stocks_data",
            headers=_APP_HEADERS,
        )
        self.assertEqual(response.status_code, 403)
        data = json.loads(response.data)
        self.assertEqual(data["error"], "pin_required")

    def test_in_memory_pin_lost_clears_flag(self):
        """When the server restarts and in-memory PIN is gone,
        pin_required should clear the session flag and return 403."""
        from app.services import session_manager

        _inject_user(self.client)
        # Simulate server restart: remove the in-memory PIN
        session_manager._user_pins.pop("test123", None)
        response = self.client.get(
            "/api/stocks_data",
            headers=_APP_HEADERS,
        )
        self.assertEqual(response.status_code, 403)
        data = json.loads(response.data)
        self.assertEqual(data["error"], "pin_required")
        # Restore PIN for other tests
        session_manager.set_pin("test123", "test01")


class TestPublicEndpoints(unittest.TestCase):
    """Verify public endpoints remain accessible without authentication."""

    def setUp(self):
        self.app = app_ui
        self.app.testing = True
        self.client = self.app.test_client()

    def test_landing_page_accessible(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_nifty50_page_accessible(self):
        response = self.client.get("/nifty50")
        self.assertEqual(response.status_code, 200)

    def test_auth_me_accessible(self):
        """auth/me should return 401 body but not be blocked by middleware."""
        response = self.client.get("/api/auth/me")
        self.assertEqual(response.status_code, 401)
        data = json.loads(response.data)
        self.assertFalse(data["authenticated"])


class TestIsAppRequest(unittest.TestCase):
    """Unit tests for the _is_app_request() helper."""

    def test_custom_header_recognised(self):
        with self.app.test_request_context(
            "/test",
            headers={APP_REQUEST_HEADER: APP_REQUEST_HEADER_VALUE},
        ):
            self.assertTrue(_is_app_request())

    def test_sec_fetch_same_origin_recognised(self):
        with self.app.test_request_context(
            "/test",
            headers={"Sec-Fetch-Mode": "same-origin"},
        ):
            self.assertTrue(_is_app_request())

    def test_sec_fetch_navigate_rejected(self):
        with self.app.test_request_context(
            "/test",
            headers={"Sec-Fetch-Mode": "navigate"},
        ):
            self.assertFalse(_is_app_request())

    def test_no_headers_rejected(self):
        with self.app.test_request_context("/test"):
            self.assertFalse(_is_app_request())

    @property
    def app(self):
        return app_ui


class TestIsAuthenticated(unittest.TestCase):
    """Unit tests for the _is_authenticated() helper."""

    def test_with_user_in_session(self):
        with app_ui.test_request_context("/test"):
            from flask import session

            session["user"] = _TEST_USER
            self.assertTrue(_is_authenticated())

    def test_without_user_in_session(self):
        with app_ui.test_request_context("/test"):
            self.assertFalse(_is_authenticated())


class TestLoginRequiredDirect(unittest.TestCase):
    """Direct unit test for @login_required decorator to hit lines 70-71."""

    def test_unauthenticated_via_decorator(self):
        @login_required
        def dummy_view():
            return "ok"

        with app_ui.test_request_context("/test", method="GET"):
            resp = dummy_view()
            self.assertEqual(resp[1], 401)


class TestAppOnlyDirect(unittest.TestCase):
    """Direct unit test for @app_only decorator to hit line 99."""

    def test_non_app_request_via_decorator(self):
        from app.config import app_config

        app_config.features["allow_browser_api_access"] = False

        @app_only
        def dummy_view():
            return "ok"

        with app_ui.test_request_context("/test", method="GET"):
            resp = dummy_view()
            self.assertEqual(resp[1], 403)


class TestProtectedApiDenyNonApp(unittest.TestCase):
    """Test protected_api rejects authenticated but non-app request (line 99)."""

    def test_authenticated_but_non_app_request(self):
        from flask import session as flask_session

        from app.config import app_config

        app_config.features["allow_browser_api_access"] = False

        @protected_api
        def dummy_view():
            return "ok"

        with app_ui.test_request_context("/test", method="GET"):
            flask_session["user"] = _TEST_USER
            resp = dummy_view()
            self.assertEqual(resp[1], 403)


if __name__ == "__main__":
    unittest.main()
