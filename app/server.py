#!/usr/bin/env python3
"""
Metron Server — Application entry point.

Usage:
    1. Set up environment: pip install -r requirements.txt
    2. Configure accounts in config/config.json
    3. Run: python main.py   (or use start.sh)
"""

import threading
import time

from flask import Flask

from .config import app_config
from .constants import SERVER_STARTUP_DELAY
from .fetchers import fetch_nifty50_data, run_auto_refresh
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


def _start_auto_refresh_service() -> None:
    """Initialize and start the auto-refresh background service."""
    threading.Thread(target=run_auto_refresh, daemon=True).start()


def main() -> None:
    """Initialize and start the Metron application.

    1. Configures logging.
    2. Loads cached authentication sessions.
    3. Validates account configuration.
    4. Starts the UI Flask server.
    5. Triggers initial data fetch.
    6. Starts the auto-refresh service.
    7. Keeps the application running.
    """
    try:
        configure()
        logger.info("Starting Metron...")


        dashboard_url = f"http://{app_config.ui_host}:{app_config.ui_port}/"
        logger.info("Starting UI server at %s", dashboard_url)
        start_server(app_ui, app_config.ui_host, app_config.ui_port)

        logger.info("Servers ready. Press CTRL+C to stop.")

        logger.info("Fetching initial Nifty50 data...")
        fetch_nifty50_data()

        _start_auto_refresh_service()

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        logger.info("\nShutting down gracefully...")
    except Exception as e:
        logger.exception("Fatal error occurred: %s", e)


if __name__ == "__main__":
    main()
