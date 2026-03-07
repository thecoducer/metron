"""
Unit tests for api/provident_fund.py — EPF corpus calculation and auto-rate.
"""
import unittest
from datetime import date
from unittest.mock import patch

from app.api.provident_fund import (
    _get_epf_rate,
    calculate_pf_corpus,
    resolve_epf_rate,
)
from app.utils import parse_date
from app.api.google_sheets_client import ProvidentFundService, DataError
from app.constants import EPF_DEFAULT_RATE, EPF_HISTORICAL_RATES


class TestGetEpfRate(unittest.TestCase):
    """Tests for the _get_epf_rate helper."""

    def test_known_rate_after_april(self):
        # June 2022 → FY 2022-23 → rate 8.15
        self.assertEqual(_get_epf_rate(2022, 6), 8.15)

    def test_known_rate_before_april(self):
        # Feb 2023 → FY 2022-23 (started Apr 2022) → rate 8.15
        self.assertEqual(_get_epf_rate(2023, 2), 8.15)

    def test_known_rate_in_april(self):
        # Apr 2024 → FY 2024-25 → rate 8.25
        self.assertEqual(_get_epf_rate(2024, 4), 8.25)

    def test_known_rate_in_march(self):
        # Mar 2025 → FY 2024-25 (started Apr 2024) → rate 8.25
        self.assertEqual(_get_epf_rate(2025, 3), 8.25)

    def test_fallback_for_old_year(self):
        # 2005 is not in the table → should return default
        self.assertEqual(_get_epf_rate(2005, 6), EPF_DEFAULT_RATE)

    def test_all_historical_rates_accessible(self):
        """Every entry in EPF_HISTORICAL_RATES should be reachable."""
        for fy_start, expected_rate in EPF_HISTORICAL_RATES.items():
            # July of the FY start year → should map to this rate
            self.assertEqual(
                _get_epf_rate(fy_start, 7), expected_rate,
                f"FY {fy_start}-{fy_start+1} rate mismatch",
            )


class TestResolveEpfRate(unittest.TestCase):
    """Tests for resolve_epf_rate helper."""

    def test_single_fy(self):
        # Apr 2022 → Mar 2023 → FY 2022, rate 8.15
        rate = resolve_epf_rate("2022-04-01", "2023-03-01")
        self.assertEqual(rate, 8.15)

    def test_cross_fy_weighted_average(self):
        # Jan 2022 (FY 2021, rate 8.10) → Jun 2022 (FY 2022, rate 8.15)
        # Jan–Mar 2022 = 3 months @ 8.10, Apr–Jun 2022 = 3 months @ 8.15
        rate = resolve_epf_rate("2022-01-01", "2022-06-01")
        expected = round((3 * 8.10 + 3 * 8.15) / 6, 2)
        self.assertEqual(rate, expected)

    def test_no_end_date_uses_today(self):
        rate = resolve_epf_rate("2024-01-01", "")
        self.assertIsNotNone(rate)
        self.assertGreater(rate, 0)

    def test_invalid_start_returns_none(self):
        self.assertIsNone(resolve_epf_rate("not-a-date"))

    def test_empty_start_returns_none(self):
        self.assertIsNone(resolve_epf_rate(""))


class TestParseDate(unittest.TestCase):
    def test_iso_format(self):
        self.assertEqual(parse_date("2024-01-15"), date(2024, 1, 15))

    def test_us_format(self):
        self.assertEqual(parse_date("01/15/2024"), date(2024, 1, 15))

    def test_long_format(self):
        self.assertEqual(parse_date("January 15, 2024"), date(2024, 1, 15))

    def test_empty_string(self):
        self.assertIsNone(parse_date(""))

    def test_none(self):
        self.assertIsNone(parse_date(None))

    def test_garbage(self):
        self.assertIsNone(parse_date("not-a-date"))

    def test_excel_serial_integer(self):
        # 45573 = 2024-10-08 in Excel/Sheets serial-date format
        self.assertEqual(parse_date("45573"), date(2024, 10, 8))

    def test_excel_serial_float(self):
        # Sheets may return "45573.0" for dates with time component
        self.assertEqual(parse_date("45573.0"), date(2024, 10, 8))

    def test_excel_serial_as_int(self):
        # Passed as a raw int from the API (not a string)
        self.assertEqual(parse_date(45573), date(2024, 10, 8))

    def test_excel_serial_zero_returns_none(self):
        self.assertIsNone(parse_date("0"))

    def test_excel_serial_known_dates(self):
        # 45293 = 2024-01-02, 45818 = 2025-06-10
        self.assertEqual(parse_date("45293"), date(2024, 1, 2))
        self.assertEqual(parse_date("45818"), date(2025, 6, 10))


