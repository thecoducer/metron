"""Mutual fund market data: in-memory cache and mfapi.in fetcher.

Provides a thread-safe singleton cache populated by a daily cron job.
The cache holds three data structures for efficient lookups:
  - isin_map:      ISIN → MFSchemeInfo  (O(1) by ISIN)
  - name_to_isin:  scheme name → ISIN   (O(1) by name)
  - name_list:     sorted list of all scheme names (for autocomplete)
"""

import threading
import time
from dataclasses import dataclass
from datetime import datetime

import requests

from ..constants import (
    COMPANY_HOLDINGS_URL_TEMPLATE,
    MF_API_MAX_RETRIES,
    MF_API_RETRY_DELAY,
    MF_API_TIMEOUT,
    MF_API_URL,
)
from ..logging_config import logger


@dataclass(frozen=True)
class MFSchemeInfo:
    """Immutable snapshot of a single mutual fund scheme."""

    scheme_code: str
    scheme_name: str
    isin: str
    latest_nav: str
    nav_updated_date: str
    holdings_url: str


class MFMarketCache:
    """Thread-safe in-memory cache for mutual fund market data.

    Data is replaced atomically on every refresh — no LRU/TTL eviction.
    Reads are always consistent because the swap is done under a lock.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._isin_map: dict[str, MFSchemeInfo] = {}
        self._name_list: list[str] = []
        self._name_to_isin: dict[str, str] = {}
        self._last_refreshed: float | None = None
        self._last_refreshed_at: datetime | None = None

    def refresh(self, schemes: list[dict]) -> None:
        """Atomically replace cache contents with fresh data.

        Args:
            schemes: Processed list of scheme dicts from mfapi.in.
        """
        isin_map: dict[str, MFSchemeInfo] = {}
        name_to_isin: dict[str, str] = {}

        for s in schemes:
            isin = s["isin"]
            name = s["schemeName"]
            info = MFSchemeInfo(
                scheme_code=str(s.get("schemeCode", "")),
                scheme_name=name,
                isin=isin,
                latest_nav=str(s.get("nav", "")),
                nav_updated_date=str(s.get("date", "")),
                holdings_url=COMPANY_HOLDINGS_URL_TEMPLATE.format(isin=isin),
            )
            isin_map[isin] = info
            name_to_isin[name] = isin

        name_list = sorted(name_to_isin.keys())

        with self._lock:
            self._isin_map = isin_map
            self._name_list = name_list
            self._name_to_isin = name_to_isin
            self._last_refreshed = time.monotonic()
            self._last_refreshed_at = datetime.now()

        logger.info("MF market cache refreshed: %d schemes loaded", len(isin_map))

    def get_by_isin(self, isin: str) -> MFSchemeInfo | None:
        """Look up scheme info by ISIN (case-insensitive)."""
        with self._lock:
            return self._isin_map.get(isin.strip().upper())

    def get_isin_for_name(self, name: str) -> str | None:
        """Return the ISIN for an exact scheme name, or None if not found."""
        with self._lock:
            return self._name_to_isin.get(name.strip())

    def search_names(self, query: str, *, limit: int = 20) -> list[str]:
        """Return up to *limit* scheme names that contain *query* (case-insensitive).

        Args:
            query: Search string entered by the user.
            limit: Maximum number of results to return.

        Returns:
            List of matching scheme names, in lexicographic order.
        """
        q = query.strip().lower()
        if not q:
            return []
        with self._lock:
            results = [name for name in self._name_list if q in name.lower()]
        return results[:limit]

    @property
    def is_populated(self) -> bool:
        """True when the cache has been loaded at least once."""
        with self._lock:
            return bool(self._name_list)

    @property
    def status(self) -> dict:
        """Return cron job status for health checks."""
        with self._lock:
            count = len(self._isin_map)
            last_run_at = self._last_refreshed_at
        if last_run_at is None:
            return {"last_run": "never", "entries": count}
        return {
            "last_run": last_run_at.strftime("%d %b %Y, %I:%M %p"),
            "entries": count,
        }


# Module-level singleton — imported by routes and scheduler.
mf_market_cache = MFMarketCache()


def fetch_and_cache_market_data() -> bool:
    """Fetch the full mutual fund list from mfapi.in and refresh mf_market_cache.

    Filters out schemes where both isinGrowth and isinDivReinvestment are absent.
    Prioritises isinGrowth over isinDivReinvestment when both are present.

    Retries up to MF_API_MAX_RETRIES times with exponential backoff on failure.

    Returns:
        True if the cache was refreshed successfully, False after all retries exhausted.
    """
    logger.info("MF market data fetch started (url=%s)", MF_API_URL)
    t0 = time.monotonic()
    data: list[dict] = []

    for attempt in range(1, MF_API_MAX_RETRIES + 1):
        try:
            response = requests.get(MF_API_URL, timeout=MF_API_TIMEOUT)
            response.raise_for_status()
            data = response.json()
            logger.info("MF API responded: %d raw entries in %.1fs", len(data), time.monotonic() - t0)
            break
        except Exception as exc:
            logger.error("MF market data fetch attempt %d/%d failed: %s", attempt, MF_API_MAX_RETRIES, exc)
            if attempt < MF_API_MAX_RETRIES:
                delay = MF_API_RETRY_DELAY * (2 ** (attempt - 1))  # exponential backoff: 5s, 10s
                logger.info("Retrying in %ds...", delay)
                time.sleep(delay)
            else:
                logger.error("All %d MF market data fetch attempts failed", MF_API_MAX_RETRIES)
                return False

    schemes = _process_mf_api_response(data)
    mf_market_cache.refresh(schemes)
    logger.info("MF market data fetch complete: %d schemes cached in %.1fs", len(schemes), time.monotonic() - t0)
    return True


def _dd_mm_yyyy_to_iso(date_str: str) -> str:
    """Convert DD-MM-YYYY to YYYY-MM-DD. Returns input unchanged for other formats."""
    parts = date_str.split("-")
    if (
        len(parts) == 3
        and len(parts[0]) == 2
        and len(parts[1]) == 2
        and len(parts[2]) == 4
        and all(p.isdigit() for p in parts)
    ):
        return f"{parts[2]}-{parts[1]}-{parts[0]}"
    return date_str


def _process_mf_api_response(data: list[dict]) -> list[dict]:
    """Filter and normalise the raw mfapi.in response.

    Args:
        data: Raw list of scheme objects from the API.

    Returns:
        Cleaned list of scheme dicts, each guaranteed to have a non-empty 'isin'.
    """
    schemes: list[dict] = []

    for item in data:
        isin_growth = (item.get("isinGrowth") or "").strip()
        isin_div = (item.get("isinDivReinvestment") or "").strip()

        # Skip schemes with no usable ISIN.
        if not isin_growth and not isin_div:
            continue

        # Prioritise the growth-plan ISIN; fall back to dividend-reinvestment.
        isin = isin_growth or isin_div

        schemes.append(
            {
                "schemeCode": item.get("schemeCode", ""),
                "schemeName": item.get("schemeName", ""),
                "isin": isin,
                "nav": item.get("nav", ""),
                "date": _dd_mm_yyyy_to_iso(str(item.get("date", ""))),
            }
        )

    return schemes
