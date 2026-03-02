"""
Unit tests for fetchers.py (data fetching and auto-refresh logic).
"""
import unittest
from unittest.mock import Mock, patch

from app.fetchers import (_should_auto_refresh,
                          fetch_nifty50_data, fetch_portfolio_data,
                          run_background_fetch)


class TestFetchPortfolioData(unittest.TestCase):
    """Test fetch_portfolio_data function."""

    @patch('app.fetchers.zerodha_client')
    @patch('app.fetchers.state_manager')
    @patch('app.fetchers.fetch_in_progress')
    def test_success(self, mock_event, mock_state, mock_client):
        mock_client.fetch_all_accounts_data.return_value = (
            [{'stock': 1}],
            [{'mf': 1}],
            [{'sip': 1}],
            None,
        )

        fetch_portfolio_data(accounts=[{"name": "test"}])

        mock_event.set.assert_called_once()
        mock_state.set_portfolio_updating.assert_called_once()
        mock_state.set_portfolio_updated.assert_called_once()
        mock_event.clear.assert_called_once()

    @patch('app.fetchers.cache')
    @patch('app.fetchers.zerodha_client')
    @patch('app.fetchers.state_manager')
    @patch('app.fetchers.fetch_in_progress')
    def test_with_error(self, mock_event, mock_state, mock_client, mock_cache):
        mock_client.fetch_all_accounts_data.return_value = (
            [], [], [], "Test error",
        )
        mock_cache.stocks = [{'old_stock': 1}]
        mock_cache.mf_holdings = [{'old_mf': 1}]
        mock_cache.sips = [{'old_sip': 1}]

        fetch_portfolio_data(accounts=[{"name": "test"}])

        mock_state.set_portfolio_updated.assert_called_with(error="Test error")
        # Verify cache was NOT updated (old data preserved)
        self.assertEqual(mock_cache.stocks, [{'old_stock': 1}])
        self.assertEqual(mock_cache.mf_holdings, [{'old_mf': 1}])
        self.assertEqual(mock_cache.sips, [{'old_sip': 1}])

    @patch('app.fetchers.cache')
    @patch('app.fetchers.zerodha_client')
    @patch('app.fetchers.state_manager')
    @patch('app.fetchers.fetch_in_progress')
    def test_success_updates_cache(self, mock_event, mock_state, mock_client, mock_cache):
        mock_client.fetch_all_accounts_data.return_value = (
            [{'new_stock': 1}],
            [{'new_mf': 1}],
            [{'new_sip': 1}],
            None,
        )
        mock_cache.stocks = [{'old_stock': 1}]
        mock_cache.mf_holdings = [{'old_mf': 1}]
        mock_cache.sips = [{'old_sip': 1}]

        fetch_portfolio_data(accounts=[{"name": "test"}])

        # Verify cache WAS updated with new data
        self.assertEqual(mock_cache.stocks, [{'new_stock': 1}])
        self.assertEqual(mock_cache.mf_holdings, [{'new_mf': 1}])
        self.assertEqual(mock_cache.sips, [{'new_sip': 1}])


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

            run_background_fetch()

            mock_thread.assert_called()
            mock_instance.start.assert_called_once()


class TestShouldAutoRefresh(unittest.TestCase):
    """Test _should_auto_refresh decision logic."""

    @patch('app.fetchers.is_market_open_ist')
    @patch('app.fetchers.fetch_in_progress')
    def test_market_closed(self, mock_in_progress, mock_market_open):
        with patch('app.fetchers.app_config') as mock_config:
            mock_config.auto_refresh_outside_market_hours = False
            mock_market_open.return_value = False
            mock_in_progress.is_set.return_value = False

            should_run, reason = _should_auto_refresh()

            self.assertFalse(should_run)
            self.assertIn("market closed", reason)

    @patch('app.fetchers.is_market_open_ist')
    @patch('app.fetchers.fetch_in_progress')
    def test_in_progress(self, mock_in_progress, mock_market):
        mock_market.return_value = True
        mock_in_progress.is_set.return_value = True

        should_run, reason = _should_auto_refresh()

        self.assertFalse(should_run)
        self.assertIn("manual refresh", reason)

    @patch('app.services.get_active_user', return_value='test123')
    @patch('app.fetchers.session_manager')
    @patch('app.fetchers.get_active_accounts', return_value=[{'name': 'test'}])
    @patch('app.fetchers.fetch_in_progress')
    @patch('app.fetchers.is_market_open_ist')
    def test_allowed(self, mock_market_open, mock_in_progress, mock_accounts, mock_session, mock_user):
        mock_market_open.return_value = True
        mock_in_progress.is_set.return_value = False
        mock_session.is_valid.return_value = True

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
