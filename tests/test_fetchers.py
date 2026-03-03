"""
Unit tests for fetchers.py (data fetching and auto-refresh logic).
"""
import unittest
from unittest.mock import Mock, patch, MagicMock

from app.fetchers import (_should_auto_refresh,
                          fetch_nifty50_data, fetch_portfolio_data,
                          run_background_fetch)


class TestFetchPortfolioData(unittest.TestCase):
    """Test fetch_portfolio_data function (per-user)."""

    @patch('app.fetchers.portfolio_cache')
    @patch('app.fetchers.zerodha_client')
    @patch('app.fetchers.state_manager')
    def test_success(self, mock_state, mock_client, mock_pcache):
        mock_client.fetch_all_accounts_data.return_value = (
            [{'stock': 1}],
            [{'mf': 1}],
            [{'sip': 1}],
            None,
        )

        fetch_portfolio_data("user1", accounts=[{"name": "test"}])

        mock_pcache.set_fetch_in_progress.assert_called_once_with("user1")
        mock_state.set_portfolio_updating.assert_called_once_with(google_id="user1")
        mock_pcache.set.assert_called_once_with(
            "user1", stocks=[{'stock': 1}], mf_holdings=[{'mf': 1}], sips=[{'sip': 1}]
        )
        mock_state.set_portfolio_updated.assert_called_once_with(google_id="user1", error=None)
        mock_pcache.clear_fetch_in_progress.assert_called_once_with("user1")

    @patch('app.fetchers.portfolio_cache')
    @patch('app.fetchers.zerodha_client')
    @patch('app.fetchers.state_manager')
    def test_with_error_preserves_old_data(self, mock_state, mock_client, mock_pcache):
        mock_client.fetch_all_accounts_data.return_value = (
            [], [], [], "Test error",
        )
        # Simulate existing cached data
        mock_user_data = Mock()
        mock_user_data.stocks = [{'old_stock': 1}]
        mock_user_data.mf_holdings = [{'old_mf': 1}]
        mock_user_data.sips = [{'old_sip': 1}]
        mock_pcache.get.return_value = mock_user_data

        fetch_portfolio_data("user1", accounts=[{"name": "test"}])

        mock_state.set_portfolio_updated.assert_called_once_with(
            google_id="user1", error="Test error"
        )
        # cache.set should NOT have been called (data preserved)
        mock_pcache.set.assert_not_called()

    @patch('app.fetchers.portfolio_cache')
    @patch('app.fetchers.zerodha_client')
    @patch('app.fetchers.state_manager')
    def test_success_updates_cache(self, mock_state, mock_client, mock_pcache):
        mock_client.fetch_all_accounts_data.return_value = (
            [{'new_stock': 1}],
            [{'new_mf': 1}],
            [{'new_sip': 1}],
            None,
        )

        fetch_portfolio_data("user1", accounts=[{"name": "test"}])

        mock_pcache.set.assert_called_once_with(
            "user1",
            stocks=[{'new_stock': 1}],
            mf_holdings=[{'new_mf': 1}],
            sips=[{'new_sip': 1}],
        )

    @patch('app.fetchers.get_authenticated_accounts')
    @patch('app.fetchers.portfolio_cache')
    @patch('app.fetchers.zerodha_client')
    @patch('app.fetchers.state_manager')
    def test_no_accounts_skips_fetch(self, mock_state, mock_client, mock_pcache, mock_auth):
        mock_auth.return_value = []

        fetch_portfolio_data("user1")

        mock_client.fetch_all_accounts_data.assert_not_called()

    @patch('app.fetchers.portfolio_cache')
    @patch('app.fetchers.zerodha_client')
    @patch('app.fetchers.state_manager')
    def test_injects_google_id_into_accounts(self, mock_state, mock_client, mock_pcache):
        """Each account config should have google_id injected."""
        mock_client.fetch_all_accounts_data.return_value = ([], [], [], None)

        fetch_portfolio_data("user1", accounts=[{"name": "Acc1", "api_key": "k1"}])

        call_args = mock_client.fetch_all_accounts_data.call_args[0][0]
        self.assertEqual(call_args[0]["google_id"], "user1")
        self.assertEqual(call_args[0]["name"], "Acc1")


