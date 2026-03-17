"""Per-user portfolio cache, global market cache, and Google Sheets LRU cache."""

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from cachetools import LRUCache

from .constants import (
    MAX_LTP_CACHE_SYMBOLS,
    MAX_PORTFOLIO_CACHE_USERS,
    MAX_SHEETS_CACHE_USERS,
    NEGATIVE_LTP_CACHE_TTL,
)


@dataclass
class UserPortfolioData:
    stocks: list[dict[str, Any]] = field(default_factory=list)
    mf_holdings: list[dict[str, Any]] = field(default_factory=list)
    sips: list[dict[str, Any]] = field(default_factory=list)
    connected_accounts: set[str] = field(default_factory=set)

    @property
    def broker_connected(self) -> bool:
        """True when at least one broker account has a live session."""
        return bool(self.connected_accounts)


@dataclass
class MarketCache:
    nifty50: list[dict[str, Any]] = field(default_factory=list)
    nifty50_last_fetch: datetime | None = None
    gold_prices: dict[str, dict[str, float]] = field(default_factory=dict)
    gold_prices_last_fetch: datetime | None = None
    market_indices: dict[str, Any] = field(default_factory=dict)
    market_indices_last_fetch: datetime | None = None


class PortfolioCacheManager:
    """Thread-safe per-user portfolio cache with LRU eviction.

    At most *maxsize* entries are kept.  The least-recently used user
    is evicted automatically when the cap is reached (via ``cachetools.LRUCache``).
    """

    def __init__(self, maxsize: int = MAX_PORTFOLIO_CACHE_USERS) -> None:
        self._lock = threading.Lock()
        self._user_data: LRUCache[str, UserPortfolioData] = LRUCache(maxsize=maxsize)
        self._fetch_events: dict[str, threading.Event] = {}

    def get(self, google_id: str) -> UserPortfolioData:
        """Return the cached portfolio for *google_id*, creating an empty one if absent."""
        with self._lock:
            data = self._user_data.get(google_id)
            if data is not None:
                return data
            data = UserPortfolioData()
            self._user_data[google_id] = data
            return data

    def set(
        self,
        google_id: str,
        *,
        stocks: list = None,
        mf_holdings: list = None,
        sips: list = None,
        connected_accounts: set = None,
    ) -> None:
        """Update one or more portfolio data fields for *google_id*."""
        with self._lock:
            data = self._user_data.get(google_id)
            if data is None:
                data = UserPortfolioData()
                self._user_data[google_id] = data
            else:
                # Touch to refresh LRU position
                self._user_data[google_id] = data
        if stocks is not None:
            data.stocks = stocks
        if mf_holdings is not None:
            data.mf_holdings = mf_holdings
        if sips is not None:
            data.sips = sips
        if connected_accounts is not None:
            data.connected_accounts = connected_accounts

    def _get_event(self, google_id: str) -> threading.Event:
        """Return the fetch-in-progress event for *google_id*, creating one if absent."""
        with self._lock:
            return self._fetch_events.setdefault(google_id, threading.Event())

    def is_fetch_in_progress(self, google_id: str) -> bool:
        """Return True if a background portfolio fetch is running for this user."""
        return self._get_event(google_id).is_set()

    def set_fetch_in_progress(self, google_id: str) -> None:
        """Mark a background portfolio fetch as running."""
        self._get_event(google_id).set()

    def clear_fetch_in_progress(self, google_id: str) -> None:
        """Mark a background portfolio fetch as finished."""
        self._get_event(google_id).clear()

    def clear(self, google_id: str) -> None:
        """Remove all cached portfolio data for *google_id*."""
        with self._lock:
            self._user_data.pop(google_id, None)

    def active_user_ids(self) -> list[str]:
        """Return google_ids of all users with cached portfolio data."""
        with self._lock:
            return list(self._user_data.keys())


market_cache = MarketCache()
portfolio_cache = PortfolioCacheManager()
nifty50_fetch_in_progress = threading.Event()


@dataclass
class _UserCacheEntry:
    physical_gold: list[dict[str, Any]] = field(default_factory=list)
    fixed_deposits: list[dict[str, Any]] = field(default_factory=list)
    stocks: list[dict[str, Any]] = field(default_factory=list)
    etfs: list[dict[str, Any]] = field(default_factory=list)
    mutual_funds: list[dict[str, Any]] = field(default_factory=list)
    sips: list[dict[str, Any]] = field(default_factory=list)
    timestamp: float = 0.0
    # Track which sheet types have actually been fetched vs just default-empty
    _fetched_sheets: set = field(default_factory=set)


