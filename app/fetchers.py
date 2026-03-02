"""
Data fetching functions and auto-refresh scheduling.

Contains all background data-fetching logic for portfolio, Nifty 50,
and gold prices, plus the auto-refresh scheduler.
"""

import threading
import time
from datetime import datetime
from typing import Optional

from requests.exceptions import ConnectionError, Timeout

from .api import MarketDataClient
from .api.ibja_gold_price import get_gold_price_service
from .cache import cache, fetch_in_progress, nifty50_fetch_in_progress
from .config import app_config
from .constants import GOLD_PRICE_FETCH_HOURS, NIFTY50_FALLBACK_SYMBOLS
from .logging_config import logger
from .services import state_manager, zerodha_client, session_manager, get_active_accounts, get_authenticated_accounts
from .utils import is_market_open_ist

# --------------------------
# PORTFOLIO DATA
# --------------------------

def fetch_portfolio_data(accounts: Optional[list] = None) -> None:
    """Fetch holdings and SIPs for authenticated Zerodha accounts.

    Args:
        accounts: List of account config dicts (pre-filtered as authenticated).
                  If None, resolves authenticated accounts from Firebase.
    """
    if accounts is None:
        accounts = get_authenticated_accounts()

    if not accounts:
        logger.info("No authenticated Zerodha accounts \u2013 skipping portfolio fetch")
        return

    fetch_in_progress.set()
    state_manager.set_portfolio_updating()
    error_occurred = None

    try:
        merged_stocks, merged_mfs, merged_sips, error_occurred = \
            zerodha_client.fetch_all_accounts_data(accounts)

        if not error_occurred:
            cache.stocks = merged_stocks
            cache.mf_holdings = merged_mfs
            cache.sips = merged_sips
            logger.info(
                "Portfolio data updated: %d stocks, %d MFs, %d SIPs",
                len(merged_stocks), len(merged_mfs), len(merged_sips),
            )
        else:
            logger.info(
                "Preserved %d existing stocks, %d MFs, %d SIPs after partial fetch failure",
                len(cache.stocks), len(cache.mf_holdings), len(cache.sips),
            )
    except Exception as e:
        logger.exception("Error fetching portfolio data: %s", e)
        error_occurred = str(e)
    finally:
        state_manager.set_portfolio_updated(error=error_occurred)
        fetch_in_progress.clear()


# --------------------------
# GOLD PRICES (IBJA)
# --------------------------

def _should_fetch_gold_prices() -> bool:
    """Check if gold prices should be fetched based on schedule."""
    if cache.gold_prices_last_fetch is None:
        return True

    now = datetime.now()
    today = now.date()
    last_fetch_date = cache.gold_prices_last_fetch.date()

    if today != last_fetch_date:
        return True

    current_hour = now.hour
    last_fetch_hour = cache.gold_prices_last_fetch.hour

    if current_hour in GOLD_PRICE_FETCH_HOURS and last_fetch_hour != current_hour:
        return True

    return False


def fetch_gold_prices(force: bool = False) -> None:
    """Fetch latest IBJA gold prices.

    Args:
        force: If True, bypass schedule and fetch immediately.
    """
    if not force and not _should_fetch_gold_prices():
        scheduled_times = ", ".join([f"{h}:00" for h in GOLD_PRICE_FETCH_HOURS])
        logger.info(
            "Skipping gold price fetch – using cached prices (next scheduled: %s IST)",
            scheduled_times,
        )
        return

    try:
        gold_service = get_gold_price_service()
        gold_prices = gold_service.fetch_gold_prices()
        if gold_prices:
            cache.gold_prices = gold_prices
            cache.gold_prices_last_fetch = datetime.now()
            logger.info("Gold prices updated: %s", list(gold_prices.keys()))
        else:
            logger.warning("Failed to fetch gold prices – keeping cached prices if available")
    except Exception as e:
        logger.error("Error fetching gold prices: %s – keeping cached prices", e)


# --------------------------
# NIFTY 50
# --------------------------