class TestFetchNifty50Data(unittest.TestCase):
    """Test fetch_nifty50_data function."""

    @patch('app.fetchers.threading.Thread')
    @patch('app.fetchers.state_manager')
    @patch('app.fetchers.nifty50_fetch_in_progress')
    def test_skips_if_in_progress(self, mock_event, mock_state, mock_thread):
        mock_event.is_set.return_value = True

        fetch_nifty50_data()

        mock_thread.assert_not_called()


class TestRunBackgroundFetch(unittest.TestCase):
    """Test run_background_fetch orchestration."""

    def test_starts_background_thread(self):
        with patch('app.fetchers.threading.Thread') as mock_thread:
            mock_instance = Mock()
            mock_thread.return_value = mock_instance

            run_background_fetch(google_id="user1")

            mock_thread.assert_called()
            mock_instance.start.assert_called_once()

    def test_passes_google_id(self):
        """run_background_fetch should propagate google_id to fetch_portfolio_data."""
        with patch('app.fetchers.threading.Thread') as mock_thread:
            mock_instance = Mock()
            mock_thread.return_value = mock_instance

            run_background_fetch(google_id="user1", accounts=[{"name": "Acc1"}])

            mock_thread.assert_called()


class TestShouldAutoRefresh(unittest.TestCase):
    """Test _should_auto_refresh decision logic."""

    @patch('app.fetchers.sse_manager')
    @patch('app.fetchers.is_market_open_ist')
    def test_market_closed(self, mock_market_open, mock_sse):
        with patch('app.fetchers.app_config') as mock_config:
            mock_config.auto_refresh_outside_market_hours = False
            mock_market_open.return_value = False

            should_run, reason = _should_auto_refresh()

            self.assertFalse(should_run)
            self.assertIn("market closed", reason)

    @patch('app.fetchers.sse_manager')
    @patch('app.fetchers.is_market_open_ist')
    def test_no_connected_users(self, mock_market, mock_sse):
        mock_market.return_value = True
        mock_sse.connected_user_ids.return_value = set()

        should_run, reason = _should_auto_refresh()

        self.assertFalse(should_run)
        self.assertIn("no active", reason)

    @patch('app.fetchers.sse_manager')
    @patch('app.fetchers.is_market_open_ist')
    def test_allowed(self, mock_market_open, mock_sse):
        mock_market_open.return_value = True
        mock_sse.connected_user_ids.return_value = {"user1"}

        should_run, reason = _should_auto_refresh()

        self.assertTrue(should_run)
        self.assertIsNone(reason)


class TestZerodhaClientFetchAccountData(unittest.TestCase):
    """Test zerodha_client.fetch_account_data via services."""

    def test_fetch_account_data(self):
        from app.services import zerodha_client

        with patch('app.services.auth_manager.authenticate') as mock_auth, \
             patch('app.services.holdings_service.fetch_holdings') as mock_holdings, \
             patch('app.services.sip_service.fetch_sips') as mock_sips:

            mock_kite = Mock()
            mock_auth.return_value = mock_kite
            mock_holdings.return_value = ([{"stock": 1}], [{"mf": 1}])
            mock_sips.return_value = [{"sip": 1}]

            account_config = {"name": "test", "api_key_env": "TEST_KEY"}
            stocks, mfs, sips = zerodha_client.fetch_account_data(account_config)

            mock_auth.assert_called_once_with(account_config)
            mock_holdings.assert_called_once_with(mock_kite)
            mock_sips.assert_called_once_with(mock_kite)
            self.assertEqual(len(stocks), 1)
            self.assertEqual(len(mfs), 1)
            self.assertEqual(len(sips), 1)


if __name__ == '__main__':
    unittest.main()
