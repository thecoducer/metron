"""Unit tests for app.api.market_data – MarketDataClient."""

import threading
import unittest
from unittest.mock import Mock, patch

from requests.exceptions import ConnectionError, RequestException, Timeout

from app.api.market_data import MarketDataClient


class TestCreateSession(unittest.TestCase):
    @patch("app.api.market_data.requests.Session")
    def test_success(self, mock_session_cls):
        client = MarketDataClient()
        sess = client._create_session()
        self.assertIsNotNone(sess)
        mock_session_cls.return_value.get.assert_called_once()

    @patch("app.api.market_data.logger")
    @patch("app.api.market_data.requests.Session")
    def test_timeout(self, mock_session_cls, mock_logger):
        mock_session_cls.return_value.get.side_effect = Timeout("slow")
        client = MarketDataClient()
        with self.assertRaises(Timeout):
            client._create_session()
        mock_logger.warning.assert_called_once()
        self.assertIn("slow to respond", mock_logger.warning.call_args[0][0])

    @patch("app.api.market_data.logger")
    @patch("app.api.market_data.requests.Session")
    def test_connection_error(self, mock_session_cls, mock_logger):
        mock_session_cls.return_value.get.side_effect = ConnectionError("down")
        client = MarketDataClient()
        with self.assertRaises(ConnectionError):
            client._create_session()
        mock_logger.warning.assert_called_once()
        self.assertIn("Cannot connect", mock_logger.warning.call_args[0][0])

    @patch("app.api.market_data.logger")
    @patch("app.api.market_data.requests.Session")
    def test_generic_error(self, mock_session_cls, mock_logger):
        mock_session_cls.return_value.get.side_effect = RuntimeError("bang")
        client = MarketDataClient()
        with self.assertRaises(RuntimeError):
            client._create_session()
        mock_logger.error.assert_called_once()
        self.assertIn("Error creating NSE session", mock_logger.error.call_args[0][0])


class TestFetchNifty50Symbols(unittest.TestCase):
    @patch("app.api.market_data.logger")
    @patch.object(MarketDataClient, "_create_session")
    def test_success(self, mock_create, mock_logger):
        mock_sess = Mock()
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": [{"symbol": "NIFTY 50"}, {"symbol": "INFY"}, {"symbol": "TCS"}]}
        mock_sess.get.return_value = mock_resp
        mock_create.return_value = mock_sess

        client = MarketDataClient()
        result = client.fetch_nifty50_symbols()
        self.assertEqual(result, ["INFY", "TCS"])
        mock_logger.error.assert_not_called()

    @patch("app.api.market_data.logger")
    @patch.object(MarketDataClient, "_create_session")
    def test_non_200(self, mock_create, mock_logger):
        mock_sess = Mock()
        mock_resp = Mock()
        mock_resp.status_code = 503
        mock_sess.get.return_value = mock_resp
        mock_create.return_value = mock_sess

        client = MarketDataClient()
        result = client.fetch_nifty50_symbols()
        self.assertEqual(result, [])
        mock_logger.warning.assert_called_once()
        self.assertIn("HTTP", mock_logger.warning.call_args[0][0])

    @patch("app.api.market_data.logger")
    @patch.object(MarketDataClient, "_create_session")
    def test_timeout(self, mock_create, mock_logger):
        mock_sess = Mock()
        mock_sess.get.side_effect = Timeout("slow")
        mock_create.return_value = mock_sess

        client = MarketDataClient()
        result = client.fetch_nifty50_symbols()
        self.assertEqual(result, [])
        mock_logger.warning.assert_called_once()
        self.assertIn("timeout", mock_logger.warning.call_args[0][0].lower())

    @patch("app.api.market_data.logger")
    @patch.object(MarketDataClient, "_create_session")
    def test_connection_error(self, mock_create, mock_logger):
        mock_sess = Mock()
        mock_sess.get.side_effect = ConnectionError("down")
        mock_create.return_value = mock_sess

        client = MarketDataClient()
        result = client.fetch_nifty50_symbols()
        self.assertEqual(result, [])
        mock_logger.warning.assert_called_once()
        self.assertIn("Cannot connect", mock_logger.warning.call_args[0][0])

    @patch("app.api.market_data.logger")
    @patch.object(MarketDataClient, "_create_session", side_effect=Exception("fail"))
    def test_generic_error(self, mock_create, mock_logger):
        client = MarketDataClient()
        result = client.fetch_nifty50_symbols()
        self.assertEqual(result, [])
        mock_logger.error.assert_called_once()
        self.assertIn("Error fetching", mock_logger.error.call_args[0][0])


