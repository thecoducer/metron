"""
Unit tests for cache.py (per-user PortfolioCacheManager, MarketCache, UserSheetsCache, ManualLTPCache).
"""

import time
import unittest

from app.cache import (
    ManualLTPCache,
    MarketCache,
    PortfolioCacheManager,
    UserPortfolioData,
    UserSheetsCache,
    manual_ltp_cache,
    market_cache,
    nifty50_fetch_in_progress,
    portfolio_cache,
    user_sheets_cache,
)


class TestUserPortfolioData(unittest.TestCase):
    """Test UserPortfolioData dataclass."""

    def test_default_initialization(self):
        data = UserPortfolioData()
        self.assertEqual(data.stocks, [])
        self.assertEqual(data.mf_holdings, [])
        self.assertEqual(data.sips, [])


class TestMarketCache(unittest.TestCase):
    """Test MarketCache global data container."""

    def test_default_initialization(self):
        mc = MarketCache()
        self.assertEqual(mc.nifty50, [])
        self.assertEqual(mc.gold_prices, {})
        self.assertIsNone(mc.gold_prices_last_fetch)
        self.assertEqual(mc.market_indices, {})
        self.assertIsNone(mc.market_indices_last_fetch)

    def test_global_market_cache_is_instance(self):
        self.assertIsInstance(market_cache, MarketCache)


class TestPortfolioCacheManager(unittest.TestCase):
    """Test PortfolioCacheManager per-user caching."""

    def setUp(self):
        self.manager = PortfolioCacheManager()

    def test_get_creates_empty_data_for_new_user(self):
        data = self.manager.get("user1")
        self.assertIsInstance(data, UserPortfolioData)
        self.assertEqual(data.stocks, [])
        self.assertEqual(data.mf_holdings, [])
        self.assertEqual(data.sips, [])

    def test_get_returns_same_instance_for_same_user(self):
        data1 = self.manager.get("user1")
        data2 = self.manager.get("user1")
        self.assertIs(data1, data2)

    def test_get_returns_different_data_per_user(self):
        data1 = self.manager.get("user1")
        data2 = self.manager.get("user2")
        self.assertIsNot(data1, data2)

    def test_set_updates_cache(self):
        stocks = [{"symbol": "INFY", "qty": 10}]
        mfs = [{"fund": "Fund A"}]
        sips = [{"sip": "SIP1"}]
        self.manager.set("user1", stocks=stocks, mf_holdings=mfs, sips=sips)

        data = self.manager.get("user1")
        self.assertEqual(data.stocks, stocks)
        self.assertEqual(data.mf_holdings, mfs)
        self.assertEqual(data.sips, sips)

    def test_set_partial_update(self):
        self.manager.set("user1", stocks=[{"s": 1}])
        self.manager.set("user1", mf_holdings=[{"m": 1}])
        data = self.manager.get("user1")
        self.assertEqual(data.stocks, [{"s": 1}])
        self.assertEqual(data.mf_holdings, [{"m": 1}])
        self.assertEqual(data.sips, [])

    def test_user_isolation(self):
        """Data for user1 must not leak to user2."""
        self.manager.set("user1", stocks=[{"u1": True}])
        self.manager.set("user2", stocks=[{"u2": True}])

        self.assertEqual(self.manager.get("user1").stocks, [{"u1": True}])
        self.assertEqual(self.manager.get("user2").stocks, [{"u2": True}])

    def test_fetch_in_progress_default_false(self):
        self.assertFalse(self.manager.is_fetch_in_progress("user1"))

    def test_set_and_clear_fetch_in_progress(self):
        self.manager.set_fetch_in_progress("user1")
        self.assertTrue(self.manager.is_fetch_in_progress("user1"))
        self.manager.clear_fetch_in_progress("user1")
        self.assertFalse(self.manager.is_fetch_in_progress("user1"))

    def test_fetch_in_progress_per_user(self):
        """Fetch lock for user1 must not affect user2."""
        self.manager.set_fetch_in_progress("user1")
        self.assertTrue(self.manager.is_fetch_in_progress("user1"))
        self.assertFalse(self.manager.is_fetch_in_progress("user2"))

    def test_active_user_ids(self):
        self.manager.get("user1")
        self.manager.get("user2")
        ids = self.manager.active_user_ids()
        self.assertIn("user1", ids)
        self.assertIn("user2", ids)

    def test_clear_removes_user_data(self):
        """clear() removes cached portfolio data for the user."""
        self.manager.set("user1", stocks=[{"s": 1}], mf_holdings=[{"m": 1}])
        self.manager.clear("user1")
        # After clear, get() should return fresh empty data
        data = self.manager.get("user1")
        self.assertEqual(data.stocks, [])
        self.assertEqual(data.mf_holdings, [])
        self.assertEqual(data.sips, [])

    def test_clear_does_not_affect_other_users(self):
        """clear() for one user must not affect another."""
        self.manager.set("user1", stocks=[{"u1": True}])
        self.manager.set("user2", stocks=[{"u2": True}])
        self.manager.clear("user1")
        self.assertEqual(self.manager.get("user2").stocks, [{"u2": True}])

    def test_clear_nonexistent_user_no_error(self):
        """clear() on a user with no cached data should not raise."""
        self.manager.clear("nonexistent")

    def test_global_portfolio_cache_is_instance(self):
        self.assertIsInstance(portfolio_cache, PortfolioCacheManager)