class TestCalculatePfCorpus(unittest.TestCase):
    """Tests for calculate_pf_corpus with manual and auto rates."""

    def test_empty_entries(self):
        self.assertEqual(calculate_pf_corpus([]), [])

    def test_unparseable_dates_skipped(self):
        result = calculate_pf_corpus([{
            "company_name": "Test",
            "start_date": "garbage",
            "monthly_contribution": 5000,
            "interest_rate": 8.5,
        }])
        self.assertEqual(result, [])

    @patch("app.api.provident_fund.date")
    def test_single_entry_manual_rate(self, mock_date):
        mock_date.today.return_value = date(2024, 3, 31)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        entries = [{
            "company_name": "Infosys",
            "start_date": "2023-04-01",
            "end_date": "2024-03-31",
            "monthly_contribution": 5000,
            "interest_rate": 8.5,
        }]
        result = calculate_pf_corpus(entries)
        self.assertEqual(len(result), 1)

        r = result[0]
        self.assertEqual(r["company_name"], "Infosys")
        self.assertEqual(r["months_worked"], 12)
        self.assertEqual(r["total_contribution"], 60000.0)
        self.assertGreater(r["interest_earned"], 0)
        self.assertGreater(r["closing_balance"], 60000)
        self.assertFalse(r["auto_rate"])

    @patch("app.api.provident_fund.date")
    def test_single_entry_auto_rate(self, mock_date):
        """When interest_rate is 0, the engine should use EPFO historical rates."""
        mock_date.today.return_value = date(2024, 3, 31)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        entries = [{
            "company_name": "Wipro",
            "start_date": "2023-04-01",
            "end_date": "2024-03-31",
            "monthly_contribution": 5000,
            "interest_rate": 0,  # auto
        }]
        result = calculate_pf_corpus(entries)
        self.assertEqual(len(result), 1)

        r = result[0]
        self.assertTrue(r["auto_rate"])
        # Should have computed interest using the FY 2023-24 rate (8.25%)
        self.assertGreater(r["interest_earned"], 0)
        self.assertGreater(r["closing_balance"], 60000)
        self.assertEqual(r["months_worked"], 12)

    @patch("app.api.provident_fund.date")
    def test_auto_rate_uses_correct_fy_rates(self, mock_date):
        """Auto-rate spanning two financial years should use different rates."""
        mock_date.today.return_value = date(2023, 3, 31)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        # Span FY 2021-22 (rate 8.10) and FY 2022-23 (rate 8.15)
        entries = [{
            "company_name": "TCS",
            "start_date": "2021-04-01",
            "end_date": "2023-03-31",
            "monthly_contribution": 10000,
            "interest_rate": 0,  # auto
        }]
        result = calculate_pf_corpus(entries)
        r = result[0]
        self.assertTrue(r["auto_rate"])
        self.assertEqual(r["months_worked"], 24)
        self.assertEqual(r["total_contribution"], 240000.0)
        # Interest should be non-trivial
        self.assertGreater(r["interest_earned"], 15000)

    @patch("app.api.provident_fund.date")
    def test_multi_company_stints(self, mock_date):
        mock_date.today.return_value = date(2024, 3, 31)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        entries = [
            {
                "company_name": "Company A",
                "start_date": "2022-04-01",
                "end_date": "2023-03-31",
                "monthly_contribution": 5000,
                "interest_rate": 8.10,
            },
            {
                "company_name": "Company B",
                "start_date": "2023-04-01",
                "end_date": "2024-03-31",
                "monthly_contribution": 7000,
                "interest_rate": 8.25,
            },
        ]
        result = calculate_pf_corpus(entries)
        self.assertEqual(len(result), 2)

        # Second entry should carry forward balance from first
        self.assertGreater(result[1]["opening_balance"], 0)
        # Corpus value should be the total
        self.assertGreater(result[1]["corpus_value"], result[0]["closing_balance"])
        # Both should have manual rates
        self.assertFalse(result[0]["auto_rate"])
        self.assertFalse(result[1]["auto_rate"])

    @patch("app.api.provident_fund.date")
    def test_no_end_date_means_current(self, mock_date):
        mock_date.today.return_value = date(2024, 6, 15)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        entries = [{
            "company_name": "Current Co",
            "start_date": "2024-04-01",
            "end_date": "",
            "monthly_contribution": 6000,
            "interest_rate": 8.25,
        }]
        result = calculate_pf_corpus(entries)
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["is_current"])
        self.assertEqual(result[0]["months_worked"], 3)  # Apr, May, Jun

    @patch("app.api.provident_fund.date")
    def test_corpus_value_on_all_entries(self, mock_date):
        """corpus_value should be the same (grand total) on all entries."""
        mock_date.today.return_value = date(2024, 3, 31)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        entries = [
            {
                "company_name": "A",
                "start_date": "2022-04-01",
                "end_date": "2023-03-31",
                "monthly_contribution": 5000,
                "interest_rate": 8.0,
            },
            {
                "company_name": "B",
                "start_date": "2023-04-01",
                "end_date": "2024-03-31",
                "monthly_contribution": 6000,
                "interest_rate": 8.0,
            },
        ]
        result = calculate_pf_corpus(entries)
        # corpus_value should be identical on both entries
        self.assertEqual(result[0]["corpus_value"], result[1]["corpus_value"])
        # closing_balance should differ (per-entry)
        self.assertNotEqual(
            result[0]["closing_balance"], result[1]["closing_balance"]
        )

    @patch("app.api.provident_fund.date")
    def test_original_entries_not_mutated(self, mock_date):
        mock_date.today.return_value = date(2024, 3, 31)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        entry = {
            "company_name": "Test",
            "start_date": "2023-04-01",
            "end_date": "2024-03-31",
            "monthly_contribution": 5000,
            "interest_rate": 8.0,
        }
        original_keys = set(entry.keys())
        calculate_pf_corpus([entry])
        # Original dict should not have been modified
        self.assertEqual(set(entry.keys()), original_keys)


