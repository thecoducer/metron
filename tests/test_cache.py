"""
Unit tests for cache.py (per-user PortfolioCacheManager, MarketCache, UserSheetsCache).
"""
import time
import unittest

from app.cache import (MarketCache, PortfolioCacheManager, UserPortfolioData,
                       UserSheetsCache, market_cache,
                       nifty50_fetch_in_progress, portfolio_cache,
                       user_sheets_cache)


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
    """Test UserSheetsCache TTL-based caching."""

    def test_put_and_get(self):
        usc = UserSheetsCache(ttl=60)
        usc.put("user1", physical_gold=[{"g": 1}], fixed_deposits=[{"fd": 1}])
        entry = usc.get("user1")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.physical_gold, [{"g": 1}])
        self.assertEqual(entry.fixed_deposits, [{"fd": 1}])

    def test_get_returns_none_for_missing_user(self):
        usc = UserSheetsCache(ttl=60)
        self.assertIsNone(usc.get("nonexistent"))

    def test_get_returns_none_after_ttl(self):
        usc = UserSheetsCache(ttl=0)  # immediate expiry
        usc.put("user1", physical_gold=[{"g": 1}])
        time.sleep(0.01)
        self.assertIsNone(usc.get("user1"))

    def test_invalidate(self):
        usc = UserSheetsCache(ttl=60)
        usc.put("user1", physical_gold=[{"g": 1}])
        usc.invalidate("user1")
        self.assertIsNone(usc.get("user1"))

    def test_user_isolation(self):
        usc = UserSheetsCache(ttl=60)
        usc.put("user1", physical_gold=[{"u1": True}])
        usc.put("user2", physical_gold=[{"u2": True}])
        self.assertEqual(usc.get("user1").physical_gold, [{"u1": True}])
        self.assertEqual(usc.get("user2").physical_gold, [{"u2": True}])

    def test_global_instance(self):
        self.assertIsInstance(user_sheets_cache, UserSheetsCache)

    # ── is_fully_cached ──

    def test_is_fully_cached_false_when_empty(self):
        usc = UserSheetsCache(ttl=60)
        self.assertFalse(usc.is_fully_cached("user1"))

    def test_is_fully_cached_false_with_only_gold_fd(self):
        usc = UserSheetsCache(ttl=60)
        usc.put("user1", physical_gold=[{"g": 1}], fixed_deposits=[{"fd": 1}])
        self.assertFalse(usc.is_fully_cached("user1"))

    def test_is_fully_cached_true_after_put_all(self):
        usc = UserSheetsCache(ttl=60)
        usc.put_all("user1",
                     physical_gold=[{"g": 1}],
                     fixed_deposits=[{"fd": 1}],
                     manual={"stocks": [{"s": 1}], "etfs": [],
                             "mutual_funds": [], "sips": []})
        self.assertTrue(usc.is_fully_cached("user1"))

    def test_is_fully_cached_false_after_ttl(self):
        usc = UserSheetsCache(ttl=0)
        usc.put_all("user1",
                     physical_gold=[], fixed_deposits=[],
                     manual={"stocks": [], "etfs": [],
                             "mutual_funds": [], "sips": []})
        time.sleep(0.01)
        self.assertFalse(usc.is_fully_cached("user1"))

    # ── put_all ──

    def test_put_all_populates_gold_fd_and_manual(self):
        usc = UserSheetsCache(ttl=60)
        usc.put_all("user1",
                     physical_gold=[{"g": 1}],
                     fixed_deposits=[{"fd": 1}],
                     manual={"stocks": [{"s": 1}], "etfs": [{"e": 1}],
                             "mutual_funds": [{"m": 1}], "sips": [{"p": 1}]})
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


if __name__ == '__main__':
    unittest.main()
