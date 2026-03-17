#!/usr/bin/env python3
"""
Metron Server — Application entry point (development mode).

For production deployment use:
    gunicorn wsgi:app -c gunicorn.conf.py

Development usage:
    python main.py
"""

import signal
import threading
import time

from dotenv import load_dotenv

load_dotenv()  # read .env into os.environ before any config is accessed

from .bootstrap import load_runtime_env

load_runtime_env()

from flask import Flask

from .config import app_config
from .constants import SERVER_STARTUP_DELAY
from .logging_config import configure, logger
from .routes import app_ui

# --------------------------
# SERVER MANAGEMENT
# --------------------------


def start_server(app: Flask, host: str, port: int) -> threading.Thread:
    """Start a Flask application in a background daemon thread.

    Args:
        app: Flask application instance.
        host: Host address to bind to.
        port: Port number to bind to.

    Returns:
        Thread running the Flask server.
    """

    def _run_server():
        app.run(host=host, port=port, debug=False, use_reloader=False)

    thread = threading.Thread(target=_run_server, daemon=True)
    thread.start()
    time.sleep(SERVER_STARTUP_DELAY)  # Allow server to start
    return thread


_shutdown_event = threading.Event()


def _handle_shutdown(signum, frame):
    """Handle SIGTERM/SIGINT for graceful shutdown."""
    sig_name = signal.Signals(signum).name
    logger.info("Received %s — shutting down gracefully...", sig_name)
    _shutdown_event.set()


def main() -> None:
    """Initialize and start the Metron application (development mode).

    1. Configures logging.
    2. Starts the UI Flask server.
    3. Keeps the application running until SIGTERM/SIGINT.
    """
    try:
        configure()
        logger.info("Starting Metron...")
        logger.info("NOTE: For production, use: gunicorn wsgi:app -c gunicorn.conf.py")

        # Register signal handlers
        signal.signal(signal.SIGTERM, _handle_shutdown)
        signal.signal(signal.SIGINT, _handle_shutdown)

        dashboard_url = f"http://{app_config.ui_host}:{app_config.ui_port}/"
        logger.info("Starting UI server at %s", dashboard_url)
        start_server(app_ui, app_config.ui_host, app_config.ui_port)

        # Eagerly initialise Firestore so the first request isn't slow.
        try:
            from .firebase_store import _db

            _db()
            logger.info("Firestore client warmed up")
        except Exception as exc:
            logger.warning("Firestore warm-up failed: %s", exc)

        logger.info("Servers ready. Press CTRL+C to stop.")

        # Block until shutdown signal
        _shutdown_event.wait()
        logger.info("Shutdown complete.")

    except KeyboardInterrupt:
        logger.info("\nShutting down gracefully...")
    except Exception as e:
        logger.exception("Fatal error occurred: %s", e)


if __name__ == "__main__":
    main()