class TestProvidentFundServiceParser(unittest.TestCase):
    """Tests for ProvidentFundService._parse_row allowing rate=0."""

    def setUp(self):
        self.svc = ProvidentFundService.__new__(ProvidentFundService)

    def test_parse_row_with_manual_rate(self):
        row = ["Infosys", "2023-04-01", "2024-03-31", "5000", "8.25"]
        result = self.svc._parse_row(row, 2)
        self.assertEqual(result["company_name"], "Infosys")
        self.assertEqual(result["interest_rate"], 8.25)

    def test_parse_row_with_zero_rate_allowed(self):
        """Rate=0 should be accepted (auto-rate mode)."""
        row = ["Wipro", "2023-04-01", "", "6000", "0"]
        result = self.svc._parse_row(row, 3)
        self.assertEqual(result["interest_rate"], 0)
        self.assertEqual(result["company_name"], "Wipro")

    def test_parse_row_negative_rate_rejected(self):
        row = ["Bad Co", "2023-04-01", "", "5000", "-1"]
        with self.assertRaises(DataError):
            self.svc._parse_row(row, 4)

    def test_parse_row_missing_company_rejected(self):
        row = ["", "2023-04-01", "", "5000", "8.5"]
        with self.assertRaises(DataError):
            self.svc._parse_row(row, 5)

    def test_parse_row_zero_contribution_rejected(self):
        row = ["Test", "2023-04-01", "", "0", "8.5"]
        with self.assertRaises(DataError):
            self.svc._parse_row(row, 6)


if __name__ == "__main__":
    unittest.main()
