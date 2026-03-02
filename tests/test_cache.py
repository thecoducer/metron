"""
Unit tests for cache.py (PortfolioCache and thread events).
"""
import unittest

from app.cache import (PortfolioCache, cache, fetch_in_progress,
                       nifty50_fetch_in_progress)


class TestPortfolioCache(unittest.TestCase):
    """Test PortfolioCache initialization."""

    def test_default_initialization(self):
        c = PortfolioCache()
        self.assertEqual(c.stocks, [])
        self.assertEqual(c.mf_holdings, [])
        self.assertEqual(c.sips, [])
        self.assertEqual(c.nifty50, [])
        self.assertEqual(c.gold_prices, {})
        self.assertIsNone(c.gold_prices_last_fetch)

    def test_global_cache_is_instance(self):
        self.assertIsInstance(cache, PortfolioCache)

    def test_thread_events_default_unset(self):
        self.assertFalse(fetch_in_progress.is_set())
        self.assertFalse(nifty50_fetch_in_progress.is_set())


if __name__ == '__main__':
    unittest.main()
