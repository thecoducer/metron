"""Background data fetching and auto-refresh scheduling.

Portfolio fetching is per-user; market data (Nifty 50, gold) is global.
Manual stock/ETF LTP fetching is per-user and non-blocking.
"""

import threading
import time
from datetime import datetime
from typing import Optional

from requests.exceptions import ConnectionError, Timeout

from .api import MarketDataClient
from .api.ibja_gold_price import get_gold_price_service
from .cache import (market_cache, manual_ltp_cache, nifty50_fetch_in_progress,
                    portfolio_cache, user_sheets_cache)
from .config import app_config
from .constants import GOLD_PRICE_FETCH_HOURS, NIFTY50_FALLBACK_SYMBOLS
from .logging_config import logger
from .services import (state_manager, zerodha_client, session_manager,
                       get_user_accounts, get_authenticated_accounts,
                       broadcast_state_change)
from .sse import sse_manager
from .utils import is_market_open_ist


# ---------------------------------------------------------------------------
# Manual LTP retry queue
# ---------------------------------------------------------------------------
# Users whose initial LTP fetch couldn't resolve symbols (cold sheets cache).
# Retried on the next auto-refresh cycle regardless of market hours.
_pending_ltp_retries: set = set()
_pending_ltp_lock = threading.Lock()

_LTP_CACHE_WARMUP_INTERVAL = 2   # seconds between polls
_LTP_CACHE_WARMUP_ATTEMPTS = 6   # max polls (~12 s total)


# ===================================================================
# Manual LTP helpers
# ===================================================================

def collect_manual_symbols(google_id: str) -> list:
    """Return deduplicated NSE symbols from the user's manual sheets cache.

    Call *before* ``user_sheets_cache.invalidate()`` so data is still present.
    """
    symbols: set = set()
    for sheet_type in ("stocks", "etfs"):
        for entry in (user_sheets_cache.get_manual(google_id, sheet_type) or []):
            sym = (entry.get("symbol") or "").upper()
            if sym:
                symbols.add(sym)
    return list(symbols)


def fetch_manual_ltps(symbols: list, *, force: bool = False) -> None:
    """Fetch LTPs from NSE for *symbols* and populate ``manual_ltp_cache``.

    Args:
        symbols: NSE symbols to look up.
        force:   Re-fetch even if already cached (used during refresh
                 cycles).  Negative-cached symbols are always skipped.
    """
    if not symbols:
        return

    to_fetch = _filter_symbols_to_fetch(symbols, force)
    if not to_fetch:
        logger.info("Manual LTP: all %d symbols already cached", len(symbols))
        return

    logger.info("Manual LTP fetch: %d/%d symbols", len(to_fetch), len(symbols))
    fetched = _nse_batch_fetch(to_fetch)
    _update_ltp_cache(to_fetch, fetched)


def _filter_symbols_to_fetch(symbols: list, force: bool) -> list:
    """Exclude symbols that don't need an NSE request."""
    result = []
    for sym in symbols:
        if manual_ltp_cache.is_negative(sym):
            continue
        if force or not manual_ltp_cache.get(sym):
            result.append(sym)
    return result


def _nse_batch_fetch(symbols: list) -> dict:
    """Call NSE for a batch of symbols. Returns ``{symbol: quote_dict}``."""
    try:
        return MarketDataClient().fetch_stock_quotes(
            symbols, cancel=manual_ltp_cache.cancel_flag,
        )
    except Exception:
        logger.exception("Error in manual LTP fetch")
        return {}


def _update_ltp_cache(requested: list, fetched: dict) -> None:
    """Write successful results and negative-cache misses."""
    if fetched:
        manual_ltp_cache.put_batch(fetched)

    missed = [s for s in requested if s not in fetched]
    if missed:
        manual_ltp_cache.put_negative_batch(missed)
        logger.warning("Manual LTP: %d symbols unresolved: %s", len(missed), missed)

    logger.info("Manual LTP fetch done: %d/%d successful",
                len(fetched), len(requested))


# ===================================================================
# Non-blocking LTP fetch + SSE broadcast
# ===================================================================

def _bg_fetch_and_broadcast_ltps(
    google_id: str,
    symbols: list | None,
    force: bool,
) -> None:
    """Background thread: fetch LTPs then push an SSE update.

    If *symbols* is empty (first load, cold cache), polls until the sheets
    cache is populated by the concurrent ``/api/all_data`` request.
    Falls back to the retry queue on failure.
    """
    try:
        syms = symbols or _wait_for_symbols(google_id)

        if not syms:
            logger.info("Manual LTP: no symbols for %s, queuing retry", google_id[:8])
            with _pending_ltp_lock:
                _pending_ltp_retries.add(google_id)
            return

        with _pending_ltp_lock:
            _pending_ltp_retries.discard(google_id)

        fetch_manual_ltps(syms, force=force)
        state_manager.set_portfolio_updated(google_id=google_id)
        logger.info("Manual LTP SSE broadcast fired for %s", google_id[:8])
    except Exception:
        logger.exception("Error in LTP fetch+broadcast for %s", google_id[:8])


