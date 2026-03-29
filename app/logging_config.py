import json
import logging
import os
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Shared logger for the project. Modules can import this `logger` to avoid
# defining `logging.getLogger(__name__)` in every file. This logger uses a
# common name so handlers/formatters apply consistently across modules.

logger = logging.getLogger("metron")


class _UTCFormatter(logging.Formatter):
    """Formatter that always emits timestamps in UTC."""

    converter = time.gmtime  # force UTC regardless of server timezone


class _JSONFormatter(logging.Formatter):
    """Emit one JSON object per line — ideal for Promtail/Loki ingestion."""

    def format(self, record: logging.LogRecord) -> str:
        ct = time.gmtime(record.created)
        ts = time.strftime("%Y-%m-%dT%H:%M:%S", ct)
        timestamp = f"{ts}.{int(record.msecs):03d}Z"
        entry: dict[str, object] = {
            "ts": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure(level: int | None = None, fmt: str | None = None) -> None:
    """Configure root logging for the application.

    Call this once from the entry point (e.g., `server.main()`).
    All timestamps are emitted in UTC for consistency across deployments.

    The log level is resolved in order: *level* argument → ``LOG_LEVEL``
    environment variable → ``logging.INFO`` default.

    Two handlers are installed:
    - **StreamHandler** (stdout) — human-readable for console / ``docker logs``
    - **RotatingFileHandler** (``logs/metron.log``) — JSON lines for Promtail
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

    def _utc_format_time(record: logging.LogRecord, datefmt: str | None = None) -> str:
        ct = time.gmtime(record.created)
        t = time.strftime("%Y-%m-%dT%H:%M:%S", ct)
        return f"{t}.{int(record.msecs):03d}Z"

    formatter.formatTime = _utc_format_time  # type: ignore[assignment]

    # Apply to root logger
    root = logging.getLogger()
    root.setLevel(level)

    # Only apply plain-text formatter to StreamHandlers (not file handlers)
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        root.addHandler(handler)
    else:
        for handler in root.handlers:
            if isinstance(handler, logging.StreamHandler) and not isinstance(
                handler, logging.FileHandler
            ):
                handler.setFormatter(formatter)

    # Add JSON file handler once — guard against duplicate calls
    has_json_handler = any(
        isinstance(h, RotatingFileHandler)
        and isinstance(h.formatter, _JSONFormatter)
        for h in root.handlers
    )
    if not has_json_handler:
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        json_handler = RotatingFileHandler(
            log_dir / "metron-json.log",
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
        )
        json_handler.setFormatter(_JSONFormatter())
        json_handler.setLevel(level)
        root.addHandler(json_handler)

    # Suppress noisy Werkzeug request logs
    try:
        logging.getLogger("werkzeug").setLevel(logging.WARNING)
    except Exception:
        pass

    # Ensure our shared logger inherits configuration
    logger.setLevel(level)

    # File handler — write to logs/ directory if it exists
    _project_root = Path(__file__).resolve().parent.parent
    _log_dir = _project_root / "logs"
    if _log_dir.is_dir():
        file_handler = RotatingFileHandler(
            _log_dir / "metron.log",
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        root.addHandler(file_handler)

    # Reduce noisy HTTP request logs from Flask's development server (Werkzeug)
    # by default; keep them at WARNING so normal request lines aren't logged
    # at INFO level unless the app or environment configures it otherwise.
    try:
        logging.getLogger("werkzeug").setLevel(logging.WARNING)
    except Exception:
        # Non-critical; if werkzeug isn't available just continue
        pass