class TestFetchStockQuote(unittest.TestCase):
    def setUp(self):
        self.client = MarketDataClient()

    @patch("app.api.market_data.logger")
    @patch("app.api.market_data.time.sleep")
    @patch("app.api.market_data.requests.get")
    def test_success(self, mock_get, mock_sleep, mock_logger):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "regularMarketPrice": 1500,
                            "previousClose": 1490,
                            "shortName": "Infosys",
                        },
                        "indicators": {
                            "quote": [{"open": [1490.0], "high": [1510.0], "low": [1480.0], "close": [1500.0]}]
                        },
                    }
                ]
            }
        }
        mock_get.return_value = mock_resp
        result = self.client.fetch_stock_quote("INFY")
        self.assertEqual(result["ltp"], 1500)
        self.assertEqual(result["symbol"], "INFY")
        self.assertEqual(result["name"], "Infosys")
        # Should log info for fetch start and success
        info_calls = [str(c) for c in mock_logger.info.call_args_list]
        self.assertTrue(any("Fetching stock quote" in s for s in info_calls))
        self.assertTrue(any("ltp=" in s for s in info_calls))
        mock_logger.error.assert_not_called()

    @patch("app.api.market_data.logger")
    @patch("app.api.market_data.time.sleep")
    @patch("app.api.market_data.requests.get")
    def test_non_200_after_retries(self, mock_get, mock_sleep, mock_logger):
        mock_resp = Mock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp
        result = self.client.fetch_stock_quote("BAD")
        self.assertEqual(result["ltp"], 0)
        # Should log warnings for retries + final failure
        self.assertTrue(mock_logger.warning.called)
        warning_msgs = [str(c) for c in mock_logger.warning.call_args_list]
        self.assertTrue(any("HTTP" in s or "No LTP" in s for s in warning_msgs))

    @patch("app.api.market_data.logger")
    @patch("app.api.market_data.time.sleep")
    @patch("app.api.market_data.requests.get", side_effect=Timeout("slow"))
    def test_timeout(self, mock_get, mock_sleep, mock_logger):
        result = self.client.fetch_stock_quote("INFY")
        self.assertEqual(result["ltp"], 0)
        # Should log warnings for timeout retries
        self.assertTrue(mock_logger.warning.called)
        warning_msgs = [str(c) for c in mock_logger.warning.call_args_list]
        self.assertTrue(any("Timeout" in s or "timeout" in s for s in warning_msgs))

    @patch("app.api.market_data.logger")
    @patch("app.api.market_data.time.sleep")
    @patch("app.api.market_data.requests.get", side_effect=ConnectionError("err"))
    def test_connection_error(self, mock_get, mock_sleep, mock_logger):
        result = self.client.fetch_stock_quote("INFY")
        self.assertEqual(result["ltp"], 0)
        self.assertTrue(mock_logger.warning.called)
        warning_msgs = [str(c) for c in mock_logger.warning.call_args_list]
        self.assertTrue(any("Connection error" in s or "No LTP" in s for s in warning_msgs))

    @patch("app.api.market_data.logger")
    @patch("app.api.market_data.requests.get", side_effect=RequestException("err"))
    def test_request_exception(self, mock_get, mock_logger):
        result = self.client.fetch_stock_quote("INFY")
        self.assertEqual(result["ltp"], 0)
        self.assertTrue(mock_logger.warning.called)
        warning_msgs = [str(c) for c in mock_logger.warning.call_args_list]
        self.assertTrue(any("Request failed" in s or "No LTP" in s for s in warning_msgs))

    @patch("app.api.market_data.logger")
    @patch("app.api.market_data.requests.get", side_effect=RuntimeError("bang"))
    def test_generic_exception(self, mock_get, mock_logger):
        result = self.client.fetch_stock_quote("INFY")
        self.assertEqual(result["ltp"], 0)
        # Unexpected errors should use logger.error with exc_info
        mock_logger.error.assert_called()
        error_call = mock_logger.error.call_args
        self.assertIn("Unexpected error", error_call[0][0])
        self.assertTrue(error_call[1].get("exc_info"))

    @patch("app.api.market_data.logger")
    @patch("app.api.market_data.time.sleep")
    @patch("app.api.market_data.requests.get")
    def test_rate_limit_retries(self, mock_get, mock_sleep, mock_logger):
        rate_resp = Mock(status_code=429)
        ok_resp = Mock(status_code=200)
        ok_resp.json.return_value = {
            "chart": {
                "result": [{"meta": {"regularMarketPrice": 100, "previousClose": 95}, "indicators": {"quote": [{}]}}]
            }
        }
        mock_get.side_effect = [rate_resp, ok_resp]
        result = self.client.fetch_stock_quote("INFY")
        self.assertEqual(result["ltp"], 100)
        self.assertEqual(mock_get.call_count, 2)
        # Should log warning about rate limiting
        warning_msgs = [str(c) for c in mock_logger.warning.call_args_list]
        self.assertTrue(any("rate-limited" in s for s in warning_msgs))

    @patch("app.api.market_data.logger")
    @patch("app.api.market_data.time.sleep")
    @patch("app.api.market_data.requests.get")
    def test_empty_chart_logs_warning(self, mock_get, mock_sleep, mock_logger):
        mock_resp = Mock(status_code=200)
        mock_resp.json.return_value = {"chart": {"result": []}}
        mock_get.return_value = mock_resp
        result = self.client.fetch_stock_quote("INFY")
        self.assertEqual(result["ltp"], 0)
        warning_msgs = [str(c) for c in mock_logger.warning.call_args_list]
        self.assertTrue(any("empty chart" in s for s in warning_msgs))

    @patch("app.api.market_data.logger")
    @patch("app.api.market_data.time.sleep")
    @patch("app.api.market_data.requests.get")
    def test_all_429_exhausts_retries(self, mock_get, mock_sleep, mock_logger):
        """When all attempts get 429, retries exhaust and warning logged."""
        mock_get.return_value = Mock(status_code=429)
        result = self.client.fetch_stock_quote("INFY")
        self.assertEqual(result["ltp"], 0)
        warning_msgs = [str(c) for c in mock_logger.warning.call_args_list]
        self.assertTrue(any("exhausted" in s for s in warning_msgs))


