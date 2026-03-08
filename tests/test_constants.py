"""
Unit tests for constants
"""
import unittest

from app.constants import (HTTP_ACCEPTED, HTTP_CONFLICT, HTTP_OK, STATE_ERROR,
                           STATE_UPDATED, STATE_UPDATING,
                           NSE_REQUEST_TIMEOUT, NSE_REQUEST_DELAY,
                           GOOGLE_SHEETS_TIMEOUT, IBJA_GOLD_PRICE_TIMEOUT,
                           TOKEN_WAIT_POLL_INTERVAL,
                           EPF_HISTORICAL_RATES, EPF_DEFAULT_RATE)


class TestConstants(unittest.TestCase):
    """Test application constants"""
    
    def test_state_constants(self):
        """Test state constant values"""
        self.assertEqual(STATE_UPDATING, "updating")
        self.assertEqual(STATE_UPDATED, "updated")
        self.assertEqual(STATE_ERROR, "error")
    
    def test_http_status_constants(self):
        """Test HTTP status code constants"""
        self.assertEqual(HTTP_OK, 200)
        self.assertEqual(HTTP_ACCEPTED, 202)
        self.assertEqual(HTTP_CONFLICT, 409)
    
    def test_default_values(self):
        """Test default configuration values"""
        from app.constants import (
            DEFAULT_REQUEST_TOKEN_TIMEOUT,
            DEFAULT_UI_PORT)
        self.assertIsInstance(DEFAULT_UI_PORT, int)
        self.assertIsInstance(DEFAULT_REQUEST_TOKEN_TIMEOUT, int)
        self.assertGreater(DEFAULT_UI_PORT, 0)
        self.assertGreater(DEFAULT_REQUEST_TOKEN_TIMEOUT, 0)

    def test_api_timeout_constants(self):
        """Test that API timeout constants are positive numbers"""
        self.assertIsInstance(NSE_REQUEST_TIMEOUT, (int, float))
        self.assertGreater(NSE_REQUEST_TIMEOUT, 0)
        self.assertIsInstance(NSE_REQUEST_DELAY, (int, float))
        self.assertGreater(NSE_REQUEST_DELAY, 0)
        self.assertIsInstance(GOOGLE_SHEETS_TIMEOUT, (int, float))
        self.assertGreater(GOOGLE_SHEETS_TIMEOUT, 0)
        self.assertIsInstance(IBJA_GOLD_PRICE_TIMEOUT, (int, float))
        self.assertGreater(IBJA_GOLD_PRICE_TIMEOUT, 0)

    def test_timing_constants(self):
        """Test timing / polling constants"""
        self.assertIsInstance(TOKEN_WAIT_POLL_INTERVAL, (int, float))
        self.assertGreater(TOKEN_WAIT_POLL_INTERVAL, 0)

    def test_epf_historical_rates(self):
        """Test EPF rate table is well-formed"""
        self.assertIsInstance(EPF_HISTORICAL_RATES, dict)
        self.assertGreater(len(EPF_HISTORICAL_RATES), 10)
        for fy_year, rate in EPF_HISTORICAL_RATES.items():
            self.assertIsInstance(fy_year, int)
            self.assertGreater(rate, 0)
            self.assertLess(rate, 20)  # sanity check

    def test_epf_default_rate(self):
        """Test EPF default rate is reasonable"""
        self.assertIsInstance(EPF_DEFAULT_RATE, (int, float))
        self.assertGreater(EPF_DEFAULT_RATE, 0)
        self.assertLess(EPF_DEFAULT_RATE, 20)


if __name__ == '__main__':
    unittest.main()
