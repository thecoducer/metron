#!/usr/bin/env python3
"""
WSGI entry point for production deployment (Gunicorn on Render).

Usage:
    gunicorn wsgi:app -c gunicorn.conf.py
"""

from dotenv import load_dotenv

load_dotenv()  # must run before any app imports that read os.environ

import signal
import sys

from app.logging_config import configure, logger
from app.routes import app_ui
from app.memory_monitor import start_memory_monitoring
from app.memory_tracking_middleware import setup_memory_tracking_middleware

# Configure logging before anything else
configure()

# Expose the Flask app for Gunicorn / Vercel
app = app_ui

# Start memory monitoring (emits snapshots every 60 seconds to stderr)
start_memory_monitoring(interval=60)

# Register per-request memory tracking middleware
setup_memory_tracking_middleware(app)


def _graceful_shutdown(signum, frame):
    """Handle SIGTERM from container orchestrator."""
    sig_name = signal.Signals(signum).name
    logger.info("Received %s — shutting down gracefully...", sig_name)
    sys.exit(0)


# Register signal handlers for graceful shutdown
signal.signal(signal.SIGTERM, _graceful_shutdown)
signal.signal(signal.SIGINT, _graceful_shutdown)
