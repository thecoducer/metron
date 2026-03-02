import logging
from typing import Optional

# Shared logger for the project. Modules can import this `logger` to avoid
# defining `logging.getLogger(__name__)` in every file. This logger uses a
# common name so handlers/formatters apply consistently across modules.

logger = logging.getLogger("metron")


def configure(level: int = logging.INFO, fmt: Optional[str] = None) -> None:
    """Configure root logging for the application.

    Call this once from the entry point (e.g., `server.main()`).
    """
    if fmt is None:
        # Use comma-separated milliseconds to match the example format:
        # 2025-11-29 20:34:42,819 INFO metron: message
        fmt = "%(asctime)s,%(msecs)03d %(levelname)s %(name)s: %(message)s"
    # Provide a datefmt so asctime contains the date/time without msecs;
    # msecs are inserted via %(msecs)03d in the format above.
    logging.basicConfig(level=level, format=fmt, datefmt="%Y-%m-%d %H:%M:%S")
    # Ensure our shared logger inherits configuration
    logger.setLevel(level)
    # Reduce noisy HTTP request logs from Flask's development server (Werkzeug)
    # by default; keep them at WARNING so normal request lines aren't logged
    # at INFO level unless the app or environment configures it otherwise.
    try:
        logging.getLogger('werkzeug').setLevel(logging.WARNING)
    except Exception:
        # Non-critical; if werkzeug isn't available just continue
        pass
