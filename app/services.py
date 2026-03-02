"""
Service instance initialization, status helpers, and state broadcasting.

This module wires together the core services used throughout the application
and provides shared helper functions for status reporting.
"""

import json
import threading
from typing import Any, Dict, List

from .api import (AuthenticationManager, HoldingsService, SIPService,
                  ZerodhaAPIClient)
from .config import app_config
from .logging_config import logger
from .sse import sse_manager
from .utils import (SessionManager, StateManager, format_timestamp,
                    is_market_open_ist)

# --------------------------
# CORE SERVICES
# --------------------------

session_manager = SessionManager()
state_manager = StateManager()
auth_manager = AuthenticationManager(session_manager)
holdings_service = HoldingsService()
sip_service = SIPService()
zerodha_client = ZerodhaAPIClient(auth_manager, holdings_service, sip_service)

# --------------------------
# ACTIVE USER / ACCOUNTS
# --------------------------

_active_user_lock = threading.Lock()
_active_google_id: str | None = None


def set_active_user(google_id: str) -> None:
    """Store the currently signed-in user's Google ID for background threads.

    Also scopes the session manager to this user so that Zerodha tokens are
    loaded from / saved to the correct Firestore document.
    """
    global _active_google_id
    with _active_user_lock:
        _active_google_id = google_id
    session_manager.set_user(google_id)


def get_active_user() -> str | None:
    """Return the active user's Google ID."""
    with _active_user_lock:
        return _active_google_id


def get_active_accounts() -> List[Dict[str, str]]:
    """Return Zerodha account configs for the active user from Firebase.

    Returns an empty list when no user is signed in or the user has no
    accounts configured.
    """
    gid = get_active_user()
    if not gid:
        return []
    try:
        from .firebase_store import get_zerodha_accounts
        return get_zerodha_accounts(gid)
    except Exception:
        logger.exception("Failed to fetch Zerodha accounts for user %s", gid)
        return []


def get_authenticated_accounts() -> List[Dict[str, str]]:
    """Return Zerodha accounts that currently have valid sessions.

    Pre-filters accounts so callers only receive accounts that are ready
    for data fetching (no login required).
    """
    accounts = get_active_accounts()
    return [acc for acc in accounts if session_manager.is_valid(acc["name"])]


# --------------------------
# STATUS HELPERS
# --------------------------


def _build_status_response() -> Dict[str, Any]:
    """Build comprehensive status response for API and SSE.

    Returns:
        Dictionary containing application state, timestamps, and session info.
        Key fields:
        - has_zerodha_accounts:    whether the user has any Zerodha accounts
        - authenticated_accounts:  list of account names with valid sessions
        - unauthenticated_accounts: list of dicts {name, login_url} needing login
        - session_validity:        {name: bool} map (kept for settings drawer)
        - login_urls:              {name: url} for expired accounts
    """
    accounts = get_active_accounts()

    authenticated = []
    unauthenticated = []
    login_urls = {}
    session_validity = {}

    for acc in accounts:
        name = acc["name"]
        if session_manager.is_valid(name):
            authenticated.append(name)
            session_validity[name] = True
        else:
            try:
                from kiteconnect import KiteConnect
                login_url = KiteConnect(api_key=acc["api_key"]).login_url()
            except Exception:
                login_url = None
            unauthenticated.append({"name": name, "login_url": login_url})
            login_urls[name] = login_url
            session_validity[name] = False

    response = {
        "last_error": state_manager.last_error,
        "market_open": is_market_open_ist(),
        "has_zerodha_accounts": len(accounts) > 0,
        "authenticated_accounts": authenticated,
        "unauthenticated_accounts": unauthenticated,
        "session_validity": session_validity,
        "login_urls": login_urls,
    }
    for st in StateManager.STATE_TYPES:
        response[f"{st}_state"] = getattr(state_manager, f"{st}_state")
        response[f"{st}_last_updated"] = format_timestamp(
            getattr(state_manager, f"{st}_last_updated")
        )
    return response


def broadcast_state_change() -> None:
    """Broadcast current state to all connected SSE clients."""
    try:
        message = json.dumps(_build_status_response())
        sse_manager.broadcast(message)
    except Exception:
        logger.exception("Error broadcasting state change")


# Register state change listener for automatic broadcasting
state_manager.add_change_listener(broadcast_state_change)
