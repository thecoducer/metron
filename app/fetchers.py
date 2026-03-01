"""
Data fetching functions and auto-refresh scheduling.

Contains all background data-fetching logic for portfolio, Nifty 50,
physical gold, and fixed deposits, plus the auto-refresh scheduler.
"""

import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from requests.exceptions import ConnectionError, Timeout

from .api import NSEAPIClient
from .api.fixed_deposits import calculate_current_value
from .api.ibja_gold_price import get_gold_price_service
from .cache import cache, fetch_in_progress, nifty50_fetch_in_progress
from .config import app_config
from .constants import GOLD_PRICE_FETCH_HOURS, NIFTY50_FALLBACK_SYMBOLS
from .logging_config import logger
from .services import (_all_sessions_valid, fixed_deposits_service,
                       physical_gold_service, state_manager, zerodha_client)
from .utils import is_market_open_ist

# --------------------------
# PORTFOLIO DATA
# --------------------------

def fetch_portfolio_data(force_login: bool = False) -> None:
    """Fetch holdings and SIPs for all configured accounts.

    Args:
        force_login: If True, force re-authentication even if cached tokens exist.
    """
    fetch_in_progress.set()
    state_manager.set_portfolio_updating()
    error_occurred = None

    try:
        merged_stocks, merged_mfs, merged_sips, error_occurred = \
            zerodha_client.fetch_all_accounts_data(app_config.accounts, force_login)

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
# GOLD PRICE SCHEDULING
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


# --------------------------
# PHYSICAL GOLD
# --------------------------

def fetch_physical_gold_and_fixed_deposits_data(force_gold_price_fetch: bool = False) -> None:
    """Fetch physical gold and fixed deposits from Google Sheets in a single batch request.

    Uses batch API to fetch both data sources efficiently in one call.

    Args:
        force_gold_price_fetch: If True, bypass schedule and fetch gold prices immediately.
    """
    state_manager.set_physical_gold_updating()
    state_manager.set_fixed_deposits_updating()
    gold_error_occurred = False
    fd_error_occurred = False

    # Fallback if services not available
    if not physical_gold_service or not fixed_deposits_service:
        _fetch_physical_gold_individual(force_gold_price_fetch)
        _fetch_fixed_deposits_individual()
        return

    try:
        gold_sheets_config = app_config.features.get("fetch_physical_gold_from_google_sheets", {})
        fd_sheets_config = app_config.features.get("fetch_fixed_deposits_from_google_sheets", {})

        gold_spreadsheet_id = gold_sheets_config.get("spreadsheet_id")
        fd_spreadsheet_id = fd_sheets_config.get("spreadsheet_id")

        # If both are configured in same spreadsheet, batch fetch
        if gold_spreadsheet_id and fd_spreadsheet_id and gold_spreadsheet_id == fd_spreadsheet_id:
            gold_sheet_name = gold_sheets_config.get("range_name", "Sheet1!A:K").split('!')[0]
            fd_sheet_name = fd_sheets_config.get("range_name", "FixedDeposits!A:K").split('!')[0]

            logger.info("Batch fetching Physical Gold and Fixed Deposits from Google Sheets...")
            
            # Single batch request for both sheets
            batch_ranges = [
                f"{gold_sheet_name}!A1:Z1000",
                f"{fd_sheet_name}!A1:Z1000"
            ]

            batch_data = physical_gold_service.client.batch_fetch_sheet_data(gold_spreadsheet_id, batch_ranges)

            logger.info("Batch data keys: %s", list(batch_data.keys()))

            # Google Sheets API returns valueRanges in the same order as requested
            # Extract values by finding the matching sheet name in returned keys
            gold_data = []
            fd_data = []
            
            for range_key, values in batch_data.items():
                logger.info("Processing batch key: %s, rows: %d, gold_sheet_name: %s, fd_sheet_name: %s", 
                           range_key, len(values), gold_sheet_name, fd_sheet_name)
                if range_key.startswith(gold_sheet_name):
                    gold_data = values
                    logger.info("Assigned gold data from key: %s, rows: %d", range_key, len(values))
                elif range_key.startswith(fd_sheet_name):
                    fd_data = values
                    logger.info("Assigned FD data from key: %s, rows: %d", range_key, len(values))

            logger.info("Gold data rows: %d, FD data rows: %d", len(gold_data), len(fd_data))

            # Process physical gold
            try:
                holdings = physical_gold_service._parse_batch_data(gold_data)
                cache.physical_gold = holdings
                logger.info("Physical Gold data updated: %d holdings", len(holdings))
            except Exception as e:
                logger.exception("Error processing Physical Gold data: %s", e)
                gold_error_occurred = True

            # Process fixed deposits
            try:
                deposits = fixed_deposits_service._parse_batch_data(fd_data)
                deposits = calculate_current_value(deposits)
                cache.fixed_deposits = deposits
                cache.fd_summary = _compute_fd_summary(deposits)
                logger.info("Fixed Deposits data updated: %d deposits, %d summary groups",
                           len(deposits), len(cache.fd_summary))
            except Exception as e:
                logger.exception("Error processing Fixed Deposits data: %s", e)
                fd_error_occurred = True
        else:
            # Fallback to individual fetches if not in same spreadsheet
            _fetch_physical_gold_individual(force_gold_price_fetch)
            _fetch_fixed_deposits_individual()
            return

        # Fetch gold prices if needed
        should_fetch = force_gold_price_fetch or _should_fetch_gold_prices()
        if should_fetch:
            try:
                gold_service = get_gold_price_service()
                gold_prices = gold_service.fetch_gold_prices()
                if gold_prices:
                    cache.gold_prices = gold_prices
                    cache.gold_prices_last_fetch = datetime.now()
                    logger.info("Gold prices updated: %s", list(gold_prices.keys()))
                else:
                    logger.warning("Failed to fetch gold prices - keeping cached prices if available")
            except Exception as gold_error:
                logger.error("Error fetching gold prices: %s - keeping cached prices", gold_error)
        else:
            scheduled_times = ", ".join([f"{h}:00" for h in GOLD_PRICE_FETCH_HOURS])
            logger.info("Skipping gold price fetch - using cached prices (next scheduled: %s IST)", scheduled_times)

    except Exception as e:
        logger.exception("Error in batch fetch: %s", e)
        gold_error_occurred = True
        fd_error_occurred = True
        logger.info(
            "Preserved %d existing physical gold holdings and %d fixed deposits after fetch failure",
            len(cache.physical_gold), len(cache.fixed_deposits),
        )
    finally:
        gold_msg = "Failed to fetch physical gold data" if gold_error_occurred else None
        fd_msg = "Failed to fetch fixed deposits data" if fd_error_occurred else None
        state_manager.set_physical_gold_updated(error=gold_msg)
        state_manager.set_fixed_deposits_updated(error=fd_msg)


