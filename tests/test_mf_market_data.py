"""Tests for MF market data cache and fetcher (app/api/mf_market_data.py)."""

import json
from unittest.mock import MagicMock, patch

from app.api.mf_market_data import MFMarketCache, _process_mf_api_response, fetch_and_cache_market_data

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_raw_item(scheme_code, name, isin_growth=None, isin_div=None, nav="10.0", date="20-Mar-2026"):
    return {
        "schemeCode": scheme_code,
        "schemeName": name,
        "isinGrowth": isin_growth,
        "isinDivReinvestment": isin_div,
        "nav": nav,
        "date": date,
    }


def _make_scheme(scheme_code, name, isin, nav="10.0", date="20-Mar-2026"):
    return {"schemeCode": scheme_code, "schemeName": name, "isin": isin, "nav": nav, "date": date}


# ---------------------------------------------------------------------------
# MFMarketCache
# ---------------------------------------------------------------------------


class TestMFMarketCache:
    def setup_method(self):
        self.cache = MFMarketCache()

    def _load(self):
        schemes = [
            _make_scheme("101", "Axis Bluechip Fund Direct Growth", "INF846K01DP8", nav="42.56"),
            _make_scheme("102", "SBI Bluechip Fund Direct Growth", "INF200KA1RJ6", nav="75.12"),
            _make_scheme("103", "HDFC Flexi Cap Fund Growth", "INF179KA1QZ5", nav="100.00"),
        ]
        self.cache.refresh(schemes)

    def test_is_populated_false_initially(self):
        assert not self.cache.is_populated

    def test_is_populated_after_refresh(self):
        self._load()
        assert self.cache.is_populated

    def test_refresh_builds_isin_map(self):
        self._load()
        scheme = self.cache.get_by_isin("INF846K01DP8")
        assert scheme is not None
        assert scheme.scheme_name == "Axis Bluechip Fund Direct Growth"
        assert scheme.latest_nav == "42.56"

    def test_get_by_isin_case_insensitive(self):
        self._load()
        assert self.cache.get_by_isin("inf846k01dp8") is not None

    def test_get_by_isin_unknown_returns_none(self):
        self._load()
        assert self.cache.get_by_isin("UNKNOWN_ISIN") is None

    def test_get_isin_for_name_exact_match(self):
        self._load()
        isin = self.cache.get_isin_for_name("Axis Bluechip Fund Direct Growth")
        assert isin == "INF846K01DP8"

    def test_get_isin_for_name_unknown_returns_none(self):
        self._load()
        assert self.cache.get_isin_for_name("Nonexistent Fund") is None

    def test_name_list_is_sorted(self):
        self._load()
        names = list(self.cache._name_list)
        assert names == sorted(names)

    def test_search_names_substring_match(self):
        self._load()
        results = self.cache.search_names("bluechip")
        assert len(results) == 2
        assert all("Bluechip" in r for r in results)

    def test_search_names_case_insensitive(self):
        self._load()
        assert self.cache.search_names("AXIS") == self.cache.search_names("axis")

    def test_search_names_empty_query_returns_empty(self):
        self._load()
        assert self.cache.search_names("") == []

    def test_search_names_short_query_still_works(self):
        # Single-char query is allowed at the cache level (caller enforces min length)
        self._load()
        results = self.cache.search_names("H")
        assert "HDFC Flexi Cap Fund Growth" in results

    def test_search_names_respects_limit(self):
        schemes = [_make_scheme(str(i), f"Test Fund {i:03d}", f"INF000K{i:04d}9") for i in range(50)]
        self.cache.refresh(schemes)
        results = self.cache.search_names("test", limit=5)
        assert len(results) == 5

    def test_search_names_default_limit_is_20(self):
        schemes = [_make_scheme(str(i), f"Growth Fund {i:03d}", f"INF000K{i:04d}9") for i in range(30)]
        self.cache.refresh(schemes)
        results = self.cache.search_names("growth")
        assert len(results) == 20

    def test_refresh_builds_correct_holdings_url(self):
        self._load()
        scheme = self.cache.get_by_isin("INF846K01DP8")
        assert scheme is not None
        assert scheme.holdings_url == "https://staticassets.zerodha.com/coin/scheme-portfolio/INF846K01DP8.json"

    def test_refresh_is_atomic(self):
        """Cache replace is atomic — a second refresh should fully replace first."""
        self.cache.refresh([_make_scheme("1", "Old Fund", "OLD_ISIN")])
        self.cache.refresh([_make_scheme("2", "New Fund", "NEW_ISIN")])
        assert self.cache.get_by_isin("OLD_ISIN") is None
        assert self.cache.get_by_isin("NEW_ISIN") is not None


# ---------------------------------------------------------------------------
# _process_mf_api_response
# ---------------------------------------------------------------------------


