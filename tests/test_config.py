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


    def test_no_session_cache_file(self):
        """AppConfig should no longer have a session_cache_file attribute."""
        self.assertFalse(hasattr(app_config, 'session_cache_file'))


if __name__ == '__main__':
    unittest.main()
