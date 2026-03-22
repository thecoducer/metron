"""Service wiring, per-user lifecycle, and status helpers."""

import threading
from typing import Any

from cachetools import LRUCache

from .api import AuthenticationManager, HoldingsService, SIPService, ZerodhaAPIClient
from .logging_config import logger
from .utils import SessionManager, StateManager, format_timestamp, is_market_open_ist

# Core service singletons
session_manager = SessionManager()
state_manager = StateManager()
auth_manager = AuthenticationManager(session_manager)
holdings_service = HoldingsService()
sip_service = SIPService()
zerodha_client = ZerodhaAPIClient(auth_manager, holdings_service, sip_service)

# User lifecycle tracking — bounded LRU to prevent unbounded growth.
_loaded_users_lock = threading.Lock()
_loaded_users: LRUCache[str, None] = LRUCache(maxsize=1000)


def ensure_user_loaded(google_id: str, *, force: bool = False) -> None:
    """Load user's Zerodha sessions from Firestore (idempotent).

    Args:
        google_id: The user's Google ID.
        force: When True, re-run even if the user was previously loaded.
               Use after PIN verification to load Zerodha sessions that
               were skipped on the initial PIN-less page load.
    """
    if not google_id:
        return
    with _loaded_users_lock:
        if not force and google_id in _loaded_users:
            logger.debug("ensure_user_loaded: already loaded")
            return
        _loaded_users[google_id] = None

    logger.info("ensure_user_loaded: loading, force=%s", force)
    session_manager.load_user(google_id)

    # Only fetch data if PIN is in server memory — no data fetching
    # before PIN verification (global market data included).
    if not session_manager.get_pin(google_id):
        logger.info("ensure_user_loaded: no PIN in memory, skipping background fetch")
        return

    from .fetchers import run_background_fetch

    run_background_fetch(google_id=google_id)


def get_user_accounts(google_id: str) -> list[dict[str, str]]:
    """Return the list of Zerodha accounts for *google_id*, or [] if unavailable."""
    if not google_id:
        return []
    pin = session_manager.get_pin(google_id)
    if not pin:
        return []
    try:
        from .firebase_store import get_zerodha_accounts

        return get_zerodha_accounts(google_id, pin)
    except Exception:
        logger.exception("Failed to fetch Zerodha accounts")
        return []


def get_authenticated_accounts(google_id: str) -> list[dict[str, str]]:
    """Return only the Zerodha accounts with a valid (non-expired) session."""
    return [acc for acc in get_user_accounts(google_id) if session_manager.is_valid(google_id, acc["name"])]


def _build_status_response(google_id: str = None) -> dict[str, Any]:
    """Build status dict for the API, scoped to *google_id* if provided."""
    accounts = get_user_accounts(google_id) if google_id else []

    authenticated, unauthenticated, login_urls, session_validity = [], [], {}, {}
    for acc in accounts:
        name = acc["name"]
        if session_manager.is_valid(google_id, name):
            authenticated.append(name)
            session_validity[name] = True
        else:
            try:
                from kiteconnect import KiteConnect

                url = KiteConnect(api_key=acc["api_key"]).login_url()
            except Exception:
                url = None
            unauthenticated.append({"name": name, "login_url": url})
            login_urls[name] = url
            session_validity[name] = False

    portfolio_state = state_manager.get_portfolio_state(google_id) if google_id else None
    portfolio_updated = state_manager.get_portfolio_last_updated(google_id) if google_id else None
    user_error = state_manager.get_user_last_error(google_id) if google_id else None
    manual_ltp_state = state_manager.get_manual_ltp_state(google_id) if google_id else None
    manual_ltp_updated = state_manager.get_manual_ltp_last_updated(google_id) if google_id else None
    sheets_state = state_manager.get_sheets_state(google_id) if google_id else None
    sheets_updated = state_manager.get_sheets_last_updated(google_id) if google_id else None
    exposure_updated = state_manager.get_exposure_last_updated(google_id) if google_id else None

    response = {
        "last_error": user_error or state_manager.last_error,
        "market_open": is_market_open_ist(),
        "has_zerodha_accounts": len(accounts) > 0,
        "authenticated_accounts": authenticated,
        "unauthenticated_accounts": unauthenticated,
        "session_validity": session_validity,
        "login_urls": login_urls,
        "portfolio_state": portfolio_state,
        "portfolio_last_updated": format_timestamp(portfolio_updated),
        "manual_ltp_state": manual_ltp_state,
        "manual_ltp_last_updated": format_timestamp(manual_ltp_updated),
        "sheets_state": sheets_state,
        "sheets_last_updated": format_timestamp(sheets_updated),
        "exposure_last_updated": format_timestamp(exposure_updated),
    }
    for st in StateManager.GLOBAL_STATE_TYPES:
        response[f"{st}_state"] = getattr(state_manager, f"{st}_state")
        response[f"{st}_last_updated"] = format_timestamp(getattr(state_manager, f"{st}_last_updated"))
    return response
