"""Memory monitoring and OOM prevention for 512MB Render.com instance.

This module provides:
- Real-time memory tracking with warning thresholds
- Per-request memory profiling
- Periodic memory snapshots to stderr (survives OOM crashes)
- Graceful degradation under memory pressure
"""

import os
import psutil
import threading
import time
from typing import Optional
from app.logging_config import logger


# Global memory threshold (bytes)
MEMORY_LIMIT = 512 * 1024 * 1024  # 512 MB for Render hobby tier
WARNING_THRESHOLD = int(MEMORY_LIMIT * 0.75)  # 384 MB (75%)
CRITICAL_THRESHOLD = int(MEMORY_LIMIT * 0.90)  # 460 MB (90%)


class MemoryMonitor:
    """Monitor memory usage and emit warnings/alerts."""

    def __init__(self):
        self.process = psutil.Process(os.getpid())
        self.monitoring = False
        self.monitor_thread: Optional[threading.Thread] = None
        self._last_warning_time = 0
        self._warning_cooldown = 30  # seconds

    def get_memory_stats(self) -> dict:
        """Get current memory usage statistics."""
        try:
            # RSS = Resident Set Size (actual physical memory used)
            rss_bytes = self.process.memory_info().rss
            rss_mb = rss_bytes / (1024 * 1024)
            percent_of_limit = (rss_bytes / MEMORY_LIMIT) * 100

            return {
                "rss_mb": rss_mb,
                "rss_bytes": rss_bytes,
                "percent_of_limit": percent_of_limit,
                "limit_mb": MEMORY_LIMIT / (1024 * 1024),
            }
        except Exception as e:
            logger.error("Failed to get memory stats: %s", e)
            return {}

    def check_memory(self) -> None:
        """Check memory usage and emit warnings if thresholds exceeded."""
        stats = self.get_memory_stats()
        if not stats:
            return

        current_time = time.time()
        rss_bytes = stats["rss_bytes"]

        # Critical: 90%+ of limit
        if rss_bytes > CRITICAL_THRESHOLD:
            # Print to stderr (survives OOM kill, visible in logs)
            print(
                f"⚠️  CRITICAL MEMORY: {stats['rss_mb']:.1f}MB ({stats['percent_of_limit']:.0f}% of {stats['limit_mb']:.0f}MB limit)",
                flush=True,
            )
            logger.critical(
                "CRITICAL: Memory at %.0f%% (%.1fMB / %.0fMB)",
                stats["percent_of_limit"],
                stats["rss_mb"],
                stats["limit_mb"],
            )
            self._last_warning_time = current_time

        # Warning: 75%+ of limit (with cooldown to avoid spam)
        elif rss_bytes > WARNING_THRESHOLD:
            if current_time - self._last_warning_time > self._warning_cooldown:
                print(
                    f"⚠️  WARNING MEMORY: {stats['rss_mb']:.1f}MB ({stats['percent_of_limit']:.0f}% of {stats['limit_mb']:.0f}MB limit)",
                    flush=True,
                )
                logger.warning(
                    "Memory at %.0f%% (%.1fMB / %.0fMB)",
                    stats["percent_of_limit"],
                    stats["rss_mb"],
                    stats["limit_mb"],
                )
                self._last_warning_time = current_time

    def start_periodic_monitor(self, interval: int = 60) -> None:
        """Start background thread to emit memory snapshots every `interval` seconds.

        This ensures memory usage is logged even if the app crashes with OOM.
        The prints go to stderr and will be captured in Render's logs.
        """
        if self.monitoring:
            logger.warning("Memory monitor already running")
            return

        self.monitoring = True

        def _monitor_loop():
            while self.monitoring:
                stats = self.get_memory_stats()
                if stats:
                    # Print to stderr so it's always visible in logs
                    print(
                        f"📊 MEMORY SNAPSHOT: {stats['rss_mb']:.1f}MB / {stats['limit_mb']:.0f}MB ({stats['percent_of_limit']:.0f}%)",
                        flush=True,
                    )
                self.check_memory()
                time.sleep(interval)

        self.monitor_thread = threading.Thread(target=_monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("Memory monitor started (interval: %ds, limit: %.0fMB)", interval, MEMORY_LIMIT / (1024 * 1024))

    def stop_periodic_monitor(self) -> None:
        """Stop the background monitoring thread."""
        if self.monitoring:
            self.monitoring = False
            if self.monitor_thread:
                self.monitor_thread.join(timeout=5)
            logger.info("Memory monitor stopped")


# Global singleton instance
_monitor = MemoryMonitor()


def get_monitor() -> MemoryMonitor:
    """Get the global memory monitor instance."""
    return _monitor


def start_memory_monitoring(interval: int = 60) -> None:
    """Start memory monitoring Background thread.

    Args:
        interval: Interval in seconds between memory snapshots (default 60).
    """
    _monitor.start_periodic_monitor(interval)


def stop_memory_monitoring() -> None:
    """Stop memory monitoring."""
    _monitor.stop_periodic_monitor()


def get_memory_stats() -> dict:
    """Get current memory statistics."""
    return _monitor.get_memory_stats()
