"""
Flask application creation and route definitions.


"""

import json
import os
import secrets
import threading
from queue import Empty, Queue
from typing import Any, Dict, List, Optional

from flask import (Flask, Response, jsonify, make_response, redirect,
                   render_template, request, session, url_for)

from .api.physical_gold import enrich_holdings_with_prices
from .cache import cache, fetch_in_progress, user_sheets_cache
from .config import app_config
from .constants import HTTP_ACCEPTED, HTTP_CONFLICT, MARKET_INDEX_CACHE_TTL, SSE_KEEPALIVE_INTERVAL
from .logging_config import logger
from .services import (_build_status_response,
                       auth_manager, set_active_user, get_active_accounts,
                       get_authenticated_accounts, sse_manager)

# --------------------------
# FLASK APP FACTORIES
# --------------------------

def _create_flask_app(name: str, enable_static: bool = False) -> Flask:
    """Create and configure a Flask application.

    Args:
        name: Application name.
        enable_static: Whether to enable static folder.

    Returns:
        Configured Flask app instance.
    """
    app = Flask(name)
    base_dir = os.path.dirname(__file__)
    app.template_folder = os.path.join(base_dir, "templates")

    if enable_static:
        app.static_folder = os.path.join(base_dir, "static")
        app.config['JSON_SORT_KEYS'] = False
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False

    return app


app_ui = _create_flask_app("ui_server", enable_static=True)

# Session secret — required for Flask's ``session`` cookie
app_ui.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))


# --------------------------
# HELPERS
# --------------------------

def _create_json_response_no_cache(data: List[Dict[str, Any]], sort_key: Optional[str] = None) -> Response:
    """Create JSON response with no-cache headers and optional sorting.

    Args:
        data: Data to serialize as JSON.
        sort_key: Optional key to sort data by.

    Returns:
        Flask Response with JSON data and no-cache headers.
    """
    sorted_data = sorted(data, key=lambda x: x.get(sort_key, "")) if sort_key else data
    response = jsonify(sorted_data)
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


def _get_current_user() -> Optional[Dict[str, Any]]:
    """Return the current user dict from session, or None if not signed in."""
    return session.get("user")


def _get_user_google_credentials():
    """Build Google OAuth credentials for the signed‑in user.

    Returns the credentials object or ``None`` if not available.
    """
    from .api.google_auth import credentials_from_dict
    user = _get_current_user()
    if not user:
        return None
    creds_dict = user.get("google_credentials")
    if not creds_dict:
        return None
    return credentials_from_dict(creds_dict)


# Per-user lock to serialise Sheets fetches and prevent duplicate calls
# when /physical_gold_data and /fixed_deposits_data hit the server concurrently.
_user_fetch_locks: Dict[str, threading.Lock] = {}
_user_fetch_locks_guard = threading.Lock()


def _get_user_fetch_lock(google_id: str) -> threading.Lock:
    """Return (or create) a per-user lock for serialising Sheets fetches."""
    with _user_fetch_locks_guard:
        if google_id not in _user_fetch_locks:
            _user_fetch_locks[google_id] = threading.Lock()
        return _user_fetch_locks[google_id]


def _fetch_user_sheets_data(user):
    """Return (physical_gold, fixed_deposits) for a signed-in user.

    Uses a TTL cache to avoid hitting Google Sheets on every request.
    A per-user lock prevents concurrent requests (e.g. parallel
    /physical_gold_data and /fixed_deposits_data) from triggering
    duplicate Sheets fetches.

    Returns (None, None) if the user has no spreadsheet.
    """
    google_id = user.get("google_id", "")
    spreadsheet_id = user.get("spreadsheet_id")
    creds_dict = user.get("google_credentials")
    if not spreadsheet_id or not creds_dict:
        return None, None

    # Fast path: return cached data without acquiring the lock
    cached = user_sheets_cache.get(google_id)
    if cached:
        return cached.physical_gold, cached.fixed_deposits

    # Serialise per-user fetches so concurrent requests share one Sheets call
    with _get_user_fetch_lock(google_id):
        # Re-check cache under lock (another thread may have just populated it)
        cached = user_sheets_cache.get(google_id)
        if cached:
            return cached.physical_gold, cached.fixed_deposits

        try:
            from .api.google_auth import credentials_from_dict
            from .api.google_sheets_client import GoogleSheetsClient, PhysicalGoldService, FixedDepositsService
            from .api.fixed_deposits import calculate_current_value

            creds = credentials_from_dict(creds_dict)
            client = GoogleSheetsClient(user_credentials=creds)

            gold_service = PhysicalGoldService(client)
            gold = gold_service.fetch_holdings(spreadsheet_id, "Gold!A:F")

            fd_service = FixedDepositsService(client)
            deposits = fd_service.fetch_deposits(spreadsheet_id, "FixedDeposits!A:K")
            deposits = calculate_current_value(deposits)

            user_sheets_cache.put(google_id, physical_gold=gold, fixed_deposits=deposits)
            logger.info("Fetched & cached Sheets data for user %s", google_id)
            return gold, deposits
        except Exception:
            logger.exception("Error fetching per-user Sheets data")
            return None, None