class TestUserSheetsCache(unittest.TestCase):
    """Test UserSheetsCache LRU-based caching."""

    def test_put_and_get(self):
        usc = UserSheetsCache()
        usc.put("user1", physical_gold=[{"g": 1}], fixed_deposits=[{"fd": 1}])
        entry = usc.get("user1")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.physical_gold, [{"g": 1}])
        self.assertEqual(entry.fixed_deposits, [{"fd": 1}])

    def test_get_returns_none_for_missing_user(self):
        usc = UserSheetsCache()
        self.assertIsNone(usc.get("nonexistent"))

    def test_get_does_not_expire_by_time(self):
        usc = UserSheetsCache()
        usc.put("user1", physical_gold=[{"g": 1}])
        time.sleep(0.01)
        self.assertIsNotNone(usc.get("user1"))

    def test_invalidate(self):
        usc = UserSheetsCache()
        usc.put("user1", physical_gold=[{"g": 1}])
        usc.invalidate("user1")
        self.assertIsNone(usc.get("user1"))

    def test_user_isolation(self):
        usc = UserSheetsCache()
        usc.put("user1", physical_gold=[{"u1": True}])
        usc.put("user2", physical_gold=[{"u2": True}])
        # pyrefly: ignore [missing-attribute]
        self.assertEqual(usc.get("user1").physical_gold, [{"u1": True}])
        # pyrefly: ignore [missing-attribute]
        self.assertEqual(usc.get("user2").physical_gold, [{"u2": True}])

    def test_lru_eviction_by_maxsize(self):
        usc = UserSheetsCache(maxsize=1)
        usc.put("user1", physical_gold=[{"u1": True}])
        usc.put("user2", physical_gold=[{"u2": True}])
        self.assertIsNone(usc.get("user1"))
        self.assertIsNotNone(usc.get("user2"))

    def test_global_instance(self):
        self.assertIsInstance(user_sheets_cache, UserSheetsCache)

    # ── is_fully_cached ──

    def test_is_fully_cached_false_when_empty(self):
        usc = UserSheetsCache()
        self.assertFalse(usc.is_fully_cached("user1"))

    def test_is_fully_cached_false_with_only_gold_fd(self):
        usc = UserSheetsCache()
        usc.put("user1", physical_gold=[{"g": 1}], fixed_deposits=[{"fd": 1}])
        self.assertFalse(usc.is_fully_cached("user1"))

    def test_is_fully_cached_true_after_put_all(self):
        usc = UserSheetsCache()
        usc.put_all(
            "user1",
            physical_gold=[{"g": 1}],
            fixed_deposits=[{"fd": 1}],
            manual={"stocks": [{"s": 1}], "etfs": [], "mutual_funds": [], "sips": []},
        )
        self.assertTrue(usc.is_fully_cached("user1"))

    def test_is_fully_cached_false_after_eviction(self):
        usc = UserSheetsCache(maxsize=1)
        usc.put_all(
            "user1",
            physical_gold=[],
            fixed_deposits=[],
            manual={"stocks": [], "etfs": [], "mutual_funds": [], "sips": []},
        )
        usc.put("user2", physical_gold=[])
        self.assertFalse(usc.is_fully_cached("user1"))

    # ── put_all ──

    def test_put_all_populates_gold_fd_and_manual(self):
        usc = UserSheetsCache()
        usc.put_all(
            "user1",
            physical_gold=[{"g": 1}],
            fixed_deposits=[{"fd": 1}],
            manual={"stocks": [{"s": 1}], "etfs": [{"e": 1}], "mutual_funds": [{"m": 1}], "sips": [{"p": 1}]},
        )
        entry = usc.get("user1")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.physical_gold, [{"g": 1}])
        self.assertEqual(entry.fixed_deposits, [{"fd": 1}])
        self.assertEqual(usc.get_manual("user1", "stocks"), [{"s": 1}])
        self.assertEqual(usc.get_manual("user1", "etfs"), [{"e": 1}])
        self.assertEqual(usc.get_manual("user1", "mutual_funds"), [{"m": 1}])
        self.assertEqual(usc.get_manual("user1", "sips"), [{"p": 1}])


class TestGlobalThreadEvents(unittest.TestCase):
    def test_nifty50_fetch_in_progress_default_unset(self):
        self.assertFalse(nifty50_fetch_in_progress.is_set())


