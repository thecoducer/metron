"""
Unit tests for config.py (AppConfig).
"""
import unittest

from app.config import AppConfig, app_config


class TestAppConfig(unittest.TestCase):
    """Test AppConfig dataclass and loading."""

    def test_singleton_loaded(self):
        """Module-level app_config should be an AppConfig instance."""
        self.assertIsInstance(app_config, AppConfig)

    def test_redirect_url_format(self):
        """redirect_url should combine callback host, port, and path."""
        expected = f"http://{app_config.callback_host}:{app_config.callback_port}{app_config.callback_path}"
        self.assertEqual(app_config.redirect_url, expected)

    def test_no_session_cache_file(self):
        """AppConfig should no longer have a session_cache_file attribute."""
        self.assertFalse(hasattr(app_config, 'session_cache_file'))


if __name__ == '__main__':
    unittest.main()
