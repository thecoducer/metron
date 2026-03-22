import logging
import os
import time

# Shared logger for the project. Modules can import this `logger` to avoid
# defining `logging.getLogger(__name__)` in every file. This logger uses a
# common name so handlers/formatters apply consistently across modules.

logger = logging.getLogger("metron")


class _UTCFormatter(logging.Formatter):
    """Formatter that always emits timestamps in UTC."""

    converter = time.gmtime  # force UTC regardless of server timezone


def configure(level: int | None = None, fmt: str | None = None) -> None:
    """Configure root logging for the application.

    Call this once from the entry point (e.g., `server.main()`).
    All timestamps are emitted in UTC for consistency across deployments.

    The log level is resolved in order: *level* argument → ``LOG_LEVEL``
    environment variable → ``logging.INFO`` default.
    """
    if level is None:
        env_level = os.environ.get("LOG_LEVEL", "").upper()
        level = getattr(logging, env_level, None) if env_level else None
        if not isinstance(level, int):
            level = logging.INFO
    if fmt is None:
        fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"

    # Build a UTC-aware formatter with millisecond precision
    formatter = _UTCFormatter(fmt=fmt, datefmt="%Y-%m-%dT%H:%M:%SZ")
    # Override formatTime to include milliseconds in ISO-8601 UTC

    def _utc_format_time(record, datefmt=None):
        ct = time.gmtime(record.created)
        t = time.strftime("%Y-%m-%dT%H:%M:%S", ct)
        return f"{t}.{int(record.msecs):03d}Z"

    formatter.formatTime = _utc_format_time

    # Apply to root logger
    root = logging.getLogger()
    root.setLevel(level)
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        root.addHandler(handler)
    else:
        for handler in root.handlers:
            handler.setFormatter(formatter)

    # Ensure our shared logger inherits configuration
    logger.setLevel(level)
    # Reduce noisy HTTP request logs from Flask's development server (Werkzeug)
    # by default; keep them at WARNING so normal request lines aren't logged
    # at INFO level unless the app or environment configures it otherwise.
    try:
        logging.getLogger("werkzeug").setLevel(logging.WARNING)
    except Exception:
        # Non-critical; if werkzeug isn't available just continue
        pass
