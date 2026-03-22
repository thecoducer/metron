"""Unit tests for app/api/nse_equity.py."""

import threading
import unittest
from unittest.mock import MagicMock, patch

from app.api.nse_equity import (
    NSEEquityCache,
    NSEEquityInfo,
    _parse_equity_csv,
)

# Mirrors the real NSE EQUITY_L.csv format: headers after the first column
# have a leading space (e.g. " ISIN NUMBER").
_SAMPLE_CSV = """\
SYMBOL,NAME OF COMPANY, SERIES, DATE OF LISTING, PAID UP VALUE, MARKET LOT, ISIN NUMBER, FACE VALUE
HDFCBANK,HDFC Bank Limited,EQ,19-NOV-1995,1,1,INE040A01034,1
INFY,Infosys Limited,EQ,11-AUG-1993,5,1,INE009A01021,5
TCS,Tata Consultancy Services Limited,EQ,25-AUG-2004,1,1,INE467B01029,1
RELIANCE,Reliance Industries Limited,EQ,29-NOV-1995,10,1,INE002A01018,10
,MISSING SYMBOL,EQ,01-JAN-2000,1,1,INE000X00001,1
NOSYMBOLISIN,NO ISIN CO,EQ,01-JAN-2000,1,1,,1
"""


class TestParseEquityCSV(unittest.TestCase):
    """Tests for _parse_equity_csv."""

    def test_parses_standard_rows(self):
        entries = _parse_equity_csv(_SAMPLE_CSV)
        symbols = {e.symbol for e in entries}
        self.assertIn("HDFCBANK", symbols)
        self.assertIn("INFY", symbols)
        self.assertIn("TCS", symbols)
        self.assertIn("RELIANCE", symbols)

    def test_skips_missing_symbol(self):
        entries = _parse_equity_csv(_SAMPLE_CSV)
        symbols = {e.symbol for e in entries}
        self.assertNotIn("", symbols)

    def test_skips_missing_isin(self):
        entries = _parse_equity_csv(_SAMPLE_CSV)
        symbols = {e.symbol for e in entries}
        self.assertNotIn("NOSYMBOLISIN", symbols)

    def test_symbol_uppercased(self):
        csv = (
            "SYMBOL,NAME OF COMPANY,SERIES,DATE OF LISTING,PAID UP VALUE,MARKET LOT,ISIN NUMBER,FACE VALUE\n"
            "hdfcbank,HDFC Bank Limited,EQ,,,1,INE040A01034,1\n"
        )
        entries = _parse_equity_csv(csv)
        self.assertEqual(entries[0].symbol, "HDFCBANK")

    def test_isin_uppercased(self):
        csv = "SYMBOL,NAME OF COMPANY,SERIES,DATE OF LISTING,PAID UP VALUE,MARKET LOT,ISIN NUMBER,FACE VALUE\nHDFCBANK,HDFC Bank Limited,EQ,,,1,ine040a01034,1\n"
        entries = _parse_equity_csv(csv)
        self.assertEqual(entries[0].isin, "INE040A01034")

    def test_company_name_preserved(self):
        entries = _parse_equity_csv(_SAMPLE_CSV)
        hdfc = next(e for e in entries if e.symbol == "HDFCBANK")
        self.assertEqual(hdfc.company_name, "HDFC Bank Limited")

    def test_series_captured(self):
        entries = _parse_equity_csv(_SAMPLE_CSV)
        hdfc = next(e for e in entries if e.symbol == "HDFCBANK")
        self.assertEqual(hdfc.series, "EQ")

    def test_empty_csv_returns_empty_list(self):
        header = "SYMBOL,NAME OF COMPANY,SERIES,DATE OF LISTING,PAID UP VALUE,MARKET LOT,ISIN NUMBER,FACE VALUE\n"
        self.assertEqual(_parse_equity_csv(header), [])


class TestNSEEquityCache(unittest.TestCase):
    """Tests for NSEEquityCache."""

    def _sample_entries(self):
        return [
            NSEEquityInfo(symbol="HDFCBANK", company_name="HDFC Bank Limited", isin="INE040A01034", series="EQ"),
            NSEEquityInfo(symbol="INFY", company_name="Infosys Limited", isin="INE009A01021", series="EQ"),
        ]

    def test_get_after_refresh(self):
        cache = NSEEquityCache()
        cache.refresh(self._sample_entries())
        info = cache.get("HDFCBANK")
        self.assertIsNotNone(info)
        self.assertEqual(info.company_name, "HDFC Bank Limited")
        self.assertEqual(info.isin, "INE040A01034")

    def test_get_case_insensitive(self):
        cache = NSEEquityCache()
        cache.refresh(self._sample_entries())
        self.assertIsNotNone(cache.get("hdfcbank"))
        self.assertIsNotNone(cache.get("Hdfcbank"))

    def test_miss_returns_none(self):
        cache = NSEEquityCache()
        cache.refresh(self._sample_entries())
        self.assertIsNone(cache.get("UNKNOWN"))

    def test_empty_cache_returns_none(self):
        cache = NSEEquityCache()
        self.assertIsNone(cache.get("HDFCBANK"))

    def test_is_populated_false_before_refresh(self):
        cache = NSEEquityCache()
        self.assertFalse(cache.is_populated)

    def test_is_populated_true_after_refresh(self):
        cache = NSEEquityCache()
        cache.refresh(self._sample_entries())
        self.assertTrue(cache.is_populated)

    def test_refresh_replaces_old_data(self):
        cache = NSEEquityCache()
        cache.refresh(self._sample_entries())
        cache.refresh(
            [
                NSEEquityInfo(
                    symbol="TCS", company_name="Tata Consultancy Services Limited", isin="INE467B01029", series="EQ"
                )
            ]
        )
        self.assertIsNone(cache.get("HDFCBANK"))
        self.assertIsNotNone(cache.get("TCS"))

    def test_status_before_refresh(self):
        cache = NSEEquityCache()
        status = cache.status
        self.assertEqual(status["last_run"], "never")
        self.assertEqual(status["entries"], 0)

    def test_status_after_refresh(self):
        cache = NSEEquityCache()
        cache.refresh(self._sample_entries())
        status = cache.status
        self.assertNotEqual(status["last_run"], "never")
        self.assertEqual(status["entries"], 2)

    def test_thread_safe_concurrent_access(self):
        cache = NSEEquityCache()
        errors = []

        def worker(symbol):
            try:
                cache.refresh([NSEEquityInfo(symbol=symbol, company_name="Co", isin=f"IN{symbol}", series="EQ")])
                _ = cache.get(symbol)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(f"SYM{i}",)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])


class TestFetchAndCacheNSEEquity(unittest.TestCase):
    """Tests for fetch_and_cache_nse_equity (mocked HTTP)."""

    @patch("app.api.nse_equity.requests.get")
    def test_successful_fetch_populates_cache(self, mock_get):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.content = _SAMPLE_CSV.encode()
        mock_get.return_value = resp

        cache = NSEEquityCache()
        with patch("app.api.nse_equity.nse_equity_cache", cache):
            from app.api.nse_equity import fetch_and_cache_nse_equity as _fetch

            result = _fetch()

        self.assertTrue(result)
        self.assertTrue(cache.is_populated)

    @patch("app.api.nse_equity.requests.get")
    def test_network_error_returns_false(self, mock_get):
        mock_get.side_effect = ConnectionError("timeout")

        from app.api.nse_equity import fetch_and_cache_nse_equity as _fetch

        result = _fetch()
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
