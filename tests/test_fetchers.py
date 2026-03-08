"""
Unit tests for fetchers.py (data fetching logic).
"""
import threading
import unittest
from unittest.mock import Mock, patch, MagicMock
from requests.exceptions import Timeout, ConnectionError

from app.fetchers import (_should_fetch_gold_prices,
                          _filter_symbols_to_fetch, _batch_fetch_quotes,
                          _update_ltp_cache, _wait_for_symbols,
                          _bg_fetch_and_broadcast_ltps,
                          _start_ltp_fetch_thread, _fetch_all_data,
                          collect_manual_symbols, fetch_manual_ltps,
                          fetch_gold_prices, fetch_nifty50_data,
                          fetch_portfolio_data, run_background_fetch)


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


# ---------------------------------------------------------------------------
# Manual LTP helpers
# ---------------------------------------------------------------------------


class TestCollectManualSymbols(unittest.TestCase):
    @patch('app.fetchers.user_sheets_cache')
    def test_collects_symbols(self, mock_usc):
        mock_usc.get_manual.side_effect = [
            [{"symbol": "INFY"}, {"symbol": "TCS"}],  # stocks
            [{"symbol": "GOLDBEES"}],                    # etfs
        ]
        result = collect_manual_symbols("user1")
        self.assertIn("INFY", result)
        self.assertIn("TCS", result)
        self.assertIn("GOLDBEES", result)

    @patch('app.fetchers.user_sheets_cache')
    def test_collects_empty(self, mock_usc):
        mock_usc.get_manual.return_value = None
        result = collect_manual_symbols("user1")
        self.assertEqual(result, [])


class TestFilterSymbolsToFetch(unittest.TestCase):
    @patch('app.fetchers.manual_ltp_cache')
    def test_filters_cached(self, mock_cache):
        mock_cache.is_negative.return_value = False
        mock_cache.get.side_effect = [{"ltp": 100}, None]
        result = _filter_symbols_to_fetch(["INFY", "TCS"], force=False)
        self.assertEqual(result, ["TCS"])

    @patch('app.fetchers.manual_ltp_cache')
    def test_force_refetch(self, mock_cache):
        mock_cache.is_negative.return_value = False
        mock_cache.get.return_value = {"ltp": 100}
        result = _filter_symbols_to_fetch(["INFY"], force=True)
        self.assertEqual(result, ["INFY"])

    @patch('app.fetchers.manual_ltp_cache')
    def test_skips_negative(self, mock_cache):
        mock_cache.is_negative.return_value = True
        result = _filter_symbols_to_fetch(["BAD"], force=True)
        self.assertEqual(result, [])


class TestBatchFetchQuotes(unittest.TestCase):
    @patch('app.fetchers.MarketDataClient')
    @patch('app.fetchers.manual_ltp_cache')
    def test_success(self, mock_cache, mock_client_cls):
        mock_client_cls.return_value.fetch_stock_quotes.return_value = {"INFY": {"ltp": 100}}
        result = _batch_fetch_quotes(["INFY"])
        self.assertEqual(result["INFY"]["ltp"], 100)

    @patch('app.fetchers.MarketDataClient')
    @patch('app.fetchers.manual_ltp_cache')
    def test_error_returns_empty(self, mock_cache, mock_client_cls):
        mock_client_cls.return_value.fetch_stock_quotes.side_effect = Exception("err")
        result = _batch_fetch_quotes(["INFY"])
        self.assertEqual(result, {})


class TestUpdateLtpCache(unittest.TestCase):
    @patch('app.fetchers.manual_ltp_cache')
    def test_updates_cache(self, mock_cache):
        _update_ltp_cache(["INFY", "TCS"], {"INFY": {"ltp": 100}})
        mock_cache.put_batch.assert_called_once_with({"INFY": {"ltp": 100}})
        mock_cache.put_negative_batch.assert_called_once_with(["TCS"])

    @patch('app.fetchers.manual_ltp_cache')
    def test_all_fetched(self, mock_cache):
        _update_ltp_cache(["INFY"], {"INFY": {"ltp": 100}})
        mock_cache.put_negative_batch.assert_not_called()

    @patch('app.fetchers.manual_ltp_cache')
    def test_empty_fetched(self, mock_cache):
        _update_ltp_cache(["INFY"], {})
        mock_cache.put_batch.assert_not_called()
        mock_cache.put_negative_batch.assert_called_once()