# --------------------------
# GOOGLE SIGN-IN ROUTES
# --------------------------

@app_ui.route("/auth/google/login", methods=["GET"])
def google_login():
    """Redirect the user to Google's OAuth 2.0 consent screen."""
    from .api.google_auth import build_oauth_flow

    try:
        redirect_uri = request.url_root.rstrip("/") + "/auth/google/callback"
        flow = build_oauth_flow(redirect_uri)
        authorization_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        session["oauth_state"] = state
        return redirect(authorization_url)
    except FileNotFoundError as e:
        logger.error("Google OAuth setup incomplete: %s", e)
        return render_template("auth_error.html",
                               error_title="Google Sign-In Not Configured",
                               error_message=str(e)), 500
    except Exception as e:
        logger.exception("Failed to start Google OAuth flow: %s", e)
        return render_template("auth_error.html",
                               error_title="Sign-In Error",
                               error_message=str(e)), 500


@app_ui.route("/auth/google/callback", methods=["GET"])
def google_callback():
    """Handle the OAuth 2.0 callback from Google."""
    from .api.google_auth import (
        credentials_to_dict,
        exchange_code_for_credentials,
        get_user_info,
    )
    from .api.user_sheets import create_portfolio_sheet
    from .firebase_store import get_user, update_spreadsheet_id, upsert_user

    code = request.args.get("code")
    if not code:
        return render_template("callback_error.html"), 400

    redirect_uri = request.url_root.rstrip("/") + "/auth/google/callback"

    try:
        credentials = exchange_code_for_credentials(code, redirect_uri)
        user_info = get_user_info(credentials)
        creds_dict = credentials_to_dict(credentials)

        google_id = user_info["id"]
        email = user_info.get("email", "")
        name = user_info.get("name", "")
        picture = user_info.get("picture", "")

        # Upsert in Firebase
        existing = get_user(google_id)
        spreadsheet_id = existing.get("spreadsheet_id", "") if existing else ""

        user_doc = upsert_user(
            google_id=google_id,
            email=email,
            name=name,
            picture=picture,
            google_credentials=creds_dict,
            spreadsheet_id=spreadsheet_id,
        )

        # Create a portfolio sheet if the user doesn't have one yet
        if not spreadsheet_id:
            spreadsheet_id = create_portfolio_sheet(
                credentials, title=f"Metron – {name or email}"
            )
            update_spreadsheet_id(google_id, spreadsheet_id)
            user_doc["spreadsheet_id"] = spreadsheet_id

        # Store essential info in Flask session (cookie)
        session["user"] = {
            "google_id": google_id,
            "email": email,
            "name": name,
            "picture": picture,
            "spreadsheet_id": spreadsheet_id,
            "google_credentials": creds_dict,
        }

        return redirect("/")

    except Exception as e:
        logger.exception("Google OAuth callback failed: %s", e)
        return render_template("callback_error.html"), 500


@app_ui.route("/auth/me", methods=["GET"])
def auth_me():
    """Return current user info (or 401 if not signed in)."""
    user = _get_current_user()
    if not user:
        return jsonify({"authenticated": False}), 401
    return jsonify({
        "authenticated": True,
        "email": user.get("email"),
        "name": user.get("name"),
        "picture": user.get("picture"),
        "spreadsheet_id": user.get("spreadsheet_id"),
    })


@app_ui.route("/auth/logout", methods=["POST"])
def auth_logout():
    """Sign out the current user."""
    session.clear()
    return jsonify({"status": "logged_out"})


# --------------------------
# ZERODHA OAUTH CALLBACK ROUTE
# --------------------------

@app_ui.route("/callback", methods=["GET"])

