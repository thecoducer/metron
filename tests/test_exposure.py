"""Unit tests for the company exposure analysis module (app/api/exposure.py)."""

import threading
import unittest
from unittest.mock import MagicMock, patch

from app.api.exposure import (
    CompanyHolding,
    ExposureCache,
    ExposureResult,
    _batch_fetch_holdings,
    _current_value,
    _display_name,
    _fetch_holdings,
    _gather_raw_entries,
    _is_non_equity,
    _merge_similar_sectors,
    _normalize_name,
    _pick_display_name,
    build_exposure_data,
)


class TestCurrentValue(unittest.TestCase):
    """Tests for _current_value helper."""

    def test_basic_multiplication(self):
        holding = {"quantity": 10.0, "last_price": 250.0}
        self.assertAlmostEqual(_current_value(holding), 2500.0)

    def test_zero_quantity(self):
        holding = {"quantity": 0, "last_price": 100.0}
        self.assertAlmostEqual(_current_value(holding), 0.0)

    def test_zero_price(self):
        holding = {"quantity": 5, "last_price": 0}
        self.assertAlmostEqual(_current_value(holding), 0.0)

    def test_missing_fields(self):
        self.assertAlmostEqual(_current_value({}), 0.0)

    def test_none_fields(self):
        holding = {"quantity": None, "last_price": None}
        self.assertAlmostEqual(_current_value(holding), 0.0)

    def test_fractional_units(self):
        holding = {"quantity": 3.5, "last_price": 100.0}
        self.assertAlmostEqual(_current_value(holding), 350.0)


class TestNormalizeName(unittest.TestCase):
    """Tests for _normalize_name helper."""

    def test_preserves_date_suffix(self):
        self.assertEqual(
            _normalize_name("HDFC Bank Limited (24/06/2026)"),
            "HDFC BANK LIMITED (24/06/2026)",
        )

    def test_expands_ltd_dot(self):
        self.assertEqual(_normalize_name("HDFC Bank Ltd."), "HDFC BANK LIMITED")

    def test_expands_ltd_no_dot(self):
        self.assertEqual(_normalize_name("HDFC Bank Ltd"), "HDFC BANK LIMITED")

    def test_expands_pvt(self):
        self.assertEqual(_normalize_name("ABC Pvt. Ltd."), "ABC PRIVATE LIMITED")

    def test_uppercases(self):
        self.assertEqual(_normalize_name("infosys limited"), "INFOSYS LIMITED")

    def test_already_normalised(self):
        self.assertEqual(_normalize_name("HDFC BANK LIMITED"), "HDFC BANK LIMITED")


class TestDisplayName(unittest.TestCase):
    """Tests for _display_name and _pick_display_name helpers."""

    def test_preserves_date_suffix(self):
        self.assertEqual(
            _display_name("HDFC Bank Limited (24/06/2026)"),
            "HDFC Bank Limited (24/06/2026)",
        )

    def test_expands_ltd(self):
        self.assertEqual(_display_name("HDFC Bank Ltd."), "HDFC Bank Limited")

    def test_expands_pvt(self):
        self.assertEqual(_display_name("ABC Pvt. Ltd."), "ABC Private Limited")

    def test_preserves_case(self):
        self.assertEqual(_display_name("Infosys Limited"), "Infosys Limited")

    def test_pick_prefers_mixed_case(self):
        names = ["HDFC BANK LIMITED", "HDFC Bank Limited"]
        self.assertEqual(_pick_display_name(names), "HDFC Bank Limited")

    def test_pick_longest_when_all_uppercase(self):
        names = ["RELIANCE", "RELIANCE INDUSTRIES"]
        self.assertEqual(_pick_display_name(names), "RELIANCE INDUSTRIES")

    def test_pick_preserves_date_in_display(self):
        names = ["HDFC Bank Ltd.", "HDFC Bank Limited (24/06/2026)"]
        result = _pick_display_name(names)
        self.assertEqual(result, "HDFC Bank Limited (24/06/2026)")


