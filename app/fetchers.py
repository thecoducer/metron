"""Background data fetching (on-demand).

Portfolio fetching is per-user; market data (Nifty 50, gold) is global.
Manual stock/ETF LTP fetching is per-user and non-blocking.
"""

import threading
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any

# Reduce thread stack size from default 8 MB to 512 KB.
# Background threads only run HTTP calls and light parsing.
threading.stack_size(524288)

from requests.exceptions import ConnectionError, Timeout

from .api import MarketDataClient
from .api.google_sheets_client import is_blank_row
from .api.ibja_gold_price import get_gold_price_service
from .cache import manual_ltp_cache, market_cache, nifty50_fetch_in_progress, portfolio_cache, user_sheets_cache
from .constants import (
    GOLD_PRICE_FETCH_HOURS,
    LTP_CACHE_WARMUP_ATTEMPTS,
    LTP_CACHE_WARMUP_INTERVAL,
    MARKET_DATA_MIN_INTERVAL,
    NIFTY50_FALLBACK_SYMBOLS,
    USER_FETCH_LOCKS_MAX,
)
from .logging_config import logger
from .services import get_authenticated_accounts, state_manager, zerodha_client

# ===================================================================
# Google credentials & per-user fetch locking
# ===================================================================


def get_google_creds_dict(user: dict[str, Any]) -> dict | None:
    """Return decrypted Google OAuth credentials for *user*.

    Checks the user dict first (populated at OAuth callback) and falls
    back to the encrypted copy in Firestore.
    """
    if not user:
        return None

    creds = user.get("google_credentials")
    if isinstance(creds, dict):
        return creds

    from .firebase_store import get_google_credentials

    return get_google_credentials(user.get("google_id", ""))


_user_fetch_locks: dict[str, threading.Lock] = {}
_user_fetch_locks_guard = threading.Lock()