def _wait_for_symbols(google_id: str) -> list:
    """Poll sheets cache until manual symbols appear (or timeout)."""
    for attempt in range(1, _LTP_CACHE_WARMUP_ATTEMPTS + 1):
        syms = collect_manual_symbols(google_id)
        if syms:
            logger.info("Manual LTP: found %d symbols after %d polls", len(syms), attempt)
            return syms
        time.sleep(_LTP_CACHE_WARMUP_INTERVAL)
    return []


def _process_pending_ltp_retries() -> None:
    """Retry LTP fetches for users that failed on first load."""
    with _pending_ltp_lock:
        pending = set(_pending_ltp_retries)

    connected = sse_manager.connected_user_ids()
    for gid in pending:
        if gid not in connected:
            with _pending_ltp_lock:
                _pending_ltp_retries.discard(gid)
            continue

        syms = collect_manual_symbols(gid)
        if not syms:
            continue

        logger.info("Manual LTP retry for %s: %d symbols", gid[:8], len(syms))
        with _pending_ltp_lock:
            _pending_ltp_retries.discard(gid)
        threading.Thread(
            target=_bg_fetch_and_broadcast_ltps,
            args=(gid, syms, False),
            name=f"RetryLTP-{gid[:8]}",
            daemon=True,
        ).start()


def _start_ltp_fetch_thread(google_id: str, symbols: list | None,
                            force: bool, prefix: str = "ManualLTP") -> None:
    """Fire a non-blocking LTP fetch + SSE broadcast thread."""
    threading.Thread(
        target=_bg_fetch_and_broadcast_ltps,
        args=(google_id, symbols, force),
        name=f"{prefix}-{google_id[:8]}",
        daemon=True,
    ).start()


# ===================================================================
# Portfolio data fetching (per-user)
# ===================================================================

def fetch_portfolio_data(google_id: str, accounts: Optional[list] = None) -> None:
    """Fetch holdings and SIPs for *google_id*'s authenticated Zerodha accounts."""
    if accounts is None:
        accounts = get_authenticated_accounts(google_id)
    if not accounts:
        logger.info("No authenticated Zerodha accounts for %s", google_id)
        return

    accounts = [{**acc, "google_id": google_id} for acc in accounts]
    portfolio_cache.set_fetch_in_progress(google_id)
    state_manager.set_portfolio_updating(google_id=google_id)
    error = None

    try:
        stocks, mfs, sips, error = zerodha_client.fetch_all_accounts_data(accounts)
        if not error:
            portfolio_cache.set(google_id, stocks=stocks, mf_holdings=mfs, sips=sips)
            logger.info("Portfolio updated for %s: %d stocks, %d MFs, %d SIPs",
                        google_id, len(stocks), len(mfs), len(sips))
        else:
            data = portfolio_cache.get(google_id)
            logger.info("Preserved %d stocks, %d MFs, %d SIPs for %s after partial failure",
                        len(data.stocks), len(data.mf_holdings), len(data.sips), google_id)
    except Exception as e:
        logger.exception("Error fetching portfolio for %s: %s", google_id, e)
        error = str(e)
    finally:
        state_manager.set_portfolio_updated(google_id=google_id, error=error)
        portfolio_cache.clear_fetch_in_progress(google_id)


# ===================================================================
# Market data fetching (global)
# ===================================================================

def _should_fetch_gold_prices() -> bool:
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


def fetch_nifty50_data() -> None:
    """Fetch Nifty 50 constituent stocks from NSE (non-blocking)."""
    if nifty50_fetch_in_progress.is_set():
        logger.info("Nifty 50 fetch already in progress")
        return

    state_manager.set_nifty50_updating()

    def _fetch():
        error = None
        try:
            nifty50_fetch_in_progress.set()
            client = MarketDataClient()
            symbols = client.fetch_nifty50_symbols() or NIFTY50_FALLBACK_SYMBOLS
            session = client._create_session()
            market_cache.nifty50 = [client.fetch_stock_quote(session, s) for s in symbols]
            logger.info("Nifty 50 updated: %d stocks", len(market_cache.nifty50))
        except Timeout:
            error = "NSE website timeout"
            logger.warning(error)
        except ConnectionError:
            error = "Connection error"
            logger.warning("Cannot connect to NSE")
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
    on_complete: Optional[callable] = None,
    is_manual: bool = False,
    accounts: Optional[list] = None,
    google_id: Optional[str] = None,
    manual_symbols: Optional[list] = None,
) -> None:
    """Kick off concurrent portfolio + market data fetch in a background thread.

    After all fetches complete, fires a non-blocking manual LTP fetch
    that will SSE-broadcast when done.
    """
    def _run():
        _fetch_all_data(google_id, accounts, is_manual)

        # Non-blocking: fetch manual LTPs and broadcast via SSE when ready.
        if google_id:
            _start_ltp_fetch_thread(google_id, manual_symbols, is_manual)

        if on_complete:
            on_complete()

    threading.Thread(target=_run, daemon=True).start()