class TestGatherRawEntries(unittest.TestCase):
    """Tests for _gather_raw_entries helper."""

    def test_gathers_mf_entries(self):
        mf_by_isin = {"INF001": {"fund": "Fund A", "quantity": 100.0, "last_price": 50.0}}
        holdings_data = {
            "INF001": [
                {
                    "company_name": "HDFC BANK",
                    "sector": "Finance",
                    "instrument_type": "Equity",
                    "allocation_pct": 10.0,
                },
            ]
        }
        entries = _gather_raw_entries(mf_by_isin, {}, [], holdings_data)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].raw_name, "HDFC BANK")
        self.assertEqual(entries[0].instrument_type, "Equity")
        self.assertAlmostEqual(entries[0].amount, 500.0)  # 10% of 5000
        self.assertEqual(entries[0].fund_name, "Fund A")

    def test_filters_non_equity(self):
        mf_by_isin = {"INF001": {"fund": "Fund A", "quantity": 100.0, "last_price": 50.0}}
        holdings_data = {
            "INF001": [
                {"company_name": "TREPS", "sector": "Cash", "instrument_type": "Equity", "allocation_pct": 5.0},
                {
                    "company_name": "Infosys Limited",
                    "sector": "IT",
                    "instrument_type": "Equity",
                    "allocation_pct": 10.0,
                },
            ]
        }
        entries = _gather_raw_entries(mf_by_isin, {}, [], holdings_data)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].raw_name, "Infosys Limited")

    @patch("app.api.exposure.nse_equity_cache")
    def test_resolves_stock_via_nse_cache(self, mock_cache):
        from app.api.nse_equity import NSEEquityInfo

        mock_cache.get.return_value = NSEEquityInfo(
            symbol="HDFCBANK",
            company_name="HDFC Bank Limited",
            isin="INE040A01034",
            series="EQ",
        )
        stocks = [{"tradingsymbol": "HDFCBANK", "quantity": 1, "last_price": 1500.0}]
        entries = _gather_raw_entries({}, {}, stocks, {})
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].raw_name, "HDFC Bank Limited")
        self.assertEqual(entries[0].fund_name, "Direct")

    def test_direct_stock_instrument_type_is_equity(self):
        """Direct stocks always get instrument_type='Equity'."""
        stocks = [{"tradingsymbol": "INFY", "quantity": 1, "last_price": 1500.0}]
        with patch("app.api.exposure.nse_equity_cache") as mock_cache:
            mock_cache.get.return_value = None
            entries = _gather_raw_entries({}, {}, stocks, {})
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].instrument_type, "Equity")

    def test_defaults_instrument_type_to_equity(self):
        """Missing instrument_type in holdings data defaults to 'Equity'."""
        mf_by_isin = {"INF001": {"fund": "Fund A", "quantity": 100.0, "last_price": 50.0}}
        holdings_data = {"INF001": [{"company_name": "HDFC BANK", "sector": "Finance", "allocation_pct": 10.0}]}
        entries = _gather_raw_entries(mf_by_isin, {}, [], holdings_data)
        self.assertEqual(entries[0].instrument_type, "Equity")

    def test_skips_zero_value_mf(self):
        mf_by_isin = {"INF001": {"fund": "Fund A", "quantity": 0, "last_price": 0}}
        holdings_data = {
            "INF001": [
                {"company_name": "HDFC BANK", "sector": "Finance", "instrument_type": "Equity", "allocation_pct": 10.0}
            ]
        }
        entries = _gather_raw_entries(mf_by_isin, {}, [], holdings_data)
        self.assertEqual(len(entries), 0)


