"""Per-user portfolio cache, global market cache, and Google Sheets TTL cache."""

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class UserPortfolioData:
    stocks: List[Dict[str, Any]] = field(default_factory=list)
    mf_holdings: List[Dict[str, Any]] = field(default_factory=list)
    sips: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class MarketCache:
    nifty50: List[Dict[str, Any]] = field(default_factory=list)
    gold_prices: Dict[str, Dict[str, float]] = field(default_factory=dict)
    gold_prices_last_fetch: Optional[datetime] = None
    market_indices: Dict[str, Any] = field(default_factory=dict)
    market_indices_last_fetch: Optional[datetime] = None


class PortfolioCacheManager:
    """Thread-safe per-user portfolio cache with fetch-in-progress tracking."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._user_data: Dict[str, UserPortfolioData] = {}
        self._fetch_events: Dict[str, threading.Event] = {}

    def get(self, google_id: str) -> UserPortfolioData:
        with self._lock:
            return self._user_data.setdefault(google_id, UserPortfolioData())

    def set(self, google_id: str, *, stocks: List = None,
            mf_holdings: List = None, sips: List = None) -> None:
        with self._lock:
            data = self._user_data.setdefault(google_id, UserPortfolioData())
        if stocks is not None:
            data.stocks = stocks
        if mf_holdings is not None:
            data.mf_holdings = mf_holdings
        if sips is not None:
            data.sips = sips

    def _get_event(self, google_id: str) -> threading.Event:
        with self._lock:
            return self._fetch_events.setdefault(google_id, threading.Event())

    def is_fetch_in_progress(self, google_id: str) -> bool:
        return self._get_event(google_id).is_set()

    def set_fetch_in_progress(self, google_id: str) -> None:
        self._get_event(google_id).set()

    def clear_fetch_in_progress(self, google_id: str) -> None:
        self._get_event(google_id).clear()

    def active_user_ids(self) -> List[str]:
        with self._lock:
            return list(self._user_data.keys())


market_cache = MarketCache()
portfolio_cache = PortfolioCacheManager()
nifty50_fetch_in_progress = threading.Event()


_SHEETS_CACHE_TTL = 300  # seconds

@dataclass
class _UserCacheEntry:
    physical_gold: List[Dict[str, Any]] = field(default_factory=list)
    fixed_deposits: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: float = 0.0


class UserSheetsCache:
    """TTL-based per-user cache for Google Sheets data. Thread-safe."""

    def __init__(self, ttl: int = _SHEETS_CACHE_TTL):
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
            now = time.monotonic()
            entry = self._store.setdefault(google_id, _UserCacheEntry(timestamp=now))
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