def zerodha_callback():
    """Handle OAuth callback from KiteConnect login (Zerodha)."""
    from .services import session_manager, state_manager, get_active_accounts, set_active_user
    from .cache import fetch_in_progress
    req_token = request.args.get("request_token")
    if not req_token:
        return render_template("callback_error.html")

    # Ensure Google user is set in session manager for correct session saving
    user = session.get("user")
    if not user or not user.get("google_id"):
        logger.warning("No active Google user in session during Zerodha callback")
        return render_template("callback_error.html")
    set_active_user(user["google_id"])

    # Try each non-valid account until one succeeds with this request token
    accounts = get_active_accounts()
    authenticated_account = None
    for acc in accounts:
        if session_manager.is_valid(acc["name"]):
            continue
        try:
            from kiteconnect import KiteConnect
            kite = KiteConnect(api_key=acc["api_key"])
            session_data = kite.generate_session(req_token, api_secret=acc["api_secret"])
            access_token = session_data.get("access_token")
            if access_token:
                session_manager.set_token(acc["name"], access_token)
                session_manager.save()
                authenticated_account = acc["name"]
                break
        except Exception:
            continue

    if not authenticated_account:
        return render_template("callback_error.html")

    logger.info("Login succeeded for %s", authenticated_account)
    # Broadcast updated session state to all SSE clients
    state_manager._notify_change()

    # Trigger data refresh for all now-authenticated accounts (may be a
    # subset if other accounts still need login – that’s fine).
    auth_accounts = [acc for acc in accounts if session_manager.is_valid(acc["name"])]
    if auth_accounts and not fetch_in_progress.is_set():
        from .fetchers import run_background_fetch
        run_background_fetch(accounts=auth_accounts)

    return render_template("callback_success.html")


# --------------------------
# UI SERVER ROUTES
# --------------------------

@app_ui.route("/status", methods=["GET"])
def status():
    """Return current application status and session validity."""
    response = jsonify(_build_status_response())
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


@app_ui.route("/events", methods=["GET"])
def events():
    """Server-Sent Events endpoint for real-time status updates."""
    def event_stream():
        client_queue = Queue(maxsize=10)
        sse_manager.add_client(client_queue)
        try:
            yield f"data: {json.dumps(_build_status_response())}\n\n"
            while True:
                try:
                    message = client_queue.get(timeout=SSE_KEEPALIVE_INTERVAL)
                    yield f"data: {message}\n\n"
                except Empty:
                    yield ": keepalive\n\n"
        except GeneratorExit:
            pass
        finally:
            sse_manager.remove_client(client_queue)

    return Response(event_stream(), mimetype='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no',
        'Connection': 'keep-alive',
    })


@app_ui.route("/stocks_data", methods=["GET"])
def stocks_data():
    """Return stock holdings as JSON."""
    return _create_json_response_no_cache(cache.stocks, sort_key="tradingsymbol")


@app_ui.route("/mf_holdings_data", methods=["GET"])
def mf_holdings_data():
    """Return mutual fund holdings as JSON."""
    return _create_json_response_no_cache(cache.mf_holdings, sort_key="fund")


@app_ui.route("/sips_data", methods=["GET"])
def sips_data():
    """Return SIPs (Systematic Investment Plans) as JSON."""
    return _create_json_response_no_cache(cache.sips, sort_key="status")


@app_ui.route("/nifty50_data", methods=["GET"])
def nifty50_data():
    """Return Nifty 50 stocks data as JSON."""
    return _create_json_response_no_cache(cache.nifty50, sort_key="symbol")


@app_ui.route("/physical_gold_data", methods=["GET"])
def physical_gold_data():
    """Return physical gold holdings as JSON with latest IBJA prices."""
    user = _get_current_user()
    if user:
        gold, _ = _fetch_user_sheets_data(user)
        if gold is not None:
            enriched = enrich_holdings_with_prices(gold, cache.gold_prices)
            return _create_json_response_no_cache(enriched, sort_key="date")

    return _create_json_response_no_cache([], sort_key="date")


@app_ui.route("/fixed_deposits_data", methods=["GET"])
def fixed_deposits_data():
    """Return fixed deposits as JSON with maturity status."""
    user = _get_current_user()
    if user:
        _, deposits = _fetch_user_sheets_data(user)
        if deposits is not None:
            return _create_json_response_no_cache(deposits, sort_key="deposited_on")

    return _create_json_response_no_cache([], sort_key="deposited_on")


@app_ui.route("/fd_summary_data", methods=["GET"])
def fd_summary_data():
    """Return empty FD summary.

    The frontend computes this from fixed deposits data client-side.
    Kept for backward compatibility with non-JS consumers.
    """
    return _create_json_response_no_cache([])


@app_ui.route("/market_indices", methods=["GET"])
def market_indices():
    """Return market index and commodity data with TTL caching."""
    from datetime import datetime, timedelta
    from .api.market_data import MarketDataClient

    # Return cached data if still fresh
    if (cache.market_indices and cache.market_indices_last_fetch and
            datetime.now() - cache.market_indices_last_fetch < timedelta(seconds=MARKET_INDEX_CACHE_TTL)):
        response = jsonify(cache.market_indices)
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return response

    client = MarketDataClient()
    data = client.fetch_market_indices()
    cache.market_indices = data
    cache.market_indices_last_fetch = datetime.now()

    response = jsonify(data)
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


