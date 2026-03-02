"""
Portfolio data cache and thread synchronization.
"""

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class PortfolioCache:
    """Container for all cached portfolio data."""
    stocks: List[Dict[str, Any]] = None
    mf_holdings: List[Dict[str, Any]] = None
    sips: List[Dict[str, Any]] = None
    nifty50: List[Dict[str, Any]] = None
    gold_prices: Dict[str, Dict[str, float]] = None
    gold_prices_last_fetch: Optional[datetime] = None
    market_indices: Dict[str, Any] = None
    market_indices_last_fetch: Optional[datetime] = None

    def __post_init__(self):
        self.stocks = self.stocks or []
        self.mf_holdings = self.mf_holdings or []
        self.sips = self.sips or []
        self.nifty50 = self.nifty50 or []
        self.gold_prices = self.gold_prices or {}


# Global cache instance
cache = PortfolioCache()

# Thread synchronization events
fetch_in_progress = threading.Event()
nifty50_fetch_in_progress = threading.Event()


# ---------------------------------------------------------------------------
# Per-user Google Sheets cache (avoids hitting Sheets on every page load)
# ---------------------------------------------------------------------------

_DEFAULT_USER_CACHE_TTL = 300  # 5 minutes

@dataclass
class _UserCacheEntry:
    physical_gold: List[Dict[str, Any]] = field(default_factory=list)
    fixed_deposits: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: float = 0.0


class UserSheetsCache:
    """TTL-based per-user cache for Google Sheets data (gold & FDs).

    Keyed by Google user ID. Thread-safe.
    """

    def __init__(self, ttl: int = _DEFAULT_USER_CACHE_TTL):
        self._ttl = ttl
        self._store: Dict[str, _UserCacheEntry] = {}
        self._lock = threading.Lock()

    def get(self, google_id: str) -> Optional[_UserCacheEntry]:
        with self._lock:
            entry = self._store.get(google_id)
            if entry and (time.monotonic() - entry.timestamp) < self._ttl:
                return entry
            return None

    def put(self, google_id: str, *, physical_gold: List = None, fixed_deposits: List = None) -> None:
        with self._lock:
            entry = self._store.get(google_id)
            now = time.monotonic()
            if entry is None:
                entry = _UserCacheEntry(timestamp=now)
                self._store[google_id] = entry
            if physical_gold is not None:
                entry.physical_gold = physical_gold
                entry.timestamp = now
            if fixed_deposits is not None:
                entry.fixed_deposits = fixed_deposits
                entry.timestamp = now

    def invalidate(self, google_id: str) -> None:
        with self._lock:
            self._store.pop(google_id, None)


user_sheets_cache = UserSheetsCache()