def _fetch_physical_gold_individual(force_gold_price_fetch: bool = False) -> None:
    """Fallback: Fetch physical gold individually."""
    if not physical_gold_service:
        return

    error_occurred = False
    try:
        google_sheets_config = app_config.features.get("fetch_physical_gold_from_google_sheets", {})
        spreadsheet_id = google_sheets_config.get("spreadsheet_id")
        range_name = google_sheets_config.get("range_name", "Sheet1!A:K")

        if not spreadsheet_id:
            return

        logger.info("Fetching Physical Gold data from Google Sheets...")
        holdings = physical_gold_service.fetch_holdings(spreadsheet_id, range_name)
        cache.physical_gold = holdings
        logger.info("Physical Gold data updated: %d holdings", len(holdings))

        should_fetch = force_gold_price_fetch or _should_fetch_gold_prices()
        if should_fetch:
            try:
                gold_service = get_gold_price_service()
                gold_prices = gold_service.fetch_gold_prices()
                if gold_prices:
                    cache.gold_prices = gold_prices
                    cache.gold_prices_last_fetch = datetime.now()
                    logger.info("Gold prices updated: %s", list(gold_prices.keys()))
            except Exception as gold_error:
                logger.error("Error fetching gold prices: %s", gold_error)
    except Exception as e:
        logger.exception("Error fetching Physical Gold data: %s", e)
        error_occurred = True
        logger.info("Preserved %d existing physical gold holdings after fetch failure", len(cache.physical_gold))
    finally:
        error_msg = "Failed to fetch physical gold data" if error_occurred else None
        state_manager.set_physical_gold_updated(error=error_msg)


# --------------------------
# FIXED DEPOSITS
# --------------------------