class TestMergeSimilarSectors(unittest.TestCase):
    """Tests for _merge_similar_sectors (mocked entity matcher)."""

    @patch("app.api.exposure.get_entity_matcher")
    def test_merges_similar_sectors(self, mock_get_matcher):
        mock_matcher = MagicMock()
        mock_matcher.cluster_names.return_value = {
            "Banking": "Banking",
            "Banks": "Banking",
        }
        mock_get_matcher.return_value = mock_matcher

        totals = {"Banking": 5000.0, "Banks": 3000.0}
        merged = _merge_similar_sectors(totals)
        self.assertEqual(len(merged), 1)
        self.assertAlmostEqual(merged["Banking"], 8000.0)

    @patch("app.api.exposure.get_entity_matcher")
    def test_unknown_passed_through(self, mock_get_matcher):
        mock_matcher = MagicMock()
        mock_matcher.cluster_names.return_value = {"IT": "IT"}
        mock_get_matcher.return_value = mock_matcher

        totals = {"IT": 5000.0, "Unknown": 2000.0}
        merged = _merge_similar_sectors(totals)
        self.assertIn("Unknown", merged)
        self.assertAlmostEqual(merged["Unknown"], 2000.0)

    def test_single_sector_passthrough(self):
        totals = {"Finance": 5000.0}
        merged = _merge_similar_sectors(totals)
        self.assertEqual(merged, totals)


class TestFetchHoldings(unittest.TestCase):
    """Tests for _fetch_holdings (mocked HTTP)."""

    def _mock_response(self, data_rows):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"data": data_rows}
        return resp

    @patch("app.api.exposure.requests.get")
    def test_parses_holdings_correctly(self, mock_get):
        rows = [
            ["1", "HDFC BANK LIMITED", "Finance", "Equity", "", "8.5"],
            ["2", "INFOSYS LIMITED", "Information Technology", "Equity", "", "6.2"],
        ]
        mock_get.return_value = self._mock_response(rows)
        isin, holdings = _fetch_holdings("INF123456789")
        self.assertEqual(isin, "INF123456789")
        self.assertEqual(len(holdings), 2)
        self.assertEqual(holdings[0]["company_name"], "HDFC BANK LIMITED")
        self.assertEqual(holdings[0]["sector"], "Finance")
        self.assertEqual(holdings[0]["instrument_type"], "Equity")
        self.assertAlmostEqual(holdings[0]["allocation_pct"], 8.5)

    @patch("app.api.exposure.requests.get")
    def test_returns_empty_on_network_error(self, mock_get):
        mock_get.side_effect = ConnectionError("timeout")
        isin, holdings = _fetch_holdings("INVALIDISN")
        self.assertEqual(isin, "INVALIDISN")
        self.assertEqual(holdings, [])

    @patch("app.api.exposure.requests.get")
    def test_skips_rows_with_invalid_allocation(self, mock_get):
        rows = [
            ["1", "HDFC BANK", "Finance", "", "", "not-a-number"],
            ["2", "INFY", "IT", "", "", "5.0"],
        ]
        mock_get.return_value = self._mock_response(rows)
        _, holdings = _fetch_holdings("INF999")
        self.assertEqual(len(holdings), 1)
        self.assertEqual(holdings[0]["company_name"], "INFY")

    @patch("app.api.exposure.requests.get")
    def test_skips_short_rows(self, mock_get):
        rows = [
            ["1", "SHORT"],  # only 2 columns — too short
            ["2", "HDFC BANK", "Finance", "", "", "8.0"],
        ]
        mock_get.return_value = self._mock_response(rows)
        _, holdings = _fetch_holdings("INF001")
        self.assertEqual(len(holdings), 1)


class TestBatchFetchHoldings(unittest.TestCase):
    """Tests for _batch_fetch_holdings concurrency wrapper."""

    @patch("app.api.exposure._fetch_holdings")
    def test_aggregates_results(self, mock_fetch):
        mock_fetch.side_effect = lambda isin: (
            isin,
            [{"company_name": "Co" + isin, "sector": "IT", "allocation_pct": 5.0}],
        )
        result = _batch_fetch_holdings(["A", "B", "C"])
        self.assertEqual(set(result.keys()), {"A", "B", "C"})

    def test_empty_list_returns_empty(self):
        result = _batch_fetch_holdings([])
        self.assertEqual(result, {})


