"""NSE equity master cache: symbol → canonical company name + ISIN.

Populated once daily via the NSE equity list CSV (EQUITY_L.csv).
Used by the company exposure analysis to convert trading symbols
(e.g. ``HDFCBANK``) to canonical names (e.g. ``HDFC Bank Limited``)
so they can be matched deterministically against mutual fund portfolio
data from Zerodha's CDN — which uses full company names, not symbols.
"""

import csv
import io
import threading
import time
from dataclasses import dataclass
from datetime import datetime

import requests

from ..constants import NSE_EQUITY_CSV_URL, NSE_EQUITY_TIMEOUT
from ..logging_config import logger


@dataclass(frozen=True)
class NSEEquityInfo:
    """Immutable snapshot of a single NSE-listed security."""

    symbol: str
    company_name: str  # NSE canonical name (e.g. "HDFC Bank Limited")
    isin: str
    series: str  # e.g. "EQ", "BE", "SM"


class NSEEquityCache:
    """Thread-safe in-memory cache for NSE symbol → equity info.

    Data is replaced atomically on each refresh — no LRU/TTL eviction.
    Reads are always consistent because the swap is done under a lock.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._symbol_map: dict[str, NSEEquityInfo] = {}
        self._last_refreshed_at: datetime | None = None

    def refresh(self, entries: list[NSEEquityInfo]) -> None:
        """Atomically replace cache contents with *entries*.

        Args:
            entries: Parsed list of NSEEquityInfo from EQUITY_L.csv.
        """
        symbol_map = {e.symbol: e for e in entries}
        with self._lock:
            self._symbol_map = symbol_map
            self._last_refreshed_at = datetime.now()
        logger.info("NSE equity cache refreshed: %d symbols loaded", len(symbol_map))

    def get(self, symbol: str) -> NSEEquityInfo | None:
        """Return equity info for *symbol* (e.g. ``'HDFCBANK'``), or None on miss."""
        with self._lock:
            return self._symbol_map.get(symbol.strip().upper())

    @property
    def is_populated(self) -> bool:
        """True when the cache has been loaded at least once."""
        with self._lock:
            return bool(self._symbol_map)

    @property
    def status(self) -> dict:
        """Return cron job status for health checks."""
        with self._lock:
            count = len(self._symbol_map)
            last_run_at = self._last_refreshed_at
        if last_run_at is None:
            return {"last_run": "never", "entries": count}
        return {
            "last_run": last_run_at.strftime("%d %b %Y, %I:%M %p"),
            "entries": count,
        }


# Module-level singleton — imported by the exposure module and scheduler.
nse_equity_cache = NSEEquityCache()


def fetch_and_cache_nse_equity() -> bool:
    """Fetch the NSE EQUITY_L.csv and refresh nse_equity_cache.

    The CSV is hosted on nsearchives.nseindia.com (static file server)
    and does not require an NSE session cookie — a plain GET suffices.

    Returns:
        True if the cache was refreshed successfully, False on error.
    """
    logger.info("NSE equity fetch started (url=%s)", NSE_EQUITY_CSV_URL)
    t0 = time.monotonic()
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(NSE_EQUITY_CSV_URL, headers=headers, timeout=NSE_EQUITY_TIMEOUT)
        resp.raise_for_status()
        entries = _parse_equity_csv(resp.content.decode("utf-8", errors="replace"))
        nse_equity_cache.refresh(entries)
        logger.info(
            "NSE equity fetch complete: %d entries in %.1fs",
            len(entries),
            time.monotonic() - t0,
        )
        return True
    except Exception as exc:
        logger.error("NSE equity fetch failed: %s", exc)
        return False


def _parse_equity_csv(text: str) -> list[NSEEquityInfo]:
    """Parse raw EQUITY_L.csv text into a list of NSEEquityInfo.

    CSV columns (positional order, header row present):
        SYMBOL, NAME OF COMPANY, SERIES, DATE OF LISTING,
        PAID UP VALUE, MARKET LOT, ISIN NUMBER, FACE VALUE

    Rows with an empty SYMBOL or ISIN are silently skipped.

    Args:
        text: Raw CSV text from NSE.

    Returns:
        List of NSEEquityInfo for all rows with a valid symbol and ISIN.
    """
    entries: list[NSEEquityInfo] = []
    # skipinitialspace strips the leading space NSE puts after each comma in
    # the header row (e.g. " ISIN NUMBER" → "ISIN NUMBER").
    reader = csv.DictReader(io.StringIO(text), skipinitialspace=True)
    for row in reader:
        symbol = (row.get("SYMBOL") or "").strip().upper()
        isin = (row.get("ISIN NUMBER") or "").strip().upper()
        name = (row.get("NAME OF COMPANY") or "").strip()
        series = (row.get("SERIES") or "").strip().upper()
        if not symbol or not isin:
            continue
        entries.append(NSEEquityInfo(symbol=symbol, company_name=name, isin=isin, series=series))
    return entries