def _fetch_all_data(google_id: Optional[str], accounts: Optional[list],
                    is_manual: bool) -> None:
    """Fetch portfolio, Nifty 50, and gold in parallel. Blocks until done."""
    force_gold = is_manual or (market_cache.gold_prices_last_fetch is None)
    threads = []
    has_portfolio = False

    if google_id:
        auth_accs = accounts if accounts is not None else get_authenticated_accounts(google_id)
        if auth_accs:
            has_portfolio = True
            threads.append(threading.Thread(
                target=fetch_portfolio_data, args=(google_id, auth_accs),
                name=f"PortfolioFetch-{google_id[:8]}", daemon=True))
        else:
            state_manager.set_portfolio_updating(google_id=google_id)

    threads.append(threading.Thread(
        target=fetch_nifty50_data, name="Nifty50Fetch", daemon=True))
    threads.append(threading.Thread(
        target=fetch_gold_prices, args=(force_gold,),
        name="GoldPriceFetch", daemon=True))

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    if google_id and not has_portfolio:
        portfolio_cache.clear(google_id)
        state_manager.set_portfolio_updated(google_id=google_id)


# ===================================================================
# Auto-refresh loop
# ===================================================================

def _should_auto_refresh() -> tuple[bool, Optional[str]]:
    if not is_market_open_ist() and not app_config.auto_refresh_outside_market_hours:
        return False, "market closed"
    if not sse_manager.connected_user_ids():
        return False, "no active SSE connections"
    return True, None


def run_auto_refresh() -> None:
    """Periodically refresh data for all connected users.

    Runs in its own thread (started at server boot). Each cycle:
    1. Broadcasts market open/close transitions
    2. Processes pending LTP retries (any market state)
    3. Fetches Nifty 50 + gold (global)
    4. Fetches portfolio per user (concurrent)
    5. Fires non-blocking per-user manual LTP fetch + SSE broadcast
    """
    last_market_open: Optional[bool] = None

    while True:
        time.sleep(app_config.auto_refresh_interval)

        # 1. Broadcast market state transitions
        current_market_open = is_market_open_ist()
        if last_market_open is not None and current_market_open != last_market_open:
            logger.info("Market state changed: %s → %s",
                        "open" if last_market_open else "closed",
                        "open" if current_market_open else "closed")
            broadcast_state_change()
        last_market_open = current_market_open

        # 2. Retry failed LTP fetches (runs regardless of market hours)
        _process_pending_ltp_retries()

        # 3. Check if full refresh should run
        should_run, reason = _should_auto_refresh()
        if not should_run:
            logger.info("Auto-refresh skipped: %s", reason)
            continue

        logger.info("Auto-refresh at %s (%s)",
                    datetime.now().strftime('%H:%M:%S'),
                    "market open" if current_market_open else "outside hours")

        # 4. Global market data
        fetch_nifty50_data()
        fetch_gold_prices()

        # 5. Per-user: collect symbols → invalidate → fetch portfolio → LTP
        connected = list(sse_manager.connected_user_ids())

        # Collect symbols BEFORE invalidation (cache will be cleared)
        per_user_symbols = {
            gid: syms
            for gid in connected
            if (syms := collect_manual_symbols(gid))
        }

        user_threads = []
        for gid in connected:
            user_sheets_cache.invalidate(gid)

            if not portfolio_cache.is_fetch_in_progress(gid):
                auth = get_authenticated_accounts(gid)
                if auth:
                    t = threading.Thread(
                        target=fetch_portfolio_data, args=(gid, auth),
                        name=f"AutoRefresh-{gid[:8]}", daemon=True)
                    user_threads.append(t)
                    t.start()
                else:
                    state_manager.set_portfolio_updating(google_id=gid)
                    state_manager.set_portfolio_updated(google_id=gid)

        for t in user_threads:
            t.join()

        # 6. Non-blocking LTP fetch per user
        for gid in connected:
            syms = per_user_symbols.get(gid)
            if syms:
                _start_ltp_fetch_thread(gid, syms, force=True, prefix="AutoLTP")