class TestProcessMFApiResponse:
    def test_filters_items_with_no_isin(self):
        data = [
            _make_raw_item(1, "Fund A", isin_growth=None, isin_div=None),
            _make_raw_item(2, "Fund B", isin_growth="INF001K01RQ2", isin_div=None),
        ]
        result = _process_mf_api_response(data)
        assert len(result) == 1
        assert result[0]["schemeName"] == "Fund B"

    def test_prioritises_isin_growth_over_div(self):
        data = [_make_raw_item(1, "Fund", isin_growth="GROWTH_ISIN", isin_div="DIV_ISIN")]
        result = _process_mf_api_response(data)
        assert result[0]["isin"] == "GROWTH_ISIN"

    def test_falls_back_to_div_when_growth_absent(self):
        data = [_make_raw_item(1, "Fund", isin_growth=None, isin_div="DIV_ISIN")]
        result = _process_mf_api_response(data)
        assert result[0]["isin"] == "DIV_ISIN"

    def test_empty_string_isin_treated_as_absent(self):
        data = [_make_raw_item(1, "Fund", isin_growth="", isin_div="")]
        result = _process_mf_api_response(data)
        assert len(result) == 0

    def test_whitespace_only_isin_treated_as_absent(self):
        data = [_make_raw_item(1, "Fund", isin_growth="  ", isin_div=" ")]
        result = _process_mf_api_response(data)
        assert len(result) == 0

    def test_preserves_scheme_fields(self):
        # mfapi.in returns dates as DD-MM-YYYY; the processor converts to ISO YYYY-MM-DD.
        data = [_make_raw_item(42, "Axis Fund", isin_growth="INF846K01DP8", nav="55.5", date="21-03-2026")]
        result = _process_mf_api_response(data)
        assert result[0]["schemeCode"] == 42
        assert result[0]["nav"] == "55.5"
        assert result[0]["date"] == "2026-03-21"

    def test_date_non_numeric_month_unchanged(self):
        # Dates with non-numeric month component are left unchanged.
        data = [_make_raw_item(1, "Fund", isin_growth="INF123", date="21-Mar-2026")]
        result = _process_mf_api_response(data)
        assert result[0]["date"] == "21-Mar-2026"

    def test_empty_input_returns_empty(self):
        assert _process_mf_api_response([]) == []

    def test_all_filtered_returns_empty(self):
        data = [_make_raw_item(i, f"Fund {i}", None, None) for i in range(5)]
        assert _process_mf_api_response(data) == []


# ---------------------------------------------------------------------------
# fetch_and_cache_market_data
# ---------------------------------------------------------------------------


class TestFetchAndCacheMarketData:
    def test_successful_fetch_populates_cache(self):
        raw = [_make_raw_item(1, "Axis Bluechip", isin_growth="INF846K01DP8", nav="42.5", date="20-Mar-2026")]
        mock_resp = MagicMock()
        mock_resp.content = json.dumps(raw).encode()
        mock_resp.raise_for_status.return_value = None

        from app.api.mf_market_data import mf_market_cache

        with patch("requests.Session") as MockSession:
            mock_session = MockSession.return_value.__enter__.return_value
            mock_session.get.return_value = mock_resp
            result = fetch_and_cache_market_data()

        assert result is True
        assert mf_market_cache.is_populated

    def test_all_retries_exhausted_returns_false(self):
        """Fails on every attempt → returns False after MF_API_MAX_RETRIES tries."""
        with patch("requests.Session") as MockSession, patch("time.sleep"):
            mock_session = MockSession.return_value.__enter__.return_value
            mock_session.get.side_effect = ConnectionError("unreachable")
            result = fetch_and_cache_market_data()
        assert result is False

    def test_retries_then_succeeds(self):
        """Fails twice, succeeds on the third attempt → returns True."""
        raw = [_make_raw_item(1, "Axis Bluechip", isin_growth="INF846K01DP8")]
        good_resp = MagicMock()
        good_resp.content = json.dumps(raw).encode()
        good_resp.raise_for_status.return_value = None

        call_count = {"n": 0}

        def side_effect(*_a, **_kw):
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise ConnectionError("transient error")
            return good_resp

        with patch("requests.Session") as MockSession, patch("time.sleep"):
            mock_session = MockSession.return_value.__enter__.return_value
            mock_session.get.side_effect = side_effect
            result = fetch_and_cache_market_data()

        assert result is True
        assert call_count["n"] == 3

    def test_bad_status_retries_and_fails(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("503 Service Unavailable")

        with patch("requests.Session") as MockSession, patch("time.sleep"):
            mock_session = MockSession.return_value.__enter__.return_value
            mock_session.get.return_value = mock_resp
            result = fetch_and_cache_market_data()
        assert result is False

    def test_all_filtered_still_returns_true(self):
        """An empty result (all schemes filtered) is not an error."""
        raw = [_make_raw_item(1, "Fund", None, None)]
        mock_resp = MagicMock()
        mock_resp.content = json.dumps(raw).encode()
        mock_resp.raise_for_status.return_value = None

        with patch("requests.Session") as MockSession:
            mock_session = MockSession.return_value.__enter__.return_value
            mock_session.get.return_value = mock_resp
            result = fetch_and_cache_market_data()
        assert result is True