class TestExposureCache(unittest.TestCase):
    """Tests for ExposureCache LRU behaviour."""

    def _make_result(self, total=100000.0):
        return ExposureResult(
            companies=[
                CompanyHolding(
                    company_name="HDFC BANK",
                    sector="Finance",
                    instrument_type="Equity",
                    holding_amount=50000.0,
                    percentage_of_portfolio=50.0,
                    funds=["Fund A"],
                )
            ],
            sector_totals={"Finance": 50000.0},
            fund_totals={"Fund A": 50000.0},
            total_portfolio_value=total,
        )

    def test_put_and_get(self):
        cache = ExposureCache(maxsize=10)
        result = self._make_result()
        cache.put("user1", result)
        retrieved = cache.get("user1")
        self.assertIsNotNone(retrieved)
        self.assertAlmostEqual(retrieved.total_portfolio_value, 100000.0)

    def test_miss_returns_none(self):
        cache = ExposureCache(maxsize=10)
        self.assertIsNone(cache.get("nonexistent"))

    def test_invalidate_removes_entry(self):
        cache = ExposureCache(maxsize=10)
        cache.put("user1", self._make_result())
        cache.invalidate("user1")
        self.assertIsNone(cache.get("user1"))

    def test_lru_eviction(self):
        cache = ExposureCache(maxsize=2)
        cache.put("u1", self._make_result())
        cache.put("u2", self._make_result())
        cache.put("u3", self._make_result())  # evicts u1 (LRU)
        self.assertIsNone(cache.get("u1"))
        self.assertIsNotNone(cache.get("u2"))
        self.assertIsNotNone(cache.get("u3"))

    def test_in_progress_lifecycle(self):
        cache = ExposureCache(maxsize=10)
        self.assertFalse(cache.is_in_progress("user1"))
        cache.set_in_progress("user1")
        self.assertTrue(cache.is_in_progress("user1"))
        cache.clear_in_progress("user1")
        self.assertFalse(cache.is_in_progress("user1"))

    def test_clear_in_progress_idempotent(self):
        cache = ExposureCache(maxsize=10)
        cache.clear_in_progress("nonexistent")  # should not raise

    def test_thread_safe_concurrent_access(self):
        """Multiple threads should be able to put/get without errors."""
        cache = ExposureCache(maxsize=50)
        errors = []

        def worker(uid):
            try:
                cache.put(uid, self._make_result())
                _ = cache.get(uid)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(f"user{i}",)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])


class TestIsNonEquity(unittest.TestCase):
    """Tests for _is_non_equity filter helper."""

    def test_treps_filtered(self):
        self.assertTrue(_is_non_equity("TREPS"))

    def test_treps_case_insensitive(self):
        self.assertTrue(_is_non_equity("treps"))

    def test_cblo_filtered(self):
        self.assertTrue(_is_non_equity("CBLO"))

    def test_net_receivables_filtered(self):
        self.assertTrue(_is_non_equity("Net Receivables"))
        self.assertTrue(_is_non_equity("NET RECEIVABLE"))

    def test_net_current_assets_filtered(self):
        self.assertTrue(_is_non_equity("Net Current Assets"))

    def test_reverse_repo_filtered(self):
        self.assertTrue(_is_non_equity("Reverse Repo"))

    def test_equity_not_filtered(self):
        self.assertFalse(_is_non_equity("Infosys Limited"))
        self.assertFalse(_is_non_equity("HDFC Bank Ltd."))
        self.assertFalse(_is_non_equity("Tata Consultancy Services"))