def _get_user_fetch_lock(google_id: str) -> threading.Lock:
    """Return a per-user lock for serialising portfolio fetches.

    Evicts the oldest half of entries when the dict exceeds
    ``USER_FETCH_LOCKS_MAX`` to bound memory usage.
    """
    with _user_fetch_locks_guard:
        if len(_user_fetch_locks) >= USER_FETCH_LOCKS_MAX:
            keys_to_remove = list(_user_fetch_locks.keys())[: USER_FETCH_LOCKS_MAX // 2]
            for k in keys_to_remove:
                _user_fetch_locks.pop(k, None)
        return _user_fetch_locks.setdefault(google_id, threading.Lock())


# ===================================================================
# Google Sheets batch prefetch
# ===================================================================


def prefetch_all_user_sheets(user, *, track_state: bool = False, ensure_tabs: bool = False):
    """Batch-fetch all sheet tabs in a single Google Sheets API call.

    On a cache miss this acquires the per-user lock, double-checks the
    cache, and issues one ``batchGet`` request for Gold, FixedDeposits,
    Stocks, ETFs, MutualFunds, and SIPs.  The parsed results are stored
    in ``user_sheets_cache`` so that subsequent calls find data already
    cached.

    When *track_state* is True (background fetch), updates
    ``state_manager.sheets_state`` so the frontend can poll for
    completion and render incrementally.

    When *ensure_tabs* is True (manual refresh), verify that every
    expected sheet tab exists and has up-to-date headers.  Skipped on
    automatic fetches to avoid 5-10 extra Google Sheets API calls.
    """
    google_id = user.get("google_id", "")
    spreadsheet_id = user.get("spreadsheet_id")
    creds_dict = get_google_creds_dict(user)
    if not spreadsheet_id or not creds_dict:
        if track_state and google_id:
            state_manager.set_sheets_updated(google_id)
        return

    # Fast path — everything already in cache.
    if user_sheets_cache.is_fully_cached(google_id):
        logger.debug("Sheets cache hit")
        if track_state and google_id:
            state_manager.set_sheets_updated(google_id)
        return

    with _get_user_fetch_lock(google_id):
        # Double-check after acquiring lock.
        if user_sheets_cache.is_fully_cached(google_id):
            return

        _t0 = time.monotonic()
        logger.info("Sheets batch-fetch started")

        try:
            from .api.fixed_deposits import calculate_current_value
            from .api.google_auth import credentials_from_dict
            from .api.google_sheets_client import (
                FixedDepositsService,
                GoogleSheetsClient,
                PhysicalGoldService,
            )
            from .api.user_sheets import SHEET_CONFIGS

            creds = credentials_from_dict(creds_dict)
            client = GoogleSheetsClient(user_credentials=creds)

            if ensure_tabs:
                tabs = [
                    (SHEET_CONFIGS[st]["sheet_name"], SHEET_CONFIGS[st]["headers"])
                    for st in ("stocks", "etfs", "mutual_funds", "sips")
                ]
                client.ensure_sheet_tabs(spreadsheet_id, tabs)

            sheet_names = [
                "Gold",
                "FixedDeposits",
                *(SHEET_CONFIGS[st]["sheet_name"] for st in ("stocks", "etfs", "mutual_funds", "sips")),
            ]

            batch = client.batch_fetch_sheet_data_until_blank(spreadsheet_id, sheet_names)

            gold_svc = PhysicalGoldService(client)
            fd_svc = FixedDepositsService(client)
            gold = gold_svc._parse_batch_data(batch.get("Gold", []))
            deposits = calculate_current_value(fd_svc._parse_batch_data(batch.get("FixedDeposits", [])))

            manual: dict = {}
            for sheet_type in ("stocks", "etfs", "mutual_funds", "sips"):
                cfg = SHEET_CONFIGS[sheet_type]
                raw = batch.get(cfg["sheet_name"], [])
                if not raw or len(raw) < 2:
                    manual[sheet_type] = []
                    continue
                fields = cfg["fields"]
                rows = []
                for idx, row in enumerate(raw[1:], start=2):
                    if is_blank_row(row):
                        break
                    entry = {"row_number": idx}
                    for fi, fname in enumerate(fields):
                        entry[fname] = row[fi] if fi < len(row) else ""
                    # Default empty/missing source to "manual"
                    if not entry.get("source"):
                        entry["source"] = "manual"
                    rows.append(entry)
                manual[sheet_type] = rows

            user_sheets_cache.put_all(
                google_id,
                physical_gold=gold,
                fixed_deposits=deposits,
                manual=manual,
            )
            _elapsed = time.monotonic() - _t0
            logger.info("Sheets batch-fetch done in %.1fs", _elapsed)

            from .api.google_auth import persist_refreshed_credentials

            persist_refreshed_credentials(creds, google_id)

            if track_state:
                state_manager.set_sheets_updated(google_id)
        except Exception as exc:
            _elapsed = time.monotonic() - _t0
            _exc_type = type(exc).__name__
            if "RefreshError" in _exc_type or "InvalidGrantError" in _exc_type:
                logger.warning(
                    "Sheets batch-fetch FAILED after %.1fs: "
                    "Google credentials expired or incomplete (%s). "
                    "User must re-authenticate.",
                    _elapsed,
                    _exc_type,
                )
            else:
                logger.exception("Sheets batch-fetch FAILED after %.1fs", _elapsed)
            if track_state:
                state_manager.set_sheets_updated(google_id, error=str(exc))


def _build_user_dict_for_sheets(google_id: str) -> dict[str, Any] | None:
    """Build a minimal user dict from Firestore for sheets prefetch."""
    from .firebase_store import get_user

    user = get_user(google_id)
    if not user:
        return None
    user.setdefault("google_id", google_id)
    return user


# ===================================================================
# Manual LTP helpers
# ===================================================================


def collect_manual_symbols(google_id: str) -> list:
    """Return deduplicated stock/ETF symbols from the user's manual sheets cache.

    Call *before* ``user_sheets_cache.invalidate()`` so data is still present.
    """
    symbols: set = set()
    for sheet_type in ("stocks", "etfs"):
        for entry in user_sheets_cache.get_manual(google_id, sheet_type) or []:
            sym = (entry.get("symbol") or "").upper()
            if sym:
                symbols.add(sym)
    return list(symbols)


def fetch_manual_ltps(symbols: list, *, force: bool = False) -> None:
    """Fetch LTPs from Yahoo Finance for *symbols* and populate ``manual_ltp_cache``.

    Args:
        symbols: Stock/ETF symbols to look up.
        force:   Re-fetch even if already cached (used during refresh
                 cycles).  Negative-cached symbols are always skipped.
    """
    if not symbols:
        return

    to_fetch = _filter_symbols_to_fetch(symbols, force)
    if not to_fetch:
        logger.debug("Manual LTP: all %d symbols already cached", len(symbols))
        return

    logger.debug("Manual LTP fetch: %d/%d symbols", len(to_fetch), len(symbols))
    fetched = _batch_fetch_quotes(to_fetch)
    _update_ltp_cache(to_fetch, fetched)


def _filter_symbols_to_fetch(symbols: list, force: bool) -> list:
    """Exclude symbols that don't need a Yahoo Finance request."""
    result = []
    for sym in symbols:
        if manual_ltp_cache.is_negative(sym):
            continue
        if force or not manual_ltp_cache.get(sym):
            result.append(sym)
    return result


def _batch_fetch_quotes(symbols: list) -> dict:
    """Fetch quotes via Yahoo Finance for a batch of symbols.

    Returns ``{symbol: quote_dict}``.
    """
    try:
        return MarketDataClient().fetch_stock_quotes(
            symbols,
            cancel=manual_ltp_cache.cancel_flag,
        )
    except Exception:
        logger.exception("Error in batch LTP fetch")
        return {}


def _update_ltp_cache(requested: list, fetched: dict) -> None:
    """Write successful results and negative-cache misses."""
    if fetched:
        manual_ltp_cache.put_batch(fetched)

    missed = [s for s in requested if s not in fetched]
    if missed:
        manual_ltp_cache.put_negative_batch(missed)
        logger.warning("Manual LTP: unresolved %d symbols", len(missed))

    logger.info("Manual LTP fetch done: %d/%d successful", len(fetched), len(requested))


# ===================================================================
# Non-blocking LTP fetch (background thread)
# ===================================================================


def _bg_fetch_and_broadcast_ltps(
    google_id: str,
    symbols: list | None,
    force: bool,
) -> None:
    """Background thread: fetch LTPs then update state.

    If *symbols* is empty (first load, cold cache), polls until the sheets
    cache is populated by the concurrent ``/api/all_data`` request.
    """
    try:
        syms = symbols or _wait_for_symbols(google_id)

        if not syms:
            logger.info("Manual LTP: no symbols to fetch")
            return

        state_manager.set_manual_ltp_updating(google_id)
        fetch_manual_ltps(syms, force=force)
        logger.debug("Manual LTP fetch complete")
    except Exception:
        logger.exception("Error in LTP fetch")
    finally:
        state_manager.set_manual_ltp_updated(google_id)


def _wait_for_symbols(google_id: str) -> list:
    """Poll sheets cache until manual symbols appear (or timeout)."""
    for attempt in range(1, LTP_CACHE_WARMUP_ATTEMPTS + 1):
        syms = collect_manual_symbols(google_id)
        if syms:
            logger.debug("Manual LTP: found %d symbols after %d polls", len(syms), attempt)
            return syms
        time.sleep(LTP_CACHE_WARMUP_INTERVAL)
    return []


def _start_ltp_fetch_thread(google_id: str, symbols: list | None, force: bool, prefix: str = "ManualLTP") -> None:
    """Fire a non-blocking background LTP fetch thread."""
    threading.Thread(
        target=_bg_fetch_and_broadcast_ltps,
        args=(google_id, symbols, force),
        name=f"{prefix}-{google_id[:8]}",
        daemon=True,
    ).start()


# ===================================================================
# Portfolio data fetching (per-user)
# ===================================================================


def fetch_portfolio_data(google_id: str, accounts: list | None = None) -> None:
    """Fetch holdings and SIPs for *google_id*'s authenticated Zerodha accounts."""
    if accounts is None:
        accounts = get_authenticated_accounts(google_id)
    if not accounts:
        logger.info("No authenticated Zerodha accounts")
        return

    accounts = [{**acc, "google_id": google_id} for acc in accounts]
    portfolio_cache.set_fetch_in_progress(google_id)
    state_manager.set_portfolio_updating(google_id=google_id)
    error = None

    try:
        stocks, mfs, sips, error = zerodha_client.fetch_all_accounts_data(accounts)
        if not error:
            synced_accounts = {acc.get("name", "") for acc in accounts}

            from .broker_sync import is_etf_holding

            pure_stocks = [s for s in stocks if not is_etf_holding(s)]
            etfs = [s for s in stocks if is_etf_holding(s)]

            portfolio_cache.set(
                google_id,
                stocks=pure_stocks,
                etfs=etfs,
                mf_holdings=mfs,
                sips=sips,
                connected_accounts=synced_accounts,
            )
            logger.info("Portfolio updated in fetch")

            # Async sync broker data to Google Sheets (fire and forget)
            from .broker_sync import start_broker_sync_thread

            start_broker_sync_thread(google_id, pure_stocks, etfs, mfs, sips, synced_accounts)
        else:
            portfolio_cache.set(google_id, connected_accounts=set())
            logger.info("Broker fetch failed, will use sheet data as fallback")
    except Exception as e:
        logger.exception("Error fetching portfolio: %s", e)
        portfolio_cache.set(google_id, connected_accounts=set())
        error = str(e)
    finally:
        state_manager.set_portfolio_updated(google_id=google_id, error=error)
        portfolio_cache.clear_fetch_in_progress(google_id)


# ===================================================================
# Market data fetching (global)
# ===================================================================


def _should_fetch_gold_prices() -> bool:
    """Return True if gold prices should be re-fetched (stale or new day/hour)."""
    if market_cache.gold_prices_last_fetch is None:
        return True
    now = datetime.now()
    last = market_cache.gold_prices_last_fetch
    if now.date() != last.date():
        return True
    return now.hour in GOLD_PRICE_FETCH_HOURS and last.hour != now.hour


def fetch_gold_prices(force: bool = False) -> None:
    """Fetch IBJA gold prices (global, retries up to 3 times)."""
    if not force and not _should_fetch_gold_prices():
        return
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            prices = get_gold_price_service().fetch_gold_prices()
            if prices:
                market_cache.gold_prices = prices
                market_cache.gold_prices_last_fetch = datetime.now()
                logger.info("Gold prices updated: %s", list(prices.keys()))
                return
            logger.warning("Attempt %d: empty gold prices", attempt)
        except Exception as e:
            logger.error("Attempt %d: gold price error: %s", attempt, e)
        if attempt < max_retries:
            logger.info("Retrying gold price fetch (%d/%d)...", attempt + 1, max_retries)
    logger.error("All %d gold price fetch attempts failed", max_retries)


def fetch_market_indices_data(*, force: bool = False) -> None:
    """Fetch market indices (Nifty50, Sensex, S&P500, Gold, Silver, USDINR).

    Stores the result in ``market_cache.market_indices`` so the
    ``/api/market_indices`` endpoint can serve it from cache.
    """
    if not force and isinstance(market_cache.market_indices_last_fetch, datetime):
        age = (datetime.now() - market_cache.market_indices_last_fetch).total_seconds()
        if age < MARKET_DATA_MIN_INTERVAL:
            logger.debug("Market indices fresh (%.0fs old), skipping", age)
            return
    try:
        client = MarketDataClient()
        data = client.fetch_market_indices()
        market_cache.market_indices = data
        market_cache.market_indices_last_fetch = datetime.now()
    except Exception as e:
        logger.error("Error fetching market indices: %s", e)


def fetch_nifty50_data(*, force: bool = False) -> None:
    """Fetch Nifty 50 constituent stocks via Yahoo Finance (non-blocking).

    The Nifty 50 symbol list is still fetched from NSE (with a hardcoded
    fallback).  Individual stock quotes are fetched concurrently from
    Yahoo Finance.
    """
    if nifty50_fetch_in_progress.is_set():
        logger.info("Nifty 50 fetch already in progress")
        return

    if not force and isinstance(market_cache.nifty50_last_fetch, datetime):
        age = (datetime.now() - market_cache.nifty50_last_fetch).total_seconds()
        if age < MARKET_DATA_MIN_INTERVAL:
            logger.debug("Nifty50 data fresh (%.0fs old), skipping", age)
            return

    state_manager.set_nifty50_updating()

    def _fetch():
        error = None
        try:
            nifty50_fetch_in_progress.set()
            client = MarketDataClient()
            symbols = client.fetch_nifty50_symbols() or NIFTY50_FALLBACK_SYMBOLS
            quotes = client.fetch_stock_quotes(symbols)
            # Preserve symbol order; include empty data for missed symbols
            market_cache.nifty50 = [quotes.get(s, client._empty_stock_data(s)) for s in symbols]
            market_cache.nifty50_last_fetch = datetime.now()
            logger.info("Nifty 50 updated: %d stocks (%d with LTP)", len(market_cache.nifty50), len(quotes))
        except Timeout:
            error = "Yahoo Finance timeout"
            logger.warning(error)
        except ConnectionError:
            error = "Connection error"
            logger.warning("Cannot connect to Yahoo Finance")
        except Exception as e:
            error = str(e)
            logger.error("Error fetching Nifty 50: %s", e)
        finally:
            state_manager.set_nifty50_updated(error=error)
            nifty50_fetch_in_progress.clear()

    threading.Thread(target=_fetch, daemon=True).start()


# ===================================================================
# Orchestration
# ===================================================================


def run_background_fetch(
    on_complete: Callable | None = None,
    is_manual: bool = False,
    accounts: list | None = None,
    google_id: str | None = None,
    manual_symbols: list | None = None,
) -> None:
    """Fire independent background threads for each data source.

    Each source (broker, sheets, nifty, gold) runs in its own thread
    and updates state independently.  The frontend polls ``/api/status``
    and renders incrementally as each source completes.
    """
    logger.info("background_fetch start: manual=%s", is_manual)

    force_gold = is_manual or (market_cache.gold_prices_last_fetch is None)

    # --- Portfolio (Zerodha) ---
    if google_id:
        auth_accs = accounts if accounts is not None else get_authenticated_accounts(google_id)
        if auth_accs:
            threading.Thread(
                target=fetch_portfolio_data,
                args=(google_id, auth_accs),
                name=f"PortfolioFetch-{google_id[:8]}",
                daemon=True,
            ).start()
        else:
            logger.info("background_fetch: no auth accounts, skipping portfolio")
            state_manager.set_portfolio_updating(google_id=google_id)
            portfolio_cache.clear(google_id)
            state_manager.set_portfolio_updated(google_id=google_id)

    # --- Google Sheets ---
    if google_id:
        # Skip the Firestore round-trip when sheets are already cached.
        if not is_manual and user_sheets_cache.is_fully_cached(google_id):
            user_dict = None
            logger.debug("Sheets cache warm — skipping sheets fetch")
            state_manager.set_sheets_updated(google_id)
            # LTPs are also cached; mark done.
            state_manager.set_manual_ltp_updated(google_id)
            if on_complete:
                on_complete()
        else:
            user_dict = _build_user_dict_for_sheets(google_id)
        if user_dict:
            state_manager.set_sheets_updating(google_id)

            def _sheets_then_ltps():
                """Fetch sheets, then kick off manual LTP fetch."""
                prefetch_all_user_sheets(user_dict, track_state=True, ensure_tabs=is_manual)
                # Manual LTP fetch needs symbols from sheets cache.
                state_manager.set_manual_ltp_updating(google_id)
                _start_ltp_fetch_thread(google_id, manual_symbols, is_manual)
                if on_complete:
                    on_complete()

            threading.Thread(
                target=_sheets_then_ltps,
                name=f"SheetsPrefetch-{google_id[:8]}",
                daemon=True,
            ).start()
        else:
            # No sheets linked — mark done immediately.
            state_manager.set_sheets_updated(google_id)
            if on_complete:
                on_complete()

    # --- Global market data ---
    threading.Thread(
        target=fetch_nifty50_data,
        kwargs={"force": is_manual},
        name="Nifty50Fetch",
        daemon=True,
    ).start()
    threading.Thread(
        target=fetch_gold_prices,
        args=(force_gold,),
        name="GoldPriceFetch",
        daemon=True,
    ).start()
    threading.Thread(
        target=fetch_market_indices_data,
        kwargs={"force": is_manual},
        name="MarketIndicesFetch",
        daemon=True,
    ).start()