class TestFetchStockQuotes(unittest.TestCase):
    def setUp(self):
        self.client = MarketDataClient()

    @patch("app.api.market_data.logger")
    @patch.object(MarketDataClient, "_fetch_yf_stock_quote")
    def test_batch_success(self, mock_quote, mock_logger):
        mock_quote.side_effect = [
            {"ltp": 100, "symbol": "A"},
            {"ltp": 200, "symbol": "B"},
        ]
        result = self.client.fetch_stock_quotes(["A", "B"])
        self.assertEqual(len(result), 2)
        # Should log start and completion at info level
        info_msgs = [str(c) for c in mock_logger.info.call_args_list]
        self.assertTrue(any("batch fetch" in s.lower() for s in info_msgs))
        self.assertTrue(any("done" in s.lower() for s in info_msgs))

    def test_empty_symbols(self):
        result = self.client.fetch_stock_quotes([])
        self.assertEqual(result, {})

    @patch("app.api.market_data.logger")
    @patch.object(MarketDataClient, "_fetch_yf_stock_quote")
    def test_cancel_event(self, mock_quote, mock_logger):
        cancel = threading.Event()
        cancel.set()  # cancel immediately
        result = self.client.fetch_stock_quotes(["A", "B"], cancel=cancel)
        self.assertEqual(result, {})

    @patch("app.api.market_data.logger")
    @patch.object(MarketDataClient, "_fetch_yf_stock_quote")
    def test_with_timeout_override(self, mock_quote, mock_logger):
        mock_quote.return_value = {"ltp": 100, "symbol": "A"}
        result = self.client.fetch_stock_quotes(["A"], timeout=5)
        self.assertEqual(len(result), 1)
        # Timeout should be restored
        self.assertEqual(self.client.timeout, MarketDataClient().timeout)

    @patch("app.api.market_data.logger")
    @patch.object(MarketDataClient, "_fetch_yf_stock_quote")
    def test_failed_symbols_logged(self, mock_quote, mock_logger):
        mock_quote.return_value = {"ltp": 0, "symbol": "BAD"}  # ltp=0 → failed
        result = self.client.fetch_stock_quotes(["BAD"])
        self.assertEqual(result, {})
        info_msgs = [str(c) for c in mock_logger.info.call_args_list]
        self.assertTrue(any("No LTP" in s for s in info_msgs))

    @patch("app.api.market_data.logger")
    @patch.object(MarketDataClient, "_fetch_yf_stock_quote")
    def test_future_exception_logged_as_error(self, mock_quote, mock_logger):
        """Exceptions raised inside futures are logged at error level."""
        mock_quote.side_effect = RuntimeError("boom")
        result = self.client.fetch_stock_quotes(["BAD"])
        self.assertEqual(result, {})
        mock_logger.error.assert_called()
        error_msgs = [str(c) for c in mock_logger.error.call_args_list]
        self.assertTrue(any("fetch error" in s for s in error_msgs))