class TestBuildExposureData(unittest.TestCase):
    """Integration-style tests for build_exposure_data."""

    def setUp(self):
        # Mock the entity matcher so we don't load the real model.
        # Identity clustering: each name maps to itself (no merging).
        mock_matcher = MagicMock()
        mock_matcher.cluster_names.side_effect = lambda names: {n: n for n in names}
        p1 = patch("app.api.exposure.get_entity_matcher", return_value=mock_matcher)
        self._mock_get_matcher = p1.start()
        self.addCleanup(p1.stop)

    def _mf(self, isin, fund_name, qty=100.0, nav=50.0):
        return {"isin": isin, "fund": fund_name, "quantity": qty, "last_price": nav}

    def _etf(self, isin, symbol, qty=10.0, price=200.0):
        return {"isin": isin, "tradingsymbol": symbol, "quantity": qty, "last_price": price, "manual_type": "etfs"}

    def _stock(self, symbol, qty=5.0, price=1500.0, isin=""):
        return {"tradingsymbol": symbol, "quantity": qty, "last_price": price, "manual_type": "stocks", "isin": isin}

    def _holdings_response(self, rows):
        return rows

    @patch("app.api.exposure._batch_fetch_holdings")
    def test_returns_none_when_no_data(self, _mock):
        result = build_exposure_data("uid", [], [])
        self.assertIsNone(result)

    @patch("app.api.exposure._batch_fetch_holdings")
    def test_returns_none_when_zero_values(self, _mock):
        stocks = [{"tradingsymbol": "TCS", "quantity": 0, "last_price": 0}]
        result = build_exposure_data("uid", stocks, [])
        self.assertIsNone(result)

    @patch("app.api.exposure._batch_fetch_holdings")
    def test_direct_stocks_included(self, mock_batch):
        mock_batch.return_value = {}
        stocks = [self._stock("TCS")]
        result = build_exposure_data("uid", stocks, [])
        self.assertIsNotNone(result)
        self.assertEqual(len(result.companies), 1)
        self.assertEqual(result.companies[0].company_name, "TCS")
        self.assertEqual(result.companies[0].instrument_type, "Equity")
        self.assertIn("Direct", result.companies[0].funds)

    @patch("app.api.exposure._batch_fetch_holdings")
    def test_mf_holdings_aggregated(self, mock_batch):
        mf = self._mf("INF001", "HDFC Top 100")  # value = 100 * 50 = 5000
        mock_batch.return_value = {
            "INF001": [
                {
                    "company_name": "HDFC BANK LTD",
                    "sector": "Finance",
                    "instrument_type": "Equity",
                    "allocation_pct": 8.0,
                },
                {
                    "company_name": "INFOSYS",
                    "sector": "IT",
                    "instrument_type": "Equity",
                    "allocation_pct": 6.0,
                },
            ]
        }
        result = build_exposure_data("uid", [], [mf])
        self.assertIsNotNone(result)
        company_names = {c.company_name for c in result.companies}
        # _display_name expands "LTD" → "Limited"
        self.assertIn("HDFC BANK Limited", company_names)
        self.assertIn("INFOSYS", company_names)
        # HDFC BANK LTD: 8% of 5000 = 400
        hdfc = next(c for c in result.companies if "HDFC BANK" in c.company_name)
        self.assertAlmostEqual(hdfc.holding_amount, 400.0, places=1)

    @patch("app.api.exposure._batch_fetch_holdings")
    def test_same_isin_deduped_across_accounts(self, mock_batch):
        mf1 = {"isin": "INF001", "fund": "HDFC Top 100", "quantity": 50.0, "last_price": 50.0}
        mf2 = {"isin": "INF001", "fund": "HDFC Top 100", "quantity": 50.0, "last_price": 50.0}
        mock_batch.return_value = {
            "INF001": [{"company_name": "INFY", "sector": "IT", "instrument_type": "Equity", "allocation_pct": 10.0}]
        }
        result = build_exposure_data("uid", [], [mf1, mf2])
        # Combined qty=100, value=5000, 10% → 500 for INFY
        # pyrefly: ignore [missing-attribute]
        infy = next(c for c in result.companies if c.company_name == "INFY")
        self.assertAlmostEqual(infy.holding_amount, 500.0, places=1)

    @patch("app.api.exposure._batch_fetch_holdings")
    def test_percentages_sum_to_100_approx(self, mock_batch):
        mf = self._mf("INF001", "Fund A")
        mock_batch.return_value = {
            "INF001": [
                {"company_name": "Co A", "sector": "IT", "instrument_type": "Equity", "allocation_pct": 50.0},
                {"company_name": "Co B", "sector": "Finance", "instrument_type": "Equity", "allocation_pct": 50.0},
            ]
        }
        result = build_exposure_data("uid", [], [mf])
        # pyrefly: ignore [missing-attribute]
        total_pct = sum(c.percentage_of_portfolio for c in result.companies)
        self.assertAlmostEqual(total_pct, 100.0, places=1)

    @patch("app.api.exposure._batch_fetch_holdings")
    def test_companies_sorted_by_amount_descending(self, mock_batch):
        mf = self._mf("INF001", "Fund A")
        mock_batch.return_value = {
            "INF001": [
                {"company_name": "Small Co", "sector": "IT", "instrument_type": "Equity", "allocation_pct": 2.0},
                {"company_name": "Big Co", "sector": "Finance", "instrument_type": "Equity", "allocation_pct": 20.0},
            ]
        }
        result = build_exposure_data("uid", [], [mf])
        # pyrefly: ignore [missing-attribute]
        amounts = [c.holding_amount for c in result.companies]
        self.assertEqual(amounts, sorted(amounts, reverse=True))

    @patch("app.api.exposure._batch_fetch_holdings")
    def test_sector_totals_computed(self, mock_batch):
        mf = self._mf("INF001", "Fund A")  # value = 5000
        mock_batch.return_value = {
            "INF001": [
                {"company_name": "HDFC", "sector": "Finance", "instrument_type": "Equity", "allocation_pct": 10.0},
                {"company_name": "INFY", "sector": "IT", "instrument_type": "Equity", "allocation_pct": 8.0},
            ]
        }
        result = build_exposure_data("uid", [], [mf])
        # pyrefly: ignore [missing-attribute]
        self.assertIn("Finance", result.sector_totals)
        # pyrefly: ignore [missing-attribute]
        self.assertIn("IT", result.sector_totals)
        # pyrefly: ignore [missing-attribute]
        self.assertAlmostEqual(result.sector_totals["Finance"], 500.0, places=1)
        # pyrefly: ignore [missing-attribute]
        self.assertAlmostEqual(result.sector_totals["IT"], 400.0, places=1)

    @patch("app.api.exposure._batch_fetch_holdings")
    def test_etf_processed_same_as_mf(self, mock_batch):
        etf = self._etf("INF100", "NIFTYBEES")  # value = 10 * 200 = 2000
        mock_batch.return_value = {
            "INF100": [
                {"company_name": "HDFC BANK", "sector": "Finance", "instrument_type": "Equity", "allocation_pct": 12.0}
            ]
        }
        result = build_exposure_data("uid", [etf], [])
        self.assertIsNotNone(result)
        hdfc = next((c for c in result.companies if c.company_name == "HDFC BANK"), None)
        self.assertIsNotNone(hdfc)
        # 12% of 2000 = 240
        self.assertAlmostEqual(hdfc.holding_amount, 240.0, places=1)

    @patch("app.api.exposure._batch_fetch_holdings")
    def test_zero_value_mf_skipped(self, mock_batch):
        mf = self._mf("INF001", "Fund A", qty=0, nav=0)
        mock_batch.return_value = {
            "INF001": [
                {"company_name": "HDFC", "sector": "Finance", "instrument_type": "Equity", "allocation_pct": 10.0}
            ]
        }
        result = build_exposure_data("uid", [], [mf])
        self.assertIsNone(result)

    @patch("app.api.exposure.nse_equity_cache")
    @patch("app.api.exposure._batch_fetch_holdings")
    def test_direct_stock_merged_via_canonical_name(self, mock_batch, mock_nse_cache):
        """NSE canonical name resolution merges 'HDFCBANK' with 'HDFC Bank Ltd.' from a fund.

        The direct stock has no CDN sector so it inherits the voted CDN sector
        from the MF entry for the same display name, allowing the two entries
        to merge into one row.
        """
        from app.api.nse_equity import NSEEquityInfo

        mock_nse_cache.get.return_value = NSEEquityInfo(
            symbol="HDFCBANK",
            company_name="HDFC Bank Limited",
            isin="INE040A01034",
            series="EQ",
        )
        mf = self._mf("INF001", "HDFC Flexi Cap")  # value = 100 * 50 = 5000
        mock_batch.return_value = {
            "INF001": [
                {
                    "company_name": "HDFC Bank Ltd.",
                    "sector": "Finance - Banks - Private Sector",
                    "instrument_type": "Equity",
                    "allocation_pct": 8.0,
                }
            ]
        }
        stock = self._stock("HDFCBANK", qty=1, price=6244.0)
        result = build_exposure_data("uid", [stock], [mf])
        self.assertIsNotNone(result)
        # Both normalise to "HDFC BANK LIMITED".  The direct stock
        # inherits "Finance - Banks - Private Sector" via CDN sector
        # voting on the display name.
        # 8% of 5000 (=400) + 6244 = 6644
        self.assertEqual(len(result.companies), 1)
        self.assertAlmostEqual(result.companies[0].holding_amount, 400.0 + 6244.0, places=0)
        self.assertIn("Direct", result.companies[0].funds)
        self.assertEqual(result.companies[0].sector, "Finance - Banks - Private Sector")

    @patch("app.api.exposure._batch_fetch_holdings")
    def test_same_company_different_instrument_types_separate(self, mock_batch):
        """Same company with different instrument types must produce separate rows."""
        mf = self._mf("INF001", "Fund A")  # value = 5000
        mock_batch.return_value = {
            "INF001": [
                {
                    "company_name": "HDFC Bank Ltd.",
                    "sector": "Finance",
                    "instrument_type": "Equity",
                    "allocation_pct": 10.0,
                },
                {
                    "company_name": "HDFC Bank Limited (20/10/2021)",
                    "sector": "Finance",
                    "instrument_type": "Certificate of Deposits",
                    "allocation_pct": 5.0,
                },
            ]
        }
        result = build_exposure_data("uid", [], [mf])
        self.assertIsNotNone(result)
        # Two separate rows: same company, different instrument types
        self.assertEqual(len(result.companies), 2)
        types = {c.instrument_type for c in result.companies}
        self.assertEqual(types, {"Equity", "Certificate of Deposits"})
        equity = next(c for c in result.companies if c.instrument_type == "Equity")
        cd = next(c for c in result.companies if c.instrument_type == "Certificate of Deposits")
        self.assertAlmostEqual(equity.holding_amount, 500.0, places=1)
        self.assertAlmostEqual(cd.holding_amount, 250.0, places=1)

    @patch("app.api.exposure._batch_fetch_holdings")
    def test_same_company_same_instrument_merged(self, mock_batch):
        """Same company and instrument type across funds must merge into one row."""
        mf1 = self._mf("INF001", "Fund A")  # value = 5000
        mf2 = self._mf("INF002", "Fund B")  # value = 5000
        mock_batch.return_value = {
            "INF001": [
                {
                    "company_name": "HDFC Bank Ltd.",
                    "sector": "Finance",
                    "instrument_type": "Equity",
                    "allocation_pct": 10.0,
                }
            ],
            "INF002": [
                {
                    "company_name": "HDFC Bank Limited",
                    "sector": "Finance",
                    "instrument_type": "Equity",
                    "allocation_pct": 10.0,
                }
            ],
        }
        result = build_exposure_data("uid", [], [mf1, mf2])
        self.assertIsNotNone(result)
        # Both normalise to "HDFC BANK LIMITED" + same instrument → single row
        self.assertEqual(len(result.companies), 1)
        self.assertAlmostEqual(result.companies[0].holding_amount, 1000.0, places=0)

    @patch("app.api.exposure._batch_fetch_holdings")
    def test_date_in_display_name_preserved(self, mock_batch):
        """Date suffix in company name should be preserved in display."""
        mf = self._mf("INF001", "Fund A")  # value = 5000
        mock_batch.return_value = {
            "INF001": [
                {
                    "company_name": "HDFC Bank Limited (20/10/2021)",
                    "sector": "Finance",
                    "instrument_type": "Certificate of Deposits",
                    "allocation_pct": 10.0,
                }
            ],
        }
        result = build_exposure_data("uid", [], [mf])
        self.assertIsNotNone(result)
        self.assertIn("(20/10/2021)", result.companies[0].company_name)

    @patch("app.api.exposure._batch_fetch_holdings")
    def test_treps_excluded_from_exposure(self, mock_batch):
        """TREPS and other cash-equivalent CDN rows must be filtered out."""
        mf = self._mf("INF001", "Fund A")  # value = 5000
        mock_batch.return_value = {
            "INF001": [
                {"company_name": "TREPS", "sector": "Financials", "instrument_type": "Equity", "allocation_pct": 5.0},
                {"company_name": "CBLO", "sector": "Financials", "instrument_type": "Equity", "allocation_pct": 2.0},
                {"company_name": "Net Receivables", "sector": "", "instrument_type": "Equity", "allocation_pct": 1.0},
                {
                    "company_name": "Infosys Limited",
                    "sector": "IT",
                    "instrument_type": "Equity",
                    "allocation_pct": 10.0,
                },
            ]
        }
        result = build_exposure_data("uid", [], [mf])
        self.assertIsNotNone(result)
        company_names = {c.company_name for c in result.companies}
        self.assertNotIn("TREPS", company_names)
        self.assertNotIn("CBLO", company_names)
        self.assertNotIn("Net Receivables", company_names)
        self.assertIn("Infosys Limited", company_names)

    @patch("app.api.exposure._batch_fetch_holdings")
    def test_missing_isin_mf_excluded_from_batch(self, mock_batch):
        mf_no_isin = {"isin": "", "fund": "Unknown Fund", "quantity": 100.0, "last_price": 50.0}
        mf_with_isin = self._mf("INF001", "Known Fund")
        mock_batch.return_value = {
            "INF001": [{"company_name": "INFY", "sector": "IT", "instrument_type": "Equity", "allocation_pct": 5.0}]
        }
        build_exposure_data("uid", [], [mf_no_isin, mf_with_isin])
        # Only ISINs with actual values should be in the batch call
        called_isins = set(mock_batch.call_args[0][0])
        self.assertIn("INF001", called_isins)
        self.assertNotIn("", called_isins)

    @patch("app.api.exposure._batch_fetch_holdings")
    def test_cdn_sector_trusted_over_classifier(self, mock_batch):
        """CDN sector is used as-is when present, classifier not invoked."""
        mf = self._mf("INF001", "Fund A")
        mock_batch.return_value = {
            "INF001": [
                {
                    "company_name": "HDFC Bank Ltd.",
                    "sector": "Finance",
                    "instrument_type": "Equity",
                    "allocation_pct": 10.0,
                }
            ]
        }
        result = build_exposure_data("uid", [], [mf])
        self.assertIsNotNone(result)
        # CDN sector "Finance" is trusted directly.
        self.assertEqual(result.companies[0].sector, "Finance")

    @patch("app.api.exposure._batch_fetch_holdings")
    def test_classifier_keeps_cdn_sector_when_low_confidence(self, mock_batch):
        """Low-confidence classification keeps original CDN sector."""
        mf = self._mf("INF001", "Fund A")
        mock_batch.return_value = {
            "INF001": [
                {
                    "company_name": "Reliance Industries",
                    "sector": "Oil & Gas",
                    "instrument_type": "Equity",
                    "allocation_pct": 10.0,
                }
            ]
        }
        result = build_exposure_data("uid", [], [mf])
        self.assertIsNotNone(result)
        # Default mock returns 0.1 confidence → CDN sector preserved.
        self.assertEqual(result.companies[0].sector, "Oil & Gas")

    @patch("app.api.exposure.nse_equity_cache")
    @patch("app.api.exposure._batch_fetch_holdings")
    def test_direct_stock_without_cdn_sector_gets_unknown(self, mock_batch, mock_nse_cache):
        """Direct stocks without a CDN sector are labelled 'Unknown'."""
        from app.api.nse_equity import NSEEquityInfo

        mock_nse_cache.get.return_value = NSEEquityInfo(
            symbol="HDFCBANK",
            company_name="HDFC Bank Limited",
            isin="INE040A01034",
            series="EQ",
        )
        stock = {"tradingsymbol": "HDFCBANK", "quantity": 10, "last_price": 1600.0}
        mock_batch.return_value = {}
        result = build_exposure_data("uid", [stock], [])
        self.assertIsNotNone(result)
        self.assertEqual(result.companies[0].sector, "Unknown")


if __name__ == "__main__":
    unittest.main()
