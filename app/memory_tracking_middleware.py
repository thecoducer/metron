"""Flask middleware for per-request memory tracking."""

from flask import request, g
import time
from app.logging_config import logger
from app.memory_monitor import get_monitor


def setup_memory_tracking_middleware(app):
    """Register request hooks to track memory usage per request.

    This helps identify which endpoints are memory-intensive.
    """

    @app.before_request
    def _before_request():
        """Record memory and time at request start."""
        g.request_start_time = time.time()
        monitor = get_monitor()
        g.request_start_memory = monitor.get_memory_stats().get("rss_bytes", 0)

    @app.after_request
    def _after_request(response):
        """Log memory usage delta for the request."""
        if not hasattr(g, "request_start_time"):
            return response

        elapsed = time.time() - g.request_start_time
        monitor = get_monitor()
        end_stats = monitor.get_memory_stats()

        if not end_stats:
            return response

        start_memory_mb = g.request_start_memory / (1024 * 1024)
        end_memory_mb = end_stats["rss_bytes"] / (1024 * 1024)
        delta_mb = end_memory_mb - start_memory_mb

        # Log memory-intensive requests (> 5MB delta or > 400MB usage)
        if abs(delta_mb) > 5 or end_stats["rss_bytes"] > (400 * 1024 * 1024):
            log_level = "warning" if delta_mb > 10 else "info"
            log_func = logger.warning if log_level == "warning" else logger.info
            log_func(
                "Request: %s %s | Time: %.2fs | Memory: %.1f→%.1fMB (Δ%.1fMB) | Used: %.0f%%",
                request.method,
                request.path,
                elapsed,
                start_memory_mb,
                end_memory_mb,
                delta_mb,
                end_stats["percent_of_limit"],
            )

        # Check memory after request
        monitor.check_memory()

        return response

    logger.info("Memory tracking middleware registered")
