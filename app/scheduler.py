"""Background cron scheduler for periodic data refreshes.

Uses APScheduler's BackgroundScheduler to run jobs in daemon threads
without blocking the Flask request loop.

Jobs:
  - market_data_refresh: daily at MARKET_DATA_CRON_HOUR_IST (2 AM IST)

On startup the scheduler also fires the market data fetch immediately in a
background thread so the cache is warm before the first cron run.
"""

import threading

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .constants import MARKET_DATA_CRON_HOUR_IST
from .logging_config import logger

_scheduler: BackgroundScheduler | None = None


def _run_market_data_fetch() -> None:
    """Cron task: fetch and cache market data."""
    from .api.mf_market_data import fetch_and_cache_market_data

    fetch_and_cache_market_data()


def start_scheduler() -> None:
    """Start APScheduler and register all recurring jobs.

    Also fires an immediate market data fetch in a daemon thread so the
    cache is populated on startup without delaying server boot.
    Safe to call multiple times — subsequent calls are no-ops.
    """
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        logger.warning("Scheduler already running — skipping start")
        return

    _scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

    _scheduler.add_job(
        _run_market_data_fetch,
        trigger=CronTrigger(hour=MARKET_DATA_CRON_HOUR_IST, minute=0, timezone="Asia/Kolkata"),
        id="market_data_refresh",
        name="Market Data Daily Refresh",
        # Allow up to 1 hour late execution (e.g. if server was down at 2 AM).
        misfire_grace_time=3600,
        # If multiple firings were missed, run only the latest one.
        coalesce=True,
    )

    _scheduler.start()
    logger.info(
        "Scheduler started — market data refresh scheduled daily at %02d:00 IST",
        MARKET_DATA_CRON_HOUR_IST,
    )

    # Trigger an immediate fetch in a non-blocking daemon thread.
    threading.Thread(target=_run_market_data_fetch, name="MarketDataInitialFetch", daemon=True).start()
    logger.info("Initial market data fetch triggered in background")


def stop_scheduler() -> None:
    """Gracefully stop the scheduler (call on server shutdown)."""
    global _scheduler

    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