class UserSheetsCache:
    """Per-user cache for Google Sheets data with LRU eviction.

    Uses ``cachetools.LRUCache`` for size-bounded eviction only.
    """

    def __init__(self, maxsize: int = MAX_SHEETS_CACHE_USERS):
        self._store: LRUCache[str, _UserCacheEntry] = LRUCache(maxsize=maxsize)
        self._lock = threading.Lock()

    def get(self, google_id: str) -> _UserCacheEntry | None:
        """Return the cache entry for *google_id* if present."""
        with self._lock:
            return self._store.get(google_id)

    def put(self, google_id: str, *, physical_gold: list = None, fixed_deposits: list = None) -> None:
        """Cache one or more sheet data types for *google_id*."""
        with self._lock:
            entry = self._store.get(google_id)
            if entry is None:
                entry = _UserCacheEntry()
            if physical_gold is not None:
                entry.physical_gold = physical_gold
            if fixed_deposits is not None:
                entry.fixed_deposits = fixed_deposits
            # Re-insert to refresh LRU position
            self._store[google_id] = entry

    # ── Sheet-entry helpers (stocks / etfs / mutual_funds / sips) ──

    _SHEET_ATTR = {
        "stocks": "stocks",
        "etfs": "etfs",
        "mutual_funds": "mutual_funds",
        "sips": "sips",
    }

    def get_manual(self, google_id: str, sheet_type: str) -> list | None:
        """Return cached entries for *sheet_type*, or None on miss."""
        attr = self._SHEET_ATTR.get(sheet_type)
        if not attr:
            return None
        with self._lock:
            entry = self._store.get(google_id)
            if entry and sheet_type in entry._fetched_sheets:
                return getattr(entry, attr)
            return None

    def put_manual(self, google_id: str, sheet_type: str, rows: list) -> None:
        """Cache entries for *sheet_type*."""
        attr = self._SHEET_ATTR.get(sheet_type)
        if not attr:
            return
        with self._lock:
            entry = self._store.get(google_id)
            if entry is None:
                entry = _UserCacheEntry()
            setattr(entry, attr, rows)
            entry._fetched_sheets.add(sheet_type)
            # Re-insert to refresh LRU position
            self._store[google_id] = entry

    # ── Batch helpers ──

    _ALL_MANUAL_TYPES = frozenset(_SHEET_ATTR)

    def is_fully_cached(self, google_id: str) -> bool:
        """Return True when gold, FDs, and all 4 manual sheet types are cached."""
        with self._lock:
            entry = self._store.get(google_id)
            if not entry:
                return False
            return self._ALL_MANUAL_TYPES.issubset(entry._fetched_sheets)

    def put_all(
        self,
        google_id: str,
        *,
        physical_gold: list = None,
        fixed_deposits: list = None,
        manual: dict[str, list] = None,
    ) -> None:
        """Cache gold, FDs, and all manual sheet types in one call."""
        with self._lock:
            entry = self._store.get(google_id)
            if entry is None:
                entry = _UserCacheEntry()
            if physical_gold is not None:
                entry.physical_gold = physical_gold
            if fixed_deposits is not None:
                entry.fixed_deposits = fixed_deposits
            if manual:
                for sheet_type, rows in manual.items():
                    attr = self._SHEET_ATTR.get(sheet_type)
                    if attr:
                        setattr(entry, attr, rows)
                        entry._fetched_sheets.add(sheet_type)
            # Re-insert to refresh LRU position
            self._store[google_id] = entry

    def invalidate(self, google_id: str) -> None:
        """Remove all cached sheet data for *google_id*."""
        with self._lock:
            self._store.pop(google_id, None)


user_sheets_cache = UserSheetsCache()


class ManualLTPCache:
    """Thread-safe LRU cache for manually-added stock/ETF last traded prices.

    Stores NSE quote data (ltp, change, pChange) keyed by symbol.
    Capped at *maxsize* entries via ``cachetools.LRUCache``.

    Negative lookups (unresolved symbols) use a 5-minute TTL to allow
    periodic retries for temporarily unavailable symbols.
    """

    _NEGATIVE_TTL = NEGATIVE_LTP_CACHE_TTL  # 5 minutes

    def __init__(self, maxsize: int = MAX_LTP_CACHE_SYMBOLS):
        self._data: LRUCache[str, dict[str, Any]] = LRUCache(maxsize=maxsize)
        self._negative: dict[str, float] = {}
        self._lock = threading.Lock()
        self._cancel = threading.Event()

    # -- Read --

    def get(self, symbol: str) -> dict[str, Any] | None:
        """Return cached quote data for *symbol*, or None on miss."""
        with self._lock:
            return self._data.get(symbol)

    def is_negative(self, symbol: str) -> bool:
        """Return True if *symbol* was recently recorded as unresolvable."""
        with self._lock:
            ts = self._negative.get(symbol)
            if ts is None:
                return False
            if (time.monotonic() - ts) >= self._NEGATIVE_TTL:
                del self._negative[symbol]
                return False
            return True

    # -- Write --

    def put(self, symbol: str, data: dict[str, Any]) -> None:
        """Cache quote data for *symbol* and remove any negative entry."""
        with self._lock:
            self._data[symbol] = data
            self._negative.pop(symbol, None)

    def put_batch(self, data: dict[str, dict[str, Any]]) -> None:
        """Cache quote data for multiple symbols at once."""
        with self._lock:
            for symbol, quote in data.items():
                self._data[symbol] = quote
                self._negative.pop(symbol, None)

    def put_negative_batch(self, symbols: list) -> None:
        """Record symbols as unresolvable (negative lookup) with a 5-minute TTL."""
        with self._lock:
            now = time.monotonic()
            for sym in symbols:
                self._negative[sym] = now

    # -- Control --

    @property
    def cancel_flag(self) -> threading.Event:
        """Event checked by background fetch threads to abort early."""
        return self._cancel

    def invalidate(self) -> None:
        """Clear all data and cancel in-flight background fetches."""
        with self._lock:
            self._data.clear()
            self._negative.clear()
        self._cancel.set()
        self._cancel = threading.Event()


manual_ltp_cache = ManualLTPCache()