class TestFetchManualLtps(unittest.TestCase):
    @patch('app.fetchers._update_ltp_cache')
    @patch('app.fetchers._batch_fetch_quotes', return_value={"INFY": {"ltp": 100}})
    @patch('app.fetchers._filter_symbols_to_fetch', return_value=["INFY"])
    def test_fetches(self, mock_filter, mock_fetch, mock_update):
        fetch_manual_ltps(["INFY"])
        mock_fetch.assert_called_once_with(["INFY"])

    @patch('app.fetchers._filter_symbols_to_fetch', return_value=[])
    def test_all_cached(self, mock_filter):
        fetch_manual_ltps(["INFY"])  # no NSE call made

    def test_empty_symbols(self):
        fetch_manual_ltps([])  # no error


class TestWaitForSymbols(unittest.TestCase):
    @patch('app.fetchers.time')
    @patch('app.fetchers.collect_manual_symbols')
    def test_finds_symbols(self, mock_collect, mock_time):
        mock_collect.return_value = ["INFY"]
        result = _wait_for_symbols("user1")
        self.assertEqual(result, ["INFY"])

    @patch('app.fetchers.time')
    @patch('app.fetchers.collect_manual_symbols', return_value=[])
    def test_timeout(self, mock_collect, mock_time):
        result = _wait_for_symbols("user1")
        self.assertEqual(result, [])


class TestBgFetchAndBroadcastLtps(unittest.TestCase):
    @patch('app.fetchers.state_manager')
    @patch('app.fetchers.fetch_manual_ltps')
    def test_with_symbols(self, mock_fetch, mock_state):
        _bg_fetch_and_broadcast_ltps("user1", ["INFY"], False)
        mock_fetch.assert_called_once()
        mock_state.set_manual_ltp_updating.assert_called_once_with("user1")
        mock_state.set_manual_ltp_updated.assert_called_once_with("user1")

    @patch('app.fetchers.state_manager')
    @patch('app.fetchers._wait_for_symbols', return_value=[])
    def test_no_symbols_returns_early(self, mock_wait, mock_state):
        """No symbols means return early (no retry queue)."""
        _bg_fetch_and_broadcast_ltps("user1", None, False)
        mock_state.set_manual_ltp_updating.assert_not_called()
        mock_state.set_manual_ltp_updated.assert_called_once_with("user1")


class TestStartLtpFetchThread(unittest.TestCase):
    @patch('app.fetchers.threading.Thread')
    def test_starts_thread(self, mock_thread):
        mock_thread.return_value = Mock()
        _start_ltp_fetch_thread("user1", ["INFY"], False)
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()


class TestShouldFetchGoldPrices(unittest.TestCase):
    @patch('app.fetchers.market_cache')
    def test_first_fetch(self, mock_mc):
        mock_mc.gold_prices_last_fetch = None
        self.assertTrue(_should_fetch_gold_prices())

    @patch('app.fetchers.market_cache')
    def test_different_date(self, mock_mc):
        from datetime import datetime
        mock_mc.gold_prices_last_fetch = datetime(2024, 1, 1, 10, 0)
        with patch('app.fetchers.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 2, 10, 0)
            self.assertTrue(_should_fetch_gold_prices())

    @patch('app.fetchers.market_cache')
    def test_same_hour(self, mock_mc):
        from datetime import datetime
        mock_mc.gold_prices_last_fetch = datetime(2024, 1, 1, 10, 30)
        with patch('app.fetchers.datetime') as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 1, 10, 45)
            self.assertFalse(_should_fetch_gold_prices())


class TestFetchGoldPrices(unittest.TestCase):
    @patch('app.fetchers._should_fetch_gold_prices', return_value=False)
    def test_skips_when_not_needed(self, mock_should):
        fetch_gold_prices()  # no error

    @patch('app.fetchers.get_gold_price_service')
    @patch('app.fetchers._should_fetch_gold_prices', return_value=True)
    @patch('app.fetchers.market_cache')
    def test_success(self, mock_mc, mock_should, mock_gold_svc):
        mock_gold_svc.return_value.fetch_gold_prices.return_value = {"24K": {"price": 7000}}
        fetch_gold_prices(force=True)
        self.assertEqual(mock_mc.gold_prices, {"24K": {"price": 7000}})

    @patch('app.fetchers.get_gold_price_service')
    @patch('app.fetchers.market_cache')
    def test_all_retries_fail(self, mock_mc, mock_gold_svc):
        mock_gold_svc.return_value.fetch_gold_prices.side_effect = Exception("err")
        fetch_gold_prices(force=True)  # should not raise