class TestFetchMarketIndices(unittest.TestCase):
    @patch("app.api.market_data.logger")
    @patch.object(MarketDataClient, "_fetch_yf_index")
    def test_returns_all_keys(self, mock_yf, mock_logger):
        client = MarketDataClient()
        result = client.fetch_market_indices()
        self.assertIn("nifty50", result)
        self.assertIn("sensex", result)
        self.assertIn("gold", result)
        # Should log start and summary at info level
        info_msgs = [str(c) for c in mock_logger.info.call_args_list]
        self.assertTrue(any("Fetching market indices" in s for s in info_msgs))
        self.assertTrue(any("fetched" in s.lower() for s in info_msgs))


class TestFetchYfIndex(unittest.TestCase):
    @patch("app.api.market_data.logger")
    @patch("app.api.market_data.requests.get")
    def test_success(self, mock_get, mock_logger):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "chart": {
                "result": [
                    {
                        "meta": {"regularMarketPrice": 22000, "previousClose": 21900},
                        "indicators": {"quote": [{"close": [21950.0, 21975.0, 22000.0]}]},
                    }
                ]
            }
        }
        mock_get.return_value = mock_resp

        client = MarketDataClient()
        result = {}
        client._fetch_yf_index(result, "nifty50", "%5ENSEI", "NIFTY 50")
        self.assertEqual(result["nifty50"]["value"], 22000)
        self.assertAlmostEqual(result["nifty50"]["change"], 100)
        # Debug log for successful index fetch
        self.assertTrue(mock_logger.debug.called)
        mock_logger.warning.assert_not_called()
        mock_logger.error.assert_not_called()

    @patch("app.api.market_data.logger")
    @patch("app.api.market_data.requests.get")
    def test_non_200(self, mock_get, mock_logger):
        mock_resp = Mock()
        mock_resp.status_code = 503
        mock_get.return_value = mock_resp

        client = MarketDataClient()
        result = {"nifty50": client._empty_index_data("NIFTY 50")}
        client._fetch_yf_index(result, "nifty50", "%5ENSEI", "NIFTY 50")
        self.assertEqual(result["nifty50"]["value"], 0)
        mock_logger.warning.assert_called_once()
        self.assertIn("HTTP", mock_logger.warning.call_args[0][0])

    @patch("app.api.market_data.logger")
    @patch("app.api.market_data.requests.get", side_effect=Timeout("slow"))
    def test_timeout(self, mock_get, mock_logger):
        client = MarketDataClient()
        result = {"nifty50": client._empty_index_data("NIFTY 50")}
        client._fetch_yf_index(result, "nifty50", "%5ENSEI", "NIFTY 50")
        self.assertEqual(result["nifty50"]["value"], 0)
        mock_logger.warning.assert_called_once()
        self.assertIn("Timeout", mock_logger.warning.call_args[0][0])

    @patch("app.api.market_data.logger")
    @patch("app.api.market_data.requests.get", side_effect=ConnectionError("err"))
    def test_connection_error(self, mock_get, mock_logger):
        client = MarketDataClient()
        result = {"nifty50": client._empty_index_data("NIFTY 50")}
        client._fetch_yf_index(result, "nifty50", "%5ENSEI", "NIFTY 50")
        self.assertEqual(result["nifty50"]["value"], 0)
        mock_logger.warning.assert_called_once()
        self.assertIn("Connection error", mock_logger.warning.call_args[0][0])

    @patch("app.api.market_data.logger")
    @patch("app.api.market_data.requests.get", side_effect=ValueError("parse"))
    def test_generic_error(self, mock_get, mock_logger):
        client = MarketDataClient()
        result = {"nifty50": client._empty_index_data("NIFTY 50")}
        client._fetch_yf_index(result, "nifty50", "%5ENSEI", "NIFTY 50")
        self.assertEqual(result["nifty50"]["value"], 0)
        # Generic exceptions now logged at error with exc_info
        mock_logger.error.assert_called_once()
        self.assertIn("Unexpected error", mock_logger.error.call_args[0][0])

    @patch("app.api.market_data.logger")
    @patch("app.api.market_data.requests.get")
    def test_empty_chart_result(self, mock_get, mock_logger):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"chart": {"result": []}}
        mock_get.return_value = mock_resp

        client = MarketDataClient()
        result = {"nifty50": client._empty_index_data("NIFTY 50")}
        client._fetch_yf_index(result, "nifty50", "%5ENSEI", "NIFTY 50")
        self.assertEqual(result["nifty50"]["value"], 0)
        mock_logger.warning.assert_called_once()
        self.assertIn("empty chart", mock_logger.warning.call_args[0][0])