def _fetch_fixed_deposits_individual() -> None:
    """Fallback: Fetch fixed deposits individually."""
    if not fixed_deposits_service:
        return

    error_occurred = False
    try:
        fixed_deposits_config = app_config.features.get("fetch_fixed_deposits_from_google_sheets", {})
        spreadsheet_id = fixed_deposits_config.get("spreadsheet_id")
        range_name = fixed_deposits_config.get("range_name", "FixedDeposits!A2:K")

        if not spreadsheet_id:
            return

        logger.info("Fetching Fixed Deposits data from Google Sheets...")
        deposits = fixed_deposits_service.fetch_deposits(spreadsheet_id, range_name)
        cache.fixed_deposits = calculate_current_value(deposits)
        cache.fd_summary = _compute_fd_summary(cache.fixed_deposits)
        logger.info("Fixed Deposits data updated: %d deposits, %d summary groups",
                   len(cache.fixed_deposits), len(cache.fd_summary))
    except Exception as e:
        logger.exception("Error fetching Fixed Deposits data: %s", e)
        error_occurred = True
        logger.info("Preserved %d existing fixed deposits after fetch failure", len(cache.fixed_deposits))
    finally:
        error_msg = "Failed to fetch fixed deposits data" if error_occurred else None
        state_manager.set_fixed_deposits_updated(error=error_msg)


# --------------------------
# FIXED DEPOSITS (LEGACY - for backward compatibility)
# --------------------------

def fetch_fixed_deposits_data() -> None:
    """Fetch fixed deposits from Google Sheets (legacy, use batch fetch instead)."""
    _fetch_fixed_deposits_individual()


def _compute_fd_summary(deposits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Compute FD summary grouped by bank and account.

    Args:
        deposits: List of fixed deposit records.

    Returns:
        List of summary dictionaries with bank, account, and aggregated amounts.
    """
    if not deposits:
        return []

    groups: Dict[str, Dict[str, Any]] = {}
    for deposit in deposits:
        bank = deposit.get('bank_name', 'Unknown')
        account = deposit.get('account', 'Unknown')
        group_key = f"{bank}|{account}"

        if group_key not in groups:
            groups[group_key] = {
                'bank': bank,
                'account': account,
                'totalDeposited': 0,
                'totalCurrentValue': 0,
                'totalReturns': 0,
            }

        groups[group_key]['totalDeposited'] += deposit.get('original_amount', 0)
        groups[group_key]['totalCurrentValue'] += deposit.get('current_value', 0)

    for group in groups.values():
        group['totalReturns'] = group['totalCurrentValue'] - group['totalDeposited']

    return list(groups.values())


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

            nse_client = NSEAPIClient()

            symbols = nse_client.fetch_nifty50_symbols()
            if not symbols:
                logger.warning("Failed to fetch symbols from NSE, using fallback list")
                symbols = NIFTY50_FALLBACK_SYMBOLS

            try:
                session = nse_client._create_session()
            except (Timeout, ConnectionError) as e:
                logger.error("Failed to create NSE session: %s", e)
                raise

            nifty50_data = [
                nse_client.fetch_stock_quote(session, symbol)
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
    force_login: bool = False,
    on_complete: Optional[callable] = None,
    is_manual: bool = False,
) -> None:
    """Orchestrate concurrent fetching of portfolio and market data.

    Launches parallel background tasks:
    1. Portfolio data (holdings and SIPs) from Zerodha.
    2. Nifty 50 market data from NSE.
    3. Physical Gold data from Google Sheets (if configured).
    4. Fixed Deposits data from Google Sheets (if configured).

    Args:
        force_login: If True, force re-authentication for portfolio data.
        on_complete: Optional callback to execute after all tasks complete.
        is_manual: If True, this is a manual refresh (always fetch gold prices).
    """
    def _orchestrate_fetch():
        force_gold_fetch = is_manual or (cache.gold_prices_last_fetch is None)

        portfolio_thread = threading.Thread(
            target=fetch_portfolio_data,
            args=(force_login,),
            name="PortfolioFetch",
            daemon=True,
        )
        nifty50_thread = threading.Thread(
            target=fetch_nifty50_data,
            name="Nifty50Fetch",
            daemon=True,
        )
        # Use batch fetch for both physical gold and fixed deposits (single API call)
        google_sheets_thread = threading.Thread(
            target=fetch_physical_gold_and_fixed_deposits_data,
            args=(force_gold_fetch,),
            name="GoogleSheetsBatchFetch",
            daemon=True,
        )

        portfolio_thread.start()
        nifty50_thread.start()
        google_sheets_thread.start()

        portfolio_thread.join()
        nifty50_thread.join()
        google_sheets_thread.join()

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
    market_open = is_market_open_ist()

    if not market_open and not app_config.auto_refresh_outside_market_hours:
        return False, "market closed and auto_refresh_outside_market_hours disabled"

    if fetch_in_progress.is_set():
        return False, "manual refresh in progress"

    if not _all_sessions_valid():
        return False, "one or more sessions invalid - manual login required"

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
        run_background_fetch(force_login=False)
