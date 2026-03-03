"""Service wiring, per-user lifecycle, status helpers, and state broadcasting."""

import json
import threading
from typing import Any, Dict, List, Optional

from .api import (AuthenticationManager, HoldingsService, SIPService,
                  ZerodhaAPIClient)
from .logging_config import logger
from .sse import sse_manager
from .utils import (SessionManager, StateManager, format_timestamp,
                    is_market_open_ist)

# Core service singletons
session_manager = SessionManager()
state_manager = StateManager()
auth_manager = AuthenticationManager(session_manager)
holdings_service = HoldingsService()
sip_service = SIPService()
zerodha_client = ZerodhaAPIClient(auth_manager, holdings_service, sip_service)

# User lifecycle tracking
_loaded_users_lock = threading.Lock()
_loaded_users: set[str] = set()


def ensure_user_loaded(google_id: str) -> None:
    """Load user's Zerodha sessions from Firestore (idempotent)."""
    if not google_id:
        return
    with _loaded_users_lock:
        if google_id in _loaded_users:
            return
        _loaded_users.add(google_id)

    session_manager.load_user(google_id)
    from .fetchers import run_background_fetch
    run_background_fetch(google_id=google_id)


def get_user_accounts(google_id: str) -> List[Dict[str, str]]:
    if not google_id:
        return []
    try:
        from .firebase_store import get_zerodha_accounts
        return get_zerodha_accounts(google_id)
    except Exception:
        logger.exception("Failed to fetch Zerodha accounts for user %s", google_id)
        return []


def get_authenticated_accounts(google_id: str) -> List[Dict[str, str]]:
    return [acc for acc in get_user_accounts(google_id)
            if session_manager.is_valid(google_id, acc["name"])]


def _build_status_response(google_id: str = None) -> Dict[str, Any]:
    """Build status dict for API and SSE, scoped to *google_id* if provided."""
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
    }
    for st in StateManager.GLOBAL_STATE_TYPES:
        response[f"{st}_state"] = getattr(state_manager, f"{st}_state")
        response[f"{st}_last_updated"] = format_timestamp(
            getattr(state_manager, f"{st}_last_updated"))
    return response


def broadcast_state_change(google_id: str = None) -> None:
    """Broadcast status to SSE clients (per-user if google_id given, else all)."""
    try:
        if google_id:
            sse_manager.broadcast_to_user(google_id, json.dumps(_build_status_response(google_id)))
        else:
            for gid in sse_manager.connected_user_ids():
                try:
                    sse_manager.broadcast_to_user(gid, json.dumps(_build_status_response(gid)))
                except Exception:
                    logger.exception("Error building state for user %s", gid)
    except Exception:
        logger.exception("Error broadcasting state change")


state_manager.add_change_listener(lambda google_id=None: broadcast_state_change(google_id))
