"""
Unit tests for server.py (application entry point).
"""
import signal
import threading
import time
import unittest
from unittest.mock import Mock, patch

from app.server import start_server


class TestStartServer(unittest.TestCase):
    """Test server management functions."""

    def test_start_server_creates_daemon_thread(self):
        """Test start_server creates daemon thread and starts Flask app."""
        mock_app = Mock()
        mock_app.run = Mock()

        thread = start_server(mock_app, '127.0.0.1', 8000)

        self.assertIsInstance(thread, threading.Thread)
        self.assertTrue(thread.daemon)

        # Give thread time to start
        time.sleep(0.6)

        mock_app.run.assert_called_once_with(
            host='127.0.0.1',
            port=8000,
            debug=False,
            use_reloader=False,
        )


class TestHandleShutdown(unittest.TestCase):
    def test_sets_shutdown_event(self):
        from app.server import _handle_shutdown, _shutdown_event
        import signal
        _shutdown_event.clear()
        _handle_shutdown(signal.SIGTERM, None)
        self.assertTrue(_shutdown_event.is_set())
        _shutdown_event.clear()  # reset for other tests


class TestMain(unittest.TestCase):
    @patch("app.server._shutdown_event")
    @patch("app.server.start_server")
    @patch("app.server.configure")
    @patch("app.server.signal.signal")
    def test_main_runs(self, mock_sig, mock_configure, mock_start, mock_event):
        from app.server import main
        mock_event.wait.return_value = None  # simulate immediate shutdown
        main()
        mock_configure.assert_called_once()
        mock_start.assert_called_once()

    @patch("app.server._shutdown_event")
    @patch("app.server.configure", side_effect=KeyboardInterrupt)
    def test_main_keyboard_interrupt(self, mock_configure, mock_event):
        from app.server import main
        main()  # should not raise

    @patch("app.server._shutdown_event")
    @patch("app.server.configure", side_effect=RuntimeError("fatal"))
    def test_main_fatal_error(self, mock_configure, mock_event):
        from app.server import main
        main()  # should not raise


if __name__ == '__main__':
    unittest.main()
