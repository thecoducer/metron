"""Background data fetching (on-demand).

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
from .constants import GOLD_PRICE_FETCH_HOURS, NIFTY50_FALLBACK_SYMBOLS
from .logging_config import logger
from .services import (state_manager, zerodha_client, session_manager,
                       get_user_accounts, get_authenticated_accounts)

_LTP_CACHE_WARMUP_INTERVAL = 2   # seconds between polls
_LTP_CACHE_WARMUP_ATTEMPTS = 6   # max polls (~12 s total)


# ===================================================================
# Manual LTP helpers
# ===================================================================

def collect_manual_symbols(google_id: str) -> list:
    """Return deduplicated stock/ETF symbols from the user's manual sheets cache.

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
            symbols, cancel=manual_ltp_cache.cancel_flag,
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
    """Background thread: fetch LTPs then update state.

    If *symbols* is empty (first load, cold cache), polls until the sheets
    cache is populated by the concurrent ``/api/all_data`` request.
    """
    try:
        syms = symbols or _wait_for_symbols(google_id)

        if not syms:
            logger.info("Manual LTP: no symbols for %s", google_id[:8])
            return

        fetch_manual_ltps(syms, force=force)
        state_manager.set_portfolio_updated(google_id=google_id)
        logger.debug("Manual LTP fetch complete for %s", google_id[:8])
    except Exception:
        logger.exception("Error in LTP fetch for %s", google_id[:8])


def _wait_for_symbols(google_id: str) -> list:
    """Poll sheets cache until manual symbols appear (or timeout)."""
    for attempt in range(1, _LTP_CACHE_WARMUP_ATTEMPTS + 1):
        syms = collect_manual_symbols(google_id)
        if syms:
            logger.debug("Manual LTP: found %d symbols after %d polls", len(syms), attempt)
            return syms
        time.sleep(_LTP_CACHE_WARMUP_INTERVAL)
    return []


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
        logger.info("No authenticated Zerodha accounts for %s", google_id[:8])
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
                        google_id[:8], len(stocks), len(mfs), len(sips))
        else:
            data = portfolio_cache.get(google_id)
            logger.info("Preserved %d stocks, %d MFs, %d SIPs for %s after partial failure",
                        len(data.stocks), len(data.mf_holdings), len(data.sips), google_id[:8])
    except Exception as e:
        logger.exception("Error fetching portfolio for %s: %s", google_id[:8], e)
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
    """Fetch Nifty 50 constituent stocks via Yahoo Finance (non-blocking).

    The Nifty 50 symbol list is still fetched from NSE (with a hardcoded
    fallback).  Individual stock quotes are fetched concurrently from
    Yahoo Finance.
    """
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
            quotes = client.fetch_stock_quotes(symbols)
            # Preserve symbol order; include empty data for missed symbols
            market_cache.nifty50 = [
                quotes.get(s, client._empty_stock_data(s)) for s in symbols
            ]
            logger.info("Nifty 50 updated: %d stocks (%d with LTP)",
                        len(market_cache.nifty50), len(quotes))
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
        t0 = time.monotonic()
        logger.info(
            "background_fetch start: user=%s manual=%s accounts=%d",
            (google_id or "")[:8], is_manual,
            len(accounts) if accounts else 0,
        )
        _fetch_all_data(google_id, accounts, is_manual)
        logger.info(
            "background_fetch done: user=%s in %.2fs",
            (google_id or "")[:8], time.monotonic() - t0,
        )

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
            logger.info("_fetch_all_data: no auth accounts for user=%s, skipping portfolio", google_id[:8])
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