class TestEmptyIndexData(unittest.TestCase):
    def test_fields(self):
        result = MarketDataClient._empty_index_data("TEST")
        self.assertEqual(result["name"], "TEST")
        self.assertEqual(result["value"], 0)
        self.assertEqual(result["chart"], [])


class TestEmptyStockData(unittest.TestCase):
    def test_fields(self):
        client = MarketDataClient()
        result = client._empty_stock_data("SYM")
        self.assertEqual(result["symbol"], "SYM")
        self.assertEqual(result["ltp"], 0)


class TestSymbolConversion(unittest.TestCase):
    def test_nse_to_yf(self):
        self.assertEqual(MarketDataClient._nse_to_yf_symbol("INFY"), "INFY.NS")
        self.assertEqual(MarketDataClient._nse_to_yf_symbol("M&M"), "M&M.NS")

    def test_yf_to_nse(self):
        self.assertEqual(MarketDataClient._yf_to_nse_symbol("INFY.NS"), "INFY")
        self.assertEqual(MarketDataClient._yf_to_nse_symbol("M&M.NS"), "M&M")
        self.assertEqual(MarketDataClient._yf_to_nse_symbol("INFY"), "INFY")


class TestParseYfChart(unittest.TestCase):
    def test_full_data(self):
        chart_data = {
            "meta": {
                "regularMarketPrice": 1500,
                "previousClose": 1490,
                "shortName": "Infosys",
            },
            "indicators": {"quote": [{"open": [1490.0], "high": [1510.0], "low": [1480.0], "close": [1500.0]}]},
        }
        result = MarketDataClient._parse_yf_chart("INFY", chart_data)
        self.assertEqual(result["symbol"], "INFY")
        self.assertEqual(result["name"], "Infosys")
        self.assertEqual(result["ltp"], 1500)
        self.assertAlmostEqual(result["change"], 10.0)
        self.assertEqual(result["open"], 1490.0)
        self.assertEqual(result["high"], 1510.0)
        self.assertEqual(result["low"], 1480.0)
        self.assertEqual(result["close"], 1490.0)

    def test_empty_meta(self):
        chart_data = {"meta": {}, "indicators": {"quote": [{}]}}
        result = MarketDataClient._parse_yf_chart("SYM", chart_data)
        self.assertEqual(result["ltp"], 0)
        self.assertEqual(result["name"], "SYM")

    def test_missing_indicators(self):
        chart_data = {"meta": {"regularMarketPrice": 100, "previousClose": 95}}
        result = MarketDataClient._parse_yf_chart("SYM", chart_data)
        self.assertEqual(result["ltp"], 100)
        self.assertEqual(result["open"], 0)