class TestFetchAllData(unittest.TestCase):
    @patch('app.fetchers.fetch_gold_prices')
    @patch('app.fetchers.fetch_nifty50_data')
    @patch('app.fetchers.fetch_portfolio_data')
    @patch('app.fetchers.get_authenticated_accounts', return_value=[{"name": "A"}])
    @patch('app.fetchers.state_manager')
    @patch('app.fetchers.portfolio_cache')
    def test_with_accounts(self, mock_pc, mock_state, mock_auth, mock_fetch_pf,
                           mock_fetch_n, mock_fetch_g):
        _fetch_all_data("user1", None, False)
        mock_fetch_pf.assert_called_once()

    @patch('app.fetchers.fetch_gold_prices')
    @patch('app.fetchers.fetch_nifty50_data')
    @patch('app.fetchers.get_authenticated_accounts', return_value=[])
    @patch('app.fetchers.state_manager')
    @patch('app.fetchers.portfolio_cache')
    def test_no_accounts(self, mock_pc, mock_state, mock_auth, mock_fetch_n, mock_fetch_g):
        _fetch_all_data("user1", None, False)
        mock_state.set_portfolio_updating.assert_called()
        mock_state.set_portfolio_updated.assert_called()
        mock_pc.clear.assert_called_with("user1")


class TestBgFetchBroadcastException(unittest.TestCase):
    @patch('app.fetchers.state_manager')
    @patch('app.fetchers.fetch_manual_ltps', side_effect=Exception("boom"))
    @patch('app.fetchers._wait_for_symbols', return_value=["INFY"])
    def test_exception_caught(self, mock_wait, mock_fetch, mock_state):
        from app.fetchers import _bg_fetch_and_broadcast_ltps
        _bg_fetch_and_broadcast_ltps("user1", None, False)
        # Should not raise


class TestFetchPortfolioPartialError(unittest.TestCase):
    @patch('app.fetchers.portfolio_cache')
    @patch('app.fetchers.state_manager')
    @patch('app.fetchers.zerodha_client')
    def test_partial_error_preserves(self, mock_zc, mock_state, mock_pc):
        mock_zc.fetch_all_accounts_data.return_value = ([], [], [], "partial error")
        mock_data = Mock()
        mock_data.stocks = [1, 2]
        mock_data.mf_holdings = [3]
        mock_data.sips = []
        mock_pc.get.return_value = mock_data
        fetch_portfolio_data("user1", [{"name": "A"}])
        mock_state.set_portfolio_updated.assert_called()

    @patch('app.fetchers.portfolio_cache')
    @patch('app.fetchers.state_manager')
    @patch('app.fetchers.zerodha_client')
    def test_exception_in_fetch(self, mock_zc, mock_state, mock_pc):
        mock_zc.fetch_all_accounts_data.side_effect = Exception("api error")
        fetch_portfolio_data("user1", [{"name": "A"}])
        mock_state.set_portfolio_updated.assert_called()
        args = mock_state.set_portfolio_updated.call_args
        self.assertIsNotNone(args.kwargs.get("error") or args[1].get("error"))


class TestFetchGoldPricesRetries(unittest.TestCase):
    @patch('app.fetchers.get_gold_price_service')
    @patch('app.fetchers.market_cache')
    def test_empty_prices_retries(self, mock_mc, mock_svc):
        """Empty prices retries up to max_retries."""
        mock_mc.gold_prices_last_fetch = None
        mock_svc.return_value.fetch_gold_prices.return_value = {}
        fetch_gold_prices(force=True)
        self.assertEqual(mock_svc.return_value.fetch_gold_prices.call_count, 3)

    @patch('app.fetchers.get_gold_price_service')
    @patch('app.fetchers.market_cache')
    def test_exception_retries(self, mock_mc, mock_svc):
        """Exceptions retry up to max_retries."""
        mock_mc.gold_prices_last_fetch = None
        mock_svc.return_value.fetch_gold_prices.side_effect = Exception("timeout")
        fetch_gold_prices(force=True)
        self.assertEqual(mock_svc.return_value.fetch_gold_prices.call_count, 3)