@app_ui.route("/refresh", methods=["POST"])
def refresh_route():
    """Trigger a manual data refresh.

    Fetches portfolio data only for authenticated Zerodha accounts.
    Always refreshes gold prices, Nifty 50, and (via cache invalidation)
    Google Sheets data.
    """
    from .fetchers import run_background_fetch

    if fetch_in_progress.is_set():
        return make_response(jsonify({"error": "Fetch already in progress"}), HTTP_CONFLICT)

    # Invalidate per-user Sheets cache so the next fetch gets fresh data
    user = _get_current_user()
    if user and user.get("google_id"):
        set_active_user(user["google_id"])
        user_sheets_cache.invalidate(user["google_id"])

    # Only fetch portfolio data for accounts that are already authenticated.
    # Accounts needing login are surfaced via the login banner / toast.
    authenticated = get_authenticated_accounts()
    run_background_fetch(is_manual=True, accounts=authenticated)

    return make_response(jsonify({"status": "started"}), HTTP_ACCEPTED)


@app_ui.route("/", methods=["GET"])
def portfolio_page():
    """Serve the landing page or the portfolio dashboard.

    If the user is signed in via Google, render the portfolio with
    all cached data inlined so the UI renders instantly (no extra
    fetch round-trips on page load).
    """
    user = _get_current_user()
    if not user:
        return render_template("landing.html")

    # Track active user so background threads can look up accounts
    set_active_user(user.get("google_id", ""))

    physical_gold_enabled = True
    fixed_deposits_enabled = True

    # Build initial data payload so the browser can render immediately.
    user_gold, user_fds = _fetch_user_sheets_data(user)

    gold_data = user_gold if user_gold is not None else []
    fd_data = user_fds if user_fds is not None else []

    enriched_gold = enrich_holdings_with_prices(gold_data, cache.gold_prices)
    initial_data = {
        "stocks": sorted(cache.stocks, key=lambda x: x.get("tradingsymbol", "")),
        "mfHoldings": sorted(cache.mf_holdings, key=lambda x: x.get("fund", "")),
        "sips": sorted(cache.sips, key=lambda x: x.get("status", "")),
        "physicalGold": sorted(enriched_gold, key=lambda x: x.get("date", "")),
        "fixedDeposits": sorted(fd_data, key=lambda x: x.get("deposited_on", "")),
        "fdSummary": [],
        "status": _build_status_response(),
    }

    return render_template(
        "portfolio.html",
        physical_gold_enabled=physical_gold_enabled,
        fixed_deposits_enabled=fixed_deposits_enabled,
        user=user,
        initial_data_json=json.dumps(initial_data, default=str),
    )


@app_ui.route("/nifty50", methods=["GET"])
def nifty50_page():
    """Serve the Nifty 50 stocks page."""
    return render_template("nifty50.html")


# --------------------------
# SETTINGS
# --------------------------

@app_ui.route("/api/settings", methods=["GET"])
def get_settings():
    """Return connected Zerodha account names with session validity and login URLs."""
    user = _get_current_user()
    if not user:
        return jsonify({"error": "not authenticated"}), 401

    from .firebase_store import get_zerodha_accounts
    from .services import session_manager
    accounts = get_zerodha_accounts(user["google_id"])
    names = [acc["name"] for acc in accounts]
    validity = session_manager.get_validity(names)

    # Build login URLs for expired accounts so the drawer can show them directly
    login_urls = {}
    for acc in accounts:
        if not session_manager.is_valid(acc["name"]):
            try:
                from kiteconnect import KiteConnect
                login_urls[acc["name"]] = KiteConnect(api_key=acc["api_key"]).login_url()
            except Exception:
                pass

    return jsonify({"zerodha_accounts": names, "session_validity": validity, "login_urls": login_urls})


@app_ui.route("/api/settings/zerodha", methods=["POST"])
def add_zerodha():
    """Add a new Zerodha account for the signed-in user."""
    user = _get_current_user()
    if not user:
        return jsonify({"error": "not authenticated"}), 401

    data = request.get_json(silent=True) or {}
    account_name = (data.get("account_name") or "").strip()
    api_key = (data.get("api_key") or "").strip()
    api_secret = (data.get("api_secret") or "").strip()

    if not account_name or not api_key or not api_secret:
        return jsonify({"error": "account_name, api_key, and api_secret are required"}), 400

    from .firebase_store import add_zerodha_account
    try:
        add_zerodha_account(user["google_id"], account_name, api_key, api_secret)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409

    return jsonify({"status": "saved", "account_name": account_name})


@app_ui.route("/api/settings/zerodha/<account_name>", methods=["DELETE"])
def remove_zerodha(account_name):
    """Remove a Zerodha account by name."""
    user = _get_current_user()
    if not user:
        return jsonify({"error": "not authenticated"}), 401

    from .firebase_store import remove_zerodha_account
    try:
        remove_zerodha_account(user["google_id"], account_name)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404

    return jsonify({"status": "removed"})
