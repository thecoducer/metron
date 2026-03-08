"""
Unit tests for config.py (AppConfig).
"""
import os
import unittest
from unittest.mock import patch

from app.config import AppConfig, app_config


class TestAppConfig(unittest.TestCase):
    """Test AppConfig dataclass and loading."""

    def test_singleton_loaded(self):
        """Module-level app_config should be an AppConfig instance."""
        self.assertIsInstance(app_config, AppConfig)

    def test_from_env_defaults(self):
        """from_env uses defaults when no env vars are set."""
        with patch.dict(os.environ, {}, clear=True):
            cfg = AppConfig.from_env()
        self.assertEqual(cfg.ui_host, "127.0.0.1")
        self.assertEqual(cfg.ui_port, 8000)
        self.assertEqual(cfg.request_token_timeout, 180)
        self.assertFalse(cfg.features.get("allow_browser_api_access"))

    def test_from_env_custom_values(self):
        """from_env respects environment overrides."""
        env = {
            "METRON_UI_HOST": "0.0.0.0",
            "METRON_UI_PORT": "9000",
            "METRON_REQUEST_TOKEN_TIMEOUT": "300",
            "METRON_ALLOW_BROWSER_API_ACCESS": "1",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = AppConfig.from_env()
        self.assertEqual(cfg.ui_host, "0.0.0.0")
        self.assertEqual(cfg.ui_port, 9000)
        self.assertEqual(cfg.request_token_timeout, 300)
        self.assertTrue(cfg.features["allow_browser_api_access"])

    def test_no_session_cache_file(self):
        """AppConfig should no longer have a session_cache_file attribute."""
        self.assertFalse(hasattr(app_config, 'session_cache_file'))


if __name__ == '__main__':
    unittest.main()