class TestManualLTPCache(unittest.TestCase):
    """Test ManualLTPCache for manual stock/ETF LTP caching."""

    def setUp(self):
        self.cache = ManualLTPCache()

    def test_get_returns_none_initially(self):
        self.assertIsNone(self.cache.get("INFY"))

    def test_put_and_get(self):
        self.cache.put("INFY", {"ltp": 1500, "change": 10})
        result = self.cache.get("INFY")
        # pyrefly: ignore [unsupported-operation]
        self.assertEqual(result["ltp"], 1500)

    def test_put_removes_negative_cache(self):
        self.cache.put_negative_batch(["INFY"])
        self.assertTrue(self.cache.is_negative("INFY"))
        self.cache.put("INFY", {"ltp": 100})
        self.assertFalse(self.cache.is_negative("INFY"))

    def test_put_batch(self):
        data = {
            "INFY": {"ltp": 1500},
            "TCS": {"ltp": 3500},
        }
        self.cache.put_batch(data)
        # pyrefly: ignore [unsupported-operation]
        self.assertEqual(self.cache.get("INFY")["ltp"], 1500)
        # pyrefly: ignore [unsupported-operation]
        self.assertEqual(self.cache.get("TCS")["ltp"], 3500)

    def test_put_batch_removes_negatives(self):
        self.cache.put_negative_batch(["INFY"])
        self.cache.put_batch({"INFY": {"ltp": 1500}})
        self.assertFalse(self.cache.is_negative("INFY"))

    def test_put_negative_batch(self):
        self.cache.put_negative_batch(["UNKNOWN1", "UNKNOWN2"])
        self.assertTrue(self.cache.is_negative("UNKNOWN1"))
        self.assertTrue(self.cache.is_negative("UNKNOWN2"))

    def test_is_negative_false_initially(self):
        self.assertFalse(self.cache.is_negative("INFY"))

    def test_is_negative_expires_after_ttl(self):
        self.cache._NEGATIVE_TTL = 0  # expire immediately
        self.cache.put_negative_batch(["EXPIRED"])
        time.sleep(0.01)
        self.assertFalse(self.cache.is_negative("EXPIRED"))

    def test_cancel_flag_is_event(self):
        import threading

        self.assertIsInstance(self.cache.cancel_flag, threading.Event)

    def test_invalidate_clears_all(self):
        self.cache.put("INFY", {"ltp": 100})
        self.cache.put_negative_batch(["BAD"])
        self.cache.invalidate()
        self.assertIsNone(self.cache.get("INFY"))
        self.assertFalse(self.cache.is_negative("BAD"))

    def test_global_manual_ltp_cache_is_instance(self):
        self.assertIsInstance(manual_ltp_cache, ManualLTPCache)


class TestUserSheetsCacheManual(unittest.TestCase):
    """Test UserSheetsCache get_manual/put_manual methods."""

    def test_get_manual_unknown_type(self):
        usc = UserSheetsCache()
        self.assertIsNone(usc.get_manual("user1", "unknown_type"))

    def test_put_manual_unknown_type_noop(self):
        usc = UserSheetsCache()
        usc.put_manual("user1", "unknown_type", [{"a": 1}])
        self.assertIsNone(usc.get_manual("user1", "unknown_type"))

    def test_get_manual_not_fetched_returns_none(self):
        """get_manual returns None when the sheet type hasn't been fetched yet."""
        usc = UserSheetsCache()
        usc.put("user1", physical_gold=[{"g": 1}])  # only gold
        self.assertIsNone(usc.get_manual("user1", "stocks"))

    def test_put_manual_and_get_manual(self):
        usc = UserSheetsCache()
        usc.put_manual("user1", "stocks", [{"symbol": "INFY"}])
        result = usc.get_manual("user1", "stocks")
        self.assertEqual(result, [{"symbol": "INFY"}])

    def test_get_manual_evicted_returns_none(self):
        usc = UserSheetsCache(maxsize=1)
        usc.put_manual("user1", "etfs", [{"x": 1}])
        usc.put_manual("user2", "etfs", [{"y": 1}])
        self.assertIsNone(usc.get_manual("user1", "etfs"))

    def test_put_all_with_unknown_manual_type_ignored(self):
        usc = UserSheetsCache()
        usc.put_all("user1", manual={"unknown": [{"a": 1}], "stocks": [{"s": 1}]})
        self.assertIsNone(usc.get_manual("user1", "unknown"))
        self.assertEqual(usc.get_manual("user1", "stocks"), [{"s": 1}])

    def test_put_all_without_optional_args(self):
        usc = UserSheetsCache()
        usc.put_all("user1")
        entry = usc.get("user1")
        self.assertIsNotNone(entry)


if __name__ == "__main__":
    unittest.main()