def fetch_nifty50_data() -> None:
    """Fetch Nifty 50 index constituent stocks data from NSE API.

    Runs asynchronously in a background thread.
    """
    if nifty50_fetch_in_progress.is_set():
        logger.info("Nifty 50 fetch already in progress, skipping")
        return

    state_manager.set_nifty50_updating()

    def _fetch_task():
        error_occurred = None
        try:
            nifty50_fetch_in_progress.set()
            logger.info("Fetching Nifty 50 data...")

            market_client = MarketDataClient()

            symbols = market_client.fetch_nifty50_symbols()
            if not symbols:
                logger.warning("Failed to fetch symbols from NSE, using fallback list")
                symbols = NIFTY50_FALLBACK_SYMBOLS

            try:
                session = market_client._create_session()
            except (Timeout, ConnectionError) as e:
                logger.error("Failed to create NSE session: %s", e)
                raise

            nifty50_data = [
                market_client.fetch_stock_quote(session, symbol)
                for symbol in symbols
            ]

            cache.nifty50 = nifty50_data

            logger.info("Nifty 50 data updated: %d stocks", len(cache.nifty50))
        except Timeout:
            logger.warning("NSE website timeout - Nifty 50 data not updated (server slow)")
            error_occurred = "NSE website timeout"
        except ConnectionError:
            logger.warning("Cannot connect to NSE website - Nifty 50 data not updated")
            error_occurred = "Connection error"
        except Exception as e:
            logger.error("Error fetching Nifty 50 data: %s", str(e))
            error_occurred = str(e)
        finally:
            state_manager.set_nifty50_updated(error=error_occurred)
            nifty50_fetch_in_progress.clear()

    threading.Thread(target=_fetch_task, daemon=True).start()


# --------------------------
# ORCHESTRATION
# --------------------------

def run_background_fetch(
    on_complete: Optional[callable] = None,
    is_manual: bool = False,
    accounts: Optional[list] = None,
) -> None:
    """Orchestrate concurrent fetching of portfolio and market data.

    Launches parallel background tasks:
    1. Portfolio data (only for authenticated accounts).
    2. Nifty 50 market data from NSE.
    3. Gold prices from IBJA.

    Args:
        on_complete: Optional callback to execute after all tasks complete.
        is_manual: If True, this is a manual refresh (always fetch gold prices).
        accounts: Pre-filtered authenticated Zerodha accounts. Resolved from
                  Firebase if None.
    """
    def _orchestrate_fetch():
        force_gold = is_manual or (cache.gold_prices_last_fetch is None)

        authenticated = accounts if accounts is not None else get_authenticated_accounts()

        threads = []

        if authenticated:
            portfolio_thread = threading.Thread(
                target=fetch_portfolio_data,
                args=(authenticated,),
                name="PortfolioFetch",
                daemon=True,
            )
            threads.append(portfolio_thread)
        else:
            logger.info("No authenticated Zerodha accounts \u2013 skipping portfolio fetch")

        nifty50_thread = threading.Thread(
            target=fetch_nifty50_data,
            name="Nifty50Fetch",
            daemon=True,
        )
        gold_prices_thread = threading.Thread(
            target=fetch_gold_prices,
            args=(force_gold,),
            name="GoldPriceFetch",
            daemon=True,
        )
        threads.extend([nifty50_thread, gold_prices_thread])

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        if on_complete:
            on_complete()

    threading.Thread(target=_orchestrate_fetch, daemon=True).start()


# --------------------------
# AUTO-REFRESH
# --------------------------

def _should_auto_refresh() -> tuple[bool, Optional[str]]:
    """Check if auto-refresh should run and return reason if not.

    Returns:
        Tuple of (should_run, skip_reason or None).
    """
    from .services import get_active_user

    if not is_market_open_ist() and not app_config.auto_refresh_outside_market_hours:
        return False, "market closed and auto_refresh_outside_market_hours disabled"

    if fetch_in_progress.is_set():
        return False, "manual refresh in progress"

    if not get_active_user():
        return False, "no user signed in"

    # Allow refresh when at least one Zerodha account is authenticated,
    # or when the user has no Zerodha accounts at all (sheets-only user
    # still benefits from gold / nifty refreshes).
    accounts = get_active_accounts()
    if accounts and not any(session_manager.is_valid(a["name"]) for a in accounts):
        return False, "no authenticated Zerodha accounts \u2013 manual login required"

    return True, None


def run_auto_refresh() -> None:
    """Periodically trigger full holdings refresh.

    Skips when market is closed (unless configured otherwise),
    when a manual refresh is in progress, or when sessions are invalid.
    """
    while True:
        time.sleep(app_config.auto_refresh_interval)

        should_run, skip_reason = _should_auto_refresh()

        if not should_run:
            logger.info("Auto-refresh skipped: %s", skip_reason)
            continue

        market_open = is_market_open_ist()
        market_status = "outside market hours" if not market_open else "during market hours"
        timestamp = datetime.now().strftime('%H:%M:%S')
        logger.info("Auto-refresh triggered at %s (%s)", timestamp, market_status)
        run_background_fetch()
