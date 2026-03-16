"""Utilities for memory profiling specific functions (local development).

Usage in development:
    from app.debug import profile_memory
    
    @profile_memory
    def my_expensive_function():
        # Your code here
        pass
"""

import functools
from collections.abc import Callable
from typing import Any

from app.logging_config import logger
from app.memory_monitor import get_monitor


def profile_memory(func: Callable) -> Callable:
    """Decorator to profile memory usage of a function.

    Logs memory before/after function execution with delta.
    Shows peak memory during execution.

    Usage:
        @profile_memory
        def expensive_operation():
            pass
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        monitor = get_monitor()

        # Get initial state
        start_stats = monitor.get_memory_stats()
        start_mb = start_stats["rss_mb"] if start_stats else 0

        # Execute function
        result = func(*args, **kwargs)

        # Get final state
        end_stats = monitor.get_memory_stats()
        end_mb = end_stats["rss_mb"] if end_stats else 0
        delta_mb = end_mb - start_mb

        # Log with appropriate level
        if delta_mb > 50:
            logger.critical(
                "PROFILE: %s allocated %.1fMB (%.1f→%.1fMB)",
                func.__name__,
                delta_mb,
                start_mb,
                end_mb,
            )
        elif delta_mb > 20:
            logger.warning(
                "PROFILE: %s allocated %.1fMB (%.1f→%.1fMB)",
                func.__name__,
                delta_mb,
                start_mb,
                end_mb,
            )
        else:
            logger.info(
                "PROFILE: %s allocated %.1fMB (%.1f→%.1fMB)",
                func.__name__,
                delta_mb,
                start_mb,
                end_mb,
            )

        return result

    return wrapper


def log_memory_snapshot(label: str = "") -> None:
    """Log current memory snapshot with optional label.

    Usage:
        log_memory_snapshot("before_sync")
        log_memory_snapshot("after_sync")
    """
    monitor = get_monitor()
    stats = monitor.get_memory_stats()

    if stats:
        prefix = f"[{label}] " if label else ""
        logger.info(
            "%sMEMORY: %.1fMB / %.0fMB (%.0f%%)",
            prefix,
            stats["rss_mb"],
            stats["limit_mb"],
            stats["percent_of_limit"],
        )


def assert_memory_under(max_mb: int) -> None:
    """Assert current memory usage is under max_mb, useful for tests.

    Raises AssertionError if limit exceeded.

    Usage:
        assert_memory_under(100)  # Assert using less than 100MB
    """
    monitor = get_monitor()
    stats = monitor.get_memory_stats()

    if not stats:
        return

    if stats["rss_mb"] > max_mb:
        raise AssertionError(
            f"Memory usage {stats['rss_mb']:.1f}MB exceeds limit {max_mb}MB"
        )
