#!/usr/bin/env python3
"""
WSGI entry point for production deployment (Gunicorn on Render).

Usage:
    gunicorn wsgi:app -c gunicorn.conf.py
"""

from dotenv import load_dotenv

load_dotenv()  # must run before any app imports that read os.environ

from app.bootstrap import load_runtime_env

load_runtime_env()

import signal
import sys

from app.logging_config import configure, logger
from app.routes import app_ui

# Configure logging before anything else
configure()

# Expose the Flask app for Gunicorn / Vercel
app = app_ui


def _graceful_shutdown(signum, frame):
    """Handle SIGTERM from container orchestrator."""
    sig_name = signal.Signals(signum).name
    logger.info("Received %s — shutting down gracefully...", sig_name)
    sys.exit(0)


# Register signal handlers for graceful shutdown
signal.signal(signal.SIGTERM, _graceful_shutdown)
signal.signal(signal.SIGINT, _graceful_shutdown)
