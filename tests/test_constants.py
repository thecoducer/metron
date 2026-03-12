"""
Unit tests for constants
"""

import unittest

from app.constants import (
    GOOGLE_SHEETS_TIMEOUT,
    HTTP_ACCEPTED,
    HTTP_CONFLICT,
    HTTP_OK,
    IBJA_GOLD_PRICE_TIMEOUT,
    NSE_REQUEST_TIMEOUT,
    STATE_ERROR,
    STATE_UPDATED,
    STATE_UPDATING,
)


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
        from app.constants import DEFAULT_REQUEST_TOKEN_TIMEOUT, DEFAULT_UI_PORT

        self.assertIsInstance(DEFAULT_UI_PORT, int)
        self.assertIsInstance(DEFAULT_REQUEST_TOKEN_TIMEOUT, int)
        self.assertGreater(DEFAULT_UI_PORT, 0)
        self.assertGreater(DEFAULT_REQUEST_TOKEN_TIMEOUT, 0)

    def test_api_timeout_constants(self):
        """Test that API timeout constants are positive numbers"""
        self.assertIsInstance(NSE_REQUEST_TIMEOUT, (int, float))
        self.assertGreater(NSE_REQUEST_TIMEOUT, 0)
        self.assertIsInstance(GOOGLE_SHEETS_TIMEOUT, (int, float))
        self.assertGreater(GOOGLE_SHEETS_TIMEOUT, 0)
        self.assertIsInstance(IBJA_GOLD_PRICE_TIMEOUT, (int, float))
        self.assertGreater(IBJA_GOLD_PRICE_TIMEOUT, 0)


if __name__ == "__main__":
    unittest.main()
