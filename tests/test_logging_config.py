"""
Unit tests for logging_config.py — UTC formatter and configure().
"""

import logging
import time
import unittest
from unittest.mock import patch

from app.logging_config import _UTCFormatter, configure, logger


class TestUTCFormatter(unittest.TestCase):
    def test_converter_is_gmtime(self):
        self.assertIs(_UTCFormatter.converter, time.gmtime)

    def test_formats_record(self):
        formatter = _UTCFormatter(fmt="%(asctime)s %(message)s")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="hello",
            args=(),
            exc_info=None,
        )
        formatted = formatter.format(record)
        self.assertIn("hello", formatted)


class TestConfigure(unittest.TestCase):
    def setUp(self):
        # Save original state
        self._root = logging.getLogger()
        self._orig_handlers = list(self._root.handlers)
        self._orig_level = self._root.level

    def tearDown(self):
        # Restore original state
        self._root.handlers = self._orig_handlers
        self._root.setLevel(self._orig_level)

    def test_configure_sets_level(self):
        configure(level=logging.DEBUG)
        self.assertEqual(logger.level, logging.DEBUG)

    def test_configure_default_format(self):
        # Remove existing handlers so configure() creates a new one
        root = logging.getLogger()
        root.handlers.clear()
        configure()
        self.assertTrue(len(root.handlers) >= 1)

    def test_configure_custom_format(self):
        root = logging.getLogger()
        root.handlers.clear()
        configure(fmt="%(message)s")
        self.assertTrue(len(root.handlers) >= 1)

    def test_configure_existing_handlers(self):
        root = logging.getLogger()
        handler = logging.StreamHandler()
        root.handlers = [handler]
        configure()
        # Should update formatter on existing handler, not add new
        self.assertIsNotNone(handler.formatter)

    def test_utc_format_time_produces_utc_string(self):
        root = logging.getLogger()
        root.handlers.clear()
        configure()
        handler = root.handlers[0]
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test",
            args=(),
            exc_info=None,
        )
        # pyrefly: ignore [missing-attribute]
        formatted = handler.formatter.formatTime(record)
        self.assertTrue(formatted.endswith("Z"))
        self.assertIn("T", formatted)

    def test_werkzeug_logger_suppressed(self):
        configure()
        werkzeug_logger = logging.getLogger("werkzeug")
        self.assertEqual(werkzeug_logger.level, logging.WARNING)

    def test_logger_is_metron(self):
        self.assertEqual(logger.name, "metron")

    def test_werkzeug_logger_exception_caught(self):
        """Cover lines 58-60: exception in werkzeug logger suppression."""
        import logging as _logging

        werkzeug_logger = _logging.getLogger("werkzeug")
        with patch.object(werkzeug_logger, "setLevel", side_effect=Exception("boom")):
            # Should not raise — exception is caught
            configure()


if __name__ == "__main__":
    unittest.main()
