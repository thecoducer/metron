"""Background data fetching and auto-refresh scheduling.

Portfolio fetching is per-user; market data (Nifty 50, gold) is global.
"""

import threading
import time
from datetime import datetime
from typing import Optional

from requests.exceptions import ConnectionError, Timeout

from .api import MarketDataClient
from .api.ibja_gold_price import get_gold_price_service
from .cache import market_cache, nifty50_fetch_in_progress, portfolio_cache
from .config import app_config
from .constants import GOLD_PRICE_FETCH_HOURS, NIFTY50_FALLBACK_SYMBOLS
from .logging_config import logger
from .services import (state_manager, zerodha_client, session_manager,
                       get_user_accounts, get_authenticated_accounts)
from .sse import sse_manager
from .utils import is_market_open_ist


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


def _should_fetch_gold_prices() -> bool:
    if market_cache.gold_prices_last_fetch is None:
        return True
    now = datetime.now()
    last = market_cache.gold_prices_last_fetch
    if now.date() != last.date():
        return True
    return now.hour in GOLD_PRICE_FETCH_HOURS and last.hour != now.hour


def fetch_gold_prices(force: bool = False) -> None:
    """Fetch IBJA gold prices (global)."""
    if not force and not _should_fetch_gold_prices():
        return
    try:
        prices = get_gold_price_service().fetch_gold_prices()
        if prices:
            market_cache.gold_prices = prices
            market_cache.gold_prices_last_fetch = datetime.now()
            logger.info("Gold prices updated: %s", list(prices.keys()))
        else:
            logger.warning("Failed to fetch gold prices")
    except Exception as e:
        logger.error("Error fetching gold prices: %s", e)


def fetch_nifty50_data() -> None:
    """Fetch Nifty 50 constituent stocks from NSE."""
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


def run_background_fetch(
    on_complete: Optional[callable] = None,
    is_manual: bool = False,
    accounts: Optional[list] = None,
    google_id: Optional[str] = None,
) -> None:
    """Orchestrate concurrent portfolio + market data fetch."""
    def _run():
        force_gold = is_manual or (market_cache.gold_prices_last_fetch is None)
        threads = []

        if google_id:
            auth_accs = accounts if accounts is not None else get_authenticated_accounts(google_id)
            if auth_accs:
                threads.append(threading.Thread(
                    target=fetch_portfolio_data, args=(google_id, auth_accs),
                    name=f"PortfolioFetch-{google_id[:8]}", daemon=True))

        threads.append(threading.Thread(target=fetch_nifty50_data, name="Nifty50Fetch", daemon=True))
        threads.append(threading.Thread(target=fetch_gold_prices, args=(force_gold,),
                                        name="GoldPriceFetch", daemon=True))
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        if on_complete:
            on_complete()

    threading.Thread(target=_run, daemon=True).start()


def _should_auto_refresh() -> tuple[bool, Optional[str]]:
    if not is_market_open_ist() and not app_config.auto_refresh_outside_market_hours:
        return False, "market closed"
    if not sse_manager.connected_user_ids():
        return False, "no active SSE connections"
    return True, None


def run_auto_refresh() -> None:
    """Periodically refresh data for all users with active SSE connections."""
    while True:
        time.sleep(app_config.auto_refresh_interval)
        should_run, reason = _should_auto_refresh()
        if not should_run:
            logger.info("Auto-refresh skipped: %s", reason)
            continue

        logger.info("Auto-refresh at %s (%s)",
                    datetime.now().strftime('%H:%M:%S'),
                    "market open" if is_market_open_ist() else "outside hours")

        fetch_nifty50_data()
        fetch_gold_prices()

        for gid in sse_manager.connected_user_ids():
            if not portfolio_cache.is_fetch_in_progress(gid):
                authenticated = get_authenticated_accounts(gid)
                if authenticated:
                    fetch_portfolio_data(gid, authenticated)