class TestFetchNseQuote(unittest.TestCase):
    """Tests for MarketDataClient.fetch_nse_quote."""

    def setUp(self):
        # Reset the shared session before each test so tests are isolated.
        MarketDataClient._nse_session = None

    def _make_client_with_session(self, session_mock):
        """Return a client whose _get_nse_session returns session_mock."""
        client = MarketDataClient()
        client._get_nse_session = Mock(return_value=session_mock)
        client._refresh_nse_session = Mock(return_value=session_mock)
        return client

    def _nse_response(self, ltp=1500.0, change=10.0, pchange=0.67, isin="INE009A01021"):
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "info": {"symbol": "INFY", "isin": isin},
            "priceInfo": {
                "lastPrice": ltp,
                "change": change,
                "pChange": pchange,
                "previousClose": ltp - change,
            },
        }
        return mock_resp

    def test_returns_ltp_and_isin(self):
        session = Mock()
        session.get.return_value = self._nse_response()
        client = self._make_client_with_session(session)

        result = client.fetch_nse_quote("INFY")

        self.assertIsNotNone(result)
        self.assertEqual(result["ltp"], 1500.0)
        self.assertEqual(result["isin"], "INE009A01021")
        self.assertEqual(result["symbol"], "INFY")

    def test_refreshes_session_on_403(self):
        fresh_session = Mock()
        fresh_session.get.return_value = self._nse_response()

        expired_session = Mock()
        expired_resp = Mock()
        expired_resp.status_code = 403
        expired_session.get.return_value = expired_resp

        client = MarketDataClient()
        client._get_nse_session = Mock(return_value=expired_session)
        client._refresh_nse_session = Mock(return_value=fresh_session)

        result = client.fetch_nse_quote("INFY")

        self.assertIsNotNone(result)
        client._refresh_nse_session.assert_called_once()

    def test_returns_none_on_non_200(self):
        session = Mock()
        resp = Mock()
        resp.status_code = 404
        session.get.return_value = resp
        client = self._make_client_with_session(session)

        self.assertIsNone(client.fetch_nse_quote("UNKNOWN"))

    def test_returns_none_when_ltp_zero(self):
        session = Mock()
        session.get.return_value = self._nse_response(ltp=0)
        client = self._make_client_with_session(session)

        self.assertIsNone(client.fetch_nse_quote("INFY"))

    def test_returns_none_on_timeout(self):
        session = Mock()
        session.get.side_effect = Timeout("slow")
        client = self._make_client_with_session(session)

        self.assertIsNone(client.fetch_nse_quote("INFY"))

    def test_returns_none_on_connection_error(self):
        session = Mock()
        session.get.side_effect = ConnectionError("down")
        client = self._make_client_with_session(session)

        self.assertIsNone(client.fetch_nse_quote("INFY"))

    def test_isin_uppercased_and_stripped(self):
        session = Mock()
        session.get.return_value = self._nse_response(isin="  ine009a01021  ")
        client = self._make_client_with_session(session)

        result = client.fetch_nse_quote("INFY")
        self.assertEqual(result["isin"], "INE009A01021")


if __name__ == "__main__":
    unittest.main()