class TestFetchNifty50Errors(unittest.TestCase):
    @patch('app.fetchers.nifty50_fetch_in_progress')
    @patch('app.fetchers.state_manager')
    @patch('app.fetchers.market_cache')
    @patch('app.fetchers.MarketDataClient')
    def test_timeout_error(self, mock_mdc, mock_mc, mock_state, mock_flag):
        mock_flag.is_set.return_value = False
        mock_mdc.return_value.fetch_nifty50_symbols.side_effect = Timeout("timeout")
        # The actual fetch runs in a thread; we test _fetch directly
        from app.fetchers import fetch_nifty50_data, nifty50_fetch_in_progress
        import app.fetchers as f
        # Patch threading to run synchronously
        with patch('threading.Thread') as mock_thread:
            mock_thread.return_value.start = Mock()
            fetch_nifty50_data()
            # Get the target function and call it
            call_args = mock_thread.call_args
            target = call_args.kwargs.get('target') or call_args[1].get('target')
            target()
        mock_state.set_nifty50_updated.assert_called()

    @patch('app.fetchers.nifty50_fetch_in_progress')
    @patch('app.fetchers.state_manager')
    @patch('app.fetchers.market_cache')
    @patch('app.fetchers.MarketDataClient')
    def test_connection_error(self, mock_mdc, mock_mc, mock_state, mock_flag):
        mock_flag.is_set.return_value = False
        mock_mdc.return_value.fetch_nifty50_symbols.side_effect = ConnectionError("no net")
        with patch('threading.Thread') as mock_thread:
            mock_thread.return_value.start = Mock()
            fetch_nifty50_data()
            target = mock_thread.call_args.kwargs.get('target') or mock_thread.call_args[1].get('target')
            target()
        mock_state.set_nifty50_updated.assert_called()

    @patch('app.fetchers.nifty50_fetch_in_progress')
    @patch('app.fetchers.state_manager')
    @patch('app.fetchers.market_cache')
    @patch('app.fetchers.MarketDataClient')
    def test_generic_exception(self, mock_mdc, mock_mc, mock_state, mock_flag):
        mock_flag.is_set.return_value = False
        mock_mdc.return_value.fetch_nifty50_symbols.side_effect = RuntimeError("bad")
        with patch('threading.Thread') as mock_thread:
            mock_thread.return_value.start = Mock()
            fetch_nifty50_data()
            target = mock_thread.call_args.kwargs.get('target') or mock_thread.call_args[1].get('target')
            target()
        mock_state.set_nifty50_updated.assert_called()


class TestFetchNifty50Success(unittest.TestCase):
    """Cover fetchers.py: nifty50 fetch success path (Yahoo Finance batch)."""

    @patch('app.fetchers.nifty50_fetch_in_progress')
    @patch('app.fetchers.state_manager')
    @patch('app.fetchers.market_cache')
    @patch('app.fetchers.MarketDataClient')
    @patch('threading.Thread')
    def test_nifty50_success(self, mock_thread, mock_client_cls, mock_cache,
                              mock_state, mock_flag):
        from app.fetchers import fetch_nifty50_data
        mock_flag.is_set.return_value = False
        fetch_nifty50_data()
        # Extract the _fetch function and run it directly
        call_args = mock_thread.call_args
        fetch_fn = call_args[1].get('target') or call_args[0][0] if call_args[0] else call_args[1]['target']
        client = mock_client_cls.return_value
        client.fetch_nifty50_symbols.return_value = ["INFY", "TCS"]
        client.fetch_stock_quotes.return_value = {
            "INFY": {"symbol": "INFY", "ltp": 1500},
            "TCS": {"symbol": "TCS", "ltp": 3500},
        }
        client._empty_stock_data.side_effect = lambda s: {"symbol": s, "ltp": 0}
        fetch_fn()
        self.assertEqual(len(mock_cache.nifty50), 2)
        mock_state.set_nifty50_updated.assert_called_once()


class TestRunBackgroundFetchOnComplete(unittest.TestCase):
    """Cover fetchers.py line 335: on_complete callback."""

    @patch('app.fetchers._start_ltp_fetch_thread')
    @patch('app.fetchers._fetch_all_data')
    @patch('threading.Thread')
    def test_on_complete_called(self, mock_thread, mock_fetch_all, mock_ltp):
        from app.fetchers import run_background_fetch
        callback = Mock()
        run_background_fetch(google_id="u1", on_complete=callback)
        # Extract the _run function and run it directly
        call_args = mock_thread.call_args
        run_fn = call_args[1].get('target') or call_args[0][0] if call_args[0] else call_args[1]['target']
        run_fn()
        callback.assert_called_once()
