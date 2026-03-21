"""Flask route definitions. All user data is scoped via session."""

import json
import os
import secrets
import threading
import time
from typing import Any

import psutil
from flask import Flask, Response, jsonify, make_response, redirect, render_template, request, session
from werkzeug.middleware.proxy_fix import ProxyFix

from .api.google_sheets_client import is_blank_row
from .api.physical_gold import enrich_holdings_with_prices
from .cache import manual_ltp_cache, market_cache, portfolio_cache, user_sheets_cache
from .constants import HTTP_ACCEPTED, HTTP_CONFLICT, PORTFOLIO_TABLE_ROW_LIMIT
from .fetchers import get_google_creds_dict, prefetch_all_user_sheets
from .firebase_store import reset_zerodha_data, verify_user_pin
from .logging_config import logger
from .middleware import app_only, login_required, pin_required, protected_api
from .services import (
    _build_status_response,
    ensure_user_loaded,
    get_authenticated_accounts,
    get_user_accounts,
    session_manager,
)
from .utils import format_date_for_sheet, pin_rate_limiter

_REAUTH_MESSAGE = "Google session expired. Please sign in again."
_BYTES_PER_MB = 1024 * 1024


def _collect_process_metrics() -> dict[str, Any]:
    """Collect process-level health metrics for the /healthz endpoint."""
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()

    return {
        "memory": {
            "rss_mb": round(mem_info.rss / _BYTES_PER_MB, 1),
        },
        "cpu_percent": round(process.cpu_percent(interval=None), 1),
        "uptime_seconds": round(time.time() - process.create_time()),
        "threads": process.num_threads(),
    }


def _sheets_error_response(exc: Exception, action: str, sheet_type: str) -> tuple:
    """Return an appropriate Flask error response for Google Sheets exceptions."""
    if _is_google_auth_error(exc):
        logger.warning("Auth error %s %s: %s", action, sheet_type, exc)
        return jsonify({"error": _REAUTH_MESSAGE}), 401
    logger.exception("Error %s %s", action, sheet_type)
    return jsonify({"error": str(exc)}), 500


def _is_google_auth_error(exc: Exception) -> bool:
    """Return True if *exc* is a Google credential refresh / auth failure."""
    name = type(exc).__name__
    return "RefreshError" in name or "InvalidGrantError" in name


def _create_flask_app(name: str, enable_static: bool = False) -> Flask:
    """Create and configure a Flask app with templates and optional static files."""
    app = Flask(name)
    base_dir = os.path.dirname(__file__)
    app.template_folder = os.path.join(base_dir, "templates")
    if enable_static:
        app.static_folder = os.path.join(base_dir, "static")
        app.config["JSON_SORT_KEYS"] = False
        app.config["JSONIFY_PRETTYPRINT_REGULAR"] = False
    return app


app_ui = _create_flask_app("ui_server", enable_static=True)

# Trust proxy headers from Render / load balancers so request.url_root
# correctly reports https:// instead of http://.
app_ui.wsgi_app = ProxyFix(app_ui.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# Session secret — MUST be a stable value in production so sessions survive
# container restarts.  A random fallback is used for local dev only.
_secret = os.environ.get("FLASK_SECRET_KEY")
if not _secret:
    logger.warning(
        "FLASK_SECRET_KEY not set — using a random key. "
        "Sessions will NOT survive restarts. Set this env var in production."
    )
    _secret = secrets.token_hex(32)
app_ui.secret_key = _secret

# Production session cookie settings
app_ui.config.update(
    SESSION_COOKIE_NAME="__session",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_ENV") != "development",
)


# ---------------------------------------------------------------------------
# Health check (Render liveness probe)
# ---------------------------------------------------------------------------


@app_ui.route("/healthz", methods=["GET"])
def healthz():
    """Health check with basic performance metrics for Render / load balancer probes."""
    from .api.mf_market_data import mf_market_cache

    metrics = _collect_process_metrics()
    return jsonify({"status": "ok", **metrics, "cron": {"market_data": mf_market_cache.status}}), 200


# ---------------------------------------------------------------------------
# PWA: serve service-worker at root scope
# ---------------------------------------------------------------------------


@app_ui.route("/service-worker.js", methods=["GET"])
def service_worker():
    """Serve the service worker from root so it can control all pages."""
    resp = make_response(app_ui.send_static_file("service-worker.js"))
    resp.headers["Content-Type"] = "application/javascript"
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@app_ui.before_request
def _sync_spreadsheet_id():
    """Sync spreadsheet_id from Firebase if missing in session."""
    user = session.get("user")
    if user and not user.get("spreadsheet_id"):
        from .firebase_store import get_user

        existing = get_user(user["google_id"])
        if existing and existing.get("spreadsheet_id"):
            user["spreadsheet_id"] = existing["spreadsheet_id"]
            session["user"] = user
            session.modified = True


@app_ui.after_request
def _set_cache_headers(response):
    """Set Cache-Control headers for Cloudflare edge + browser caching.

    - Static assets (/static/*): public, 1-hour browser + edge cache.
    - Everything else (HTML pages, API): private, no-store so Cloudflare
      never caches auth-dependent or dynamic responses.
    """
    if request.path.startswith("/static/"):
        # Only add if not already set by a specific route handler
        if "Cache-Control" not in response.headers:
            response.headers["Cache-Control"] = "public, max-age=3600"
    else:
        # Never let Cloudflare cache HTML or API responses.
        # Skip if a route already set an explicit Cache-Control (e.g. no-cache on SW).
        if "Cache-Control" not in response.headers:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            response.headers["Pragma"] = "no-cache"
    return response


def _json_response(data: list[dict[str, Any]], sort_key: str | None = None) -> Response:
    """JSON response with no-cache headers and optional sorting."""
    sorted_data = sorted(data, key=lambda x: x.get(sort_key, "")) if sort_key else data
    resp = jsonify(sorted_data)
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


def _current_user() -> dict[str, Any] | None:
    """Return the authenticated user dict from the session, or None."""
    return session.get("user")


def _get_google_creds_dict(user: dict[str, Any] | None = None) -> dict | None:
    """Return decrypted Google OAuth credentials for the current/given user."""
    if user is None:
        user = _current_user()
    return get_google_creds_dict(user) if user else None


def _fetch_user_sheets_data(user):
    """Return (physical_gold, fixed_deposits) from cache.

    Returns whatever is available now (may be ``(None, None)`` when
    the background sheets fetch hasn't completed yet).
    """
    google_id = user.get("google_id", "")
    cached = user_sheets_cache.get(google_id)
    if cached:
        return cached.physical_gold, cached.fixed_deposits
    return None, None


def _fetch_manual_entries(user, sheet_type):
    """Fetch manual entries from the sheets cache, returning a list of dicts."""
    google_id = user.get("google_id", "")
    cached = user_sheets_cache.get_manual(google_id, sheet_type)
    return cached if cached is not None else []


def _prefetch_all_user_sheets(user):
    """Thin wrapper — delegates to fetchers.prefetch_all_user_sheets."""
    prefetch_all_user_sheets(user)


@app_ui.route("/api/auth/google/login", methods=["GET"])
def google_login():
    """Redirect to Google OAuth consent screen."""
    from .api.google_auth import build_oauth_flow

    try:
        redirect_uri = request.url_root.rstrip("/") + "/api/auth/google/callback"
        logger.info("OAuth login initiated, redirect_uri=%s", redirect_uri)
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
        return render_template(
            "auth_error.html", error_title="Google Sign-In Not Configured", error_message=str(e)
        ), 500
    except Exception as e:
        logger.exception("Failed to start Google OAuth flow: %s", e)
        return render_template("auth_error.html", error_title="Sign-In Error", error_message=str(e)), 500


@app_ui.route("/api/auth/google/callback", methods=["GET"])
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

    redirect_uri = request.url_root.rstrip("/") + "/api/auth/google/callback"

    try:
        credentials = exchange_code_for_credentials(code, redirect_uri)
        user_info = get_user_info(credentials)
        creds_dict = credentials_to_dict(credentials)

        google_id = user_info["id"]
        email = user_info.get("email", "")
        name = user_info.get("name", "")
        picture = user_info.get("picture", "")

        existing = get_user(google_id)
        spreadsheet_id = existing.get("spreadsheet_id", "") if existing else ""
        is_new_user = existing is None
        logger.info("OAuth callback success: new_user=%s", is_new_user)

        upsert_user(
            google_id=google_id,
            email=email,
            name=name,
            picture=picture,
            google_credentials=creds_dict,
            spreadsheet_id=spreadsheet_id,
        )

        if not spreadsheet_id:
            # Spawn a background thread to create the Google Sheet.
            # Uses the live credentials object (not yet serialised)
            # since thread starts before the response is sent.
            def _create_sheet_bg(creds, title, gid):
                try:
                    sid = create_portfolio_sheet(creds, title=title)
                    update_spreadsheet_id(gid, sid)
                    logger.info("Background sheet creation done")
                except Exception:
                    logger.exception("Background sheet creation failed")

            threading.Thread(
                target=_create_sheet_bg,
                args=(credentials, f"Metron – {name or email}", google_id),
                daemon=True,
            ).start()

        session["user"] = {
            "google_id": google_id,
            "email": email,
            "name": name,
            "picture": picture,
            "spreadsheet_id": spreadsheet_id,
            "google_credentials": creds_dict,
        }
        # PIN is not yet verified at this point — the frontend will prompt
        session.pop("pin_verified", None)

        return redirect("/")

    except Exception as e:
        logger.exception("Google OAuth callback failed: %s", e)
        return render_template("callback_error.html"), 500


@app_ui.route("/api/auth/me", methods=["GET"])
def auth_me():
    """Return current user info (or 401 if not signed in)."""
    user = _current_user()
    if not user:
        return jsonify({"authenticated": False}), 401
    return jsonify(
        {
            "authenticated": True,
            "email": user.get("email"),
            "name": user.get("name"),
            "picture": user.get("picture"),
            "spreadsheet_id": user.get("spreadsheet_id"),
        }
    )


@app_ui.route("/api/auth/logout", methods=["POST"])
@app_only
def auth_logout():
    """Sign out the current user and clear PIN from memory."""
    user = _current_user()
    if user:
        gid = user.get("google_id", "")
        logger.info("User logout")
        session_manager.clear_pin(gid)
    session.clear()
    return jsonify({"status": "logged_out"})


# ---------------------------------------------------------------------------
# Security PIN endpoints
# ---------------------------------------------------------------------------


@app_ui.route("/api/pin/status", methods=["GET"])
@protected_api
def pin_status():
    """Return whether the user has set a PIN and whether it's verified this session."""
    from .firebase_store import get_zerodha_account_names, has_pin

    user = _current_user()
    google_id = user["google_id"]
    has_setup_pin = has_pin(google_id)
    has_accounts = len(get_zerodha_account_names(google_id)) > 0
    pin_verified = session.get("pin_verified", False)
    # PIN needed when user has accounts or has set up a PIN previously
    needs_pin = has_setup_pin and not pin_verified

    return jsonify(
        {
            "has_pin": has_setup_pin,
            "has_zerodha_accounts": has_accounts,
            "pin_verified": pin_verified,
            "needs_pin": needs_pin,
        }
    )


@app_ui.route("/api/pin/verify", methods=["POST"])
@protected_api
def pin_verify():
    """Verify the user's security PIN.  Stores PIN in memory on success."""
    user = _current_user()
    google_id = user["google_id"]

    # ── Rate-limit check ──
    allowed, retry_after = pin_rate_limiter.check(google_id)
    if not allowed:
        logger.warning("PIN verify rate-limited: retry_after=%ds", retry_after)
        resp = jsonify(
            {
                "error": "Too many failed attempts",
                "retry_after": retry_after,
                "locked": True,
            }
        )
        resp.status_code = 429
        resp.headers["Retry-After"] = str(retry_after)
        return resp

    data = request.get_json(silent=True) or {}
    pin = (data.get("pin") or "").strip()

    if not pin or len(pin) != 6 or not pin.isalnum():
        logger.info("PIN verify: invalid format")
        return jsonify({"error": "PIN must be exactly 6 alphanumeric characters"}), 400

    if not verify_user_pin(google_id, pin):
        attempts, lockout_secs = pin_rate_limiter.record_failure(google_id)
        logger.warning(
            "PIN verify failed: attempts=%d lockout=%s", attempts, f"{lockout_secs}s" if lockout_secs else "none"
        )
        resp_data = {"error": "Incorrect PIN", "attempts": attempts}
        if lockout_secs:
            resp_data["retry_after"] = lockout_secs
            resp_data["locked"] = True
            resp = jsonify(resp_data)
            resp.status_code = 429
            resp.headers["Retry-After"] = str(lockout_secs)
            return resp
        return jsonify(resp_data), 401

    # Success — clear rate-limit state
    pin_rate_limiter.record_success(google_id)
    logger.info("PIN verified successfully")

    # Store PIN in server memory and mark session as verified
    session_manager.set_pin(google_id, pin)
    session["pin_verified"] = True
    session.modified = True

    # Now that we have the PIN, load Zerodha sessions from Firestore
    # (force=True because the initial page load skipped this)
    ensure_user_loaded(google_id, force=True)

    return jsonify({"status": "verified"})


@app_ui.route("/api/pin/setup", methods=["POST"])
@protected_api
def pin_setup():
    """Set up a new security PIN.  Only allowed when user has no PIN yet."""
    from .firebase_store import has_pin, store_pin_check

    user = _current_user()
    google_id = user["google_id"]
    data = request.get_json(silent=True) or {}
    pin = (data.get("pin") or "").strip()

    if not pin or len(pin) != 6 or not pin.isalnum():
        return jsonify({"error": "PIN must be exactly 6 alphanumeric characters"}), 400

    if has_pin(google_id):
        logger.warning("PIN setup rejected: already has PIN")
        return jsonify({"error": "PIN already set. Use reset to change it."}), 409

    store_pin_check(google_id, pin)
    session_manager.set_pin(google_id, pin)
    session["pin_verified"] = True
    session.modified = True
    logger.info("PIN created")

    # Trigger background data loading now that PIN is available
    ensure_user_loaded(google_id, force=True)

    return jsonify({"status": "pin_created"})


@app_ui.route("/api/pin/reset", methods=["POST"])
@protected_api
def pin_reset():
    """Reset the user's PIN.  Wipes all Zerodha credentials and sessions.

    The user must re-add Zerodha accounts and set a new PIN afterward.
    """
    user = _current_user()
    google_id = user["google_id"]

    reset_zerodha_data(google_id)

    # Clear in-memory state (including rate limiter)
    session_manager.clear_pin(google_id)
    pin_rate_limiter.clear(google_id)
    session.pop("pin_verified", None)
    session.modified = True
    portfolio_cache.clear(google_id)
    logger.info("PIN reset complete (all Zerodha data wiped)")

    return jsonify({"status": "reset_complete"})


@app_ui.route("/api/callback", methods=["GET"])
def zerodha_callback():
    """Handle Zerodha KiteConnect OAuth callback."""
    req_token = request.args.get("request_token")
    if not req_token:
        logger.warning("Zerodha callback missing request_token")
        return render_template("callback_error.html")

    user = session.get("user")
    if not user or not user.get("google_id"):
        logger.warning("Zerodha callback without active session")
        return render_template("callback_error.html")

    google_id = user["google_id"]
    logger.info("Zerodha callback started")

    # PIN must be available to decrypt account credentials
    pin = session_manager.get_pin(google_id)
    if not pin:
        logger.warning("Zerodha callback: PIN not in memory")
        return render_template("callback_error.html")

    ensure_user_loaded(google_id)

    accounts = get_user_accounts(google_id)
    authenticated_account = None
    for acc in accounts:
        if session_manager.is_valid(google_id, acc["name"]):
            logger.debug("Zerodha callback: skipping already-valid account")
            continue
        try:
            from kiteconnect import KiteConnect

            kite = KiteConnect(api_key=acc["api_key"])
            session_data = kite.generate_session(req_token, api_secret=acc["api_secret"])
            access_token = session_data.get("access_token")
            if access_token:
                session_manager.set_token(google_id, acc["name"], access_token)
                session_manager.save(google_id)
                authenticated_account = acc["name"]
                break
        except Exception as e:
            logger.warning("Zerodha callback: session generation failed: %s", e)
            continue

    if not authenticated_account:
        logger.warning("Zerodha callback: no account authenticated")
        return render_template("callback_error.html")

    logger.info("Zerodha login succeeded")

    auth_accounts = [acc for acc in accounts if session_manager.is_valid(google_id, acc["name"])]
    if auth_accounts and not portfolio_cache.is_fetch_in_progress(google_id):
        from .fetchers import run_background_fetch

        run_background_fetch(google_id=google_id, accounts=auth_accounts)

    return render_template("callback_success.html")


@app_ui.route("/api/status", methods=["GET"])
@protected_api
def status():
    """Return portfolio fetch status, authenticated accounts, and session validity."""
    user = _current_user()
    google_id = user.get("google_id")
    response = jsonify(_build_status_response(google_id))
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


def _build_stocks_data(user):
    """Build merged broker + manual stocks list with live LTPs.

    When broker is connected (live data in cache), broker entries take
    precedence and zerodha-sourced sheet rows are skipped.  When broker
    is offline, persisted zerodha entries from sheets serve as fallback.
    """
    google_id = user["google_id"]
    user_data = portfolio_cache.get(google_id)
    connected_accounts = user_data.connected_accounts

    # Only use cached broker data when at least one broker session is live;
    # when all offline, synced sheet data is the sole source of truth.
    broker_stocks = []
    if connected_accounts:
        for s in user_data.stocks:
            s.setdefault("source", "zerodha")
            broker_stocks.append(s)
        for s in user_data.etfs:
            # Tag ETFs so the frontend can classify without ISIN/symbol heuristics.
            s.setdefault("source", "zerodha")
            s.setdefault("manual_type", "etfs")
            broker_stocks.append(s)

    sheet_entries = []
    for sheet_type in ("stocks", "etfs"):
        entries = _fetch_manual_entries(user, sheet_type)
        for m in entries:
            source = m.get("source", "manual")

            # Skip persisted zerodha rows only for accounts with a live session;
            # rows for disconnected accounts serve as fallback.
            if source == "zerodha" and m.get("account", "") in connected_accounts:
                continue

            qty = float(m.get("qty") or 0)
            avg = float(m.get("avg_price") or 0)
            sheet_entries.append(
                {
                    "tradingsymbol": (m.get("symbol") or "").upper(),
                    "quantity": qty,
                    "average_price": avg,
                    "last_price": avg,  # fallback; enriched below
                    "invested": qty * avg,
                    "exchange": m.get("exchange", "NSE"),
                    "account": m.get("account", "Manual") if source == "manual" else m.get("account", ""),
                    "day_change": 0,
                    "day_change_percentage": 0,
                    "isin": (m.get("isin") or "").strip().upper(),
                    "source": source,
                    "row_number": m.get("row_number"),
                    "manual_type": sheet_type,
                }
            )

    # Enrich sheet entries (both manual and zerodha-fallback) with LTP
    if sheet_entries:
        _enrich_manual_entries_with_ltp(sheet_entries)

    broker_stocks.extend(sheet_entries)
    return sorted(broker_stocks, key=lambda x: x.get("tradingsymbol", ""))


def _validate_nse_symbol(symbol: str) -> dict | None:
    """Validate a symbol and return its quote (with ISIN when available).

    Tries NSE India first — returns LTP + ISIN in one call.
    Falls back to Yahoo Finance if NSE is unreachable (no ISIN in that case).
    Returns None when the symbol does not exist on the exchange.
    """
    from .api.market_data import MarketDataClient

    client = MarketDataClient()
    try:
        data = client.fetch_nse_quote(symbol)
        if data and data.get("ltp"):
            return data
    except Exception:
        logger.warning("NSE validation failed for %s, trying Yahoo Finance", symbol)

    try:
        data = client.fetch_stock_quote(symbol)
        if data and data.get("ltp"):
            return data
    except Exception:
        logger.warning("Symbol validation failed for %s", symbol)
    return None


def _normalize_date_values(fields: list[str], values: list) -> None:
    """Reformat any date field in *values* to MM/DD/YYYY before saving to sheets."""
    from .api.user_sheets import DATE_FIELDS

    for i, field in enumerate(fields):
        if field in DATE_FIELDS and i < len(values) and values[i]:
            values[i] = format_date_for_sheet(values[i])


def _autofill_mf_nav_from_cache(fields: list[str], values: list) -> None:
    """Populate ISIN, latest NAV and NAV date from the MF market cache when the fund name matches.

    Looks up the fund name ("fund_name" field) in the in-memory mf_market_cache.
    If an exact match is found, fills in any empty isin, latest_nav and
    nav_updated_date columns so manual entries have up-to-date NAV data.

    Args:
        fields: Ordered list of field names for the mutual_funds sheet config.
        values: Mutable list of column values aligned with *fields*.
    """
    from .api.mf_market_data import mf_market_cache

    if not mf_market_cache.is_populated:
        return

    fund_name_idx = fields.index("fund_name") if "fund_name" in fields else -1
    if fund_name_idx < 0 or fund_name_idx >= len(values):
        return

    fund_name = str(values[fund_name_idx]).strip()
    isin = mf_market_cache.get_isin_for_name(fund_name)
    if not isin:
        return

    scheme = mf_market_cache.get_by_isin(isin)
    if not scheme:
        return

    # Only fill fields that are empty — never overwrite user-provided data.
    for field_key, value in [
        ("isin", scheme.isin),
        ("latest_nav", scheme.latest_nav),
        ("nav_updated_date", format_date_for_sheet(scheme.nav_updated_date)),
    ]:
        if field_key in fields:
            idx = fields.index(field_key)
            if idx < len(values) and not values[idx]:
                values[idx] = value

    logger.debug("MF cache autofill: fund_name=%s isin=%s nav=%s", fund_name, scheme.isin, scheme.latest_nav)


def _fetch_uncached_manual_ltps(user: dict, new_symbol: str = "") -> None:
    """Fetch LTPs for all uncached manual stock/ETF symbols after a CRUD add.

    Collects symbols from both stocks and etfs sheets, adds the newly-added
    symbol, then batch-fetches any that aren't already in the LTP cache.
    """
    try:
        from .api.market_data import MarketDataClient

        all_symbols: set[str] = set()
        for sheet_type in ("stocks", "etfs"):
            for entry in _fetch_manual_entries(user, sheet_type) or []:
                sym = (entry.get("symbol") or "").upper()
                if sym:
                    all_symbols.add(sym)
        if new_symbol:
            all_symbols.add(new_symbol)

        to_fetch = [s for s in all_symbols if not manual_ltp_cache.get(s) and not manual_ltp_cache.is_negative(s)]
        if not to_fetch:
            return

        fetched = MarketDataClient().fetch_stock_quotes(to_fetch)
        if fetched:
            manual_ltp_cache.put_batch(fetched)
        missed = [s for s in to_fetch if s not in (fetched or {})]
        if missed:
            manual_ltp_cache.put_negative_batch(missed)
    except Exception:
        logger.warning("Failed to fetch LTPs after CRUD add for %s", new_symbol)


def _enrich_manual_entries_with_ltp(entries: list) -> None:
    """Apply cached LTPs to manual entries (read-only, never fetches)."""
    symbols = list({e["tradingsymbol"] for e in entries if e["tradingsymbol"]})
    if not symbols:
        return

    enriched = 0
    for sym in symbols:
        cached = manual_ltp_cache.get(sym)
        if not cached or not cached.get("ltp"):
            continue
        for entry in entries:
            if entry["tradingsymbol"] == sym:
                entry["last_price"] = cached["ltp"]
                entry["day_change"] = cached.get("change", 0)
                entry["day_change_percentage"] = cached.get("pChange", 0)
                enriched += 1

    if enriched:
        logger.debug("Manual LTP enrichment: %d/%d symbols from cache", enriched, len(symbols))
    else:
        logger.debug("Manual LTP enrichment: %d symbols, all uncached", len(symbols))


def _build_mf_data(user):
    """Build merged broker + manual mutual fund holdings list.

    Zerodha-sourced sheet entries are used as fallback when broker is offline.
    """
    google_id = user["google_id"]
    user_data = portfolio_cache.get(google_id)
    connected_accounts = user_data.connected_accounts
    broker_mf = list(user_data.mf_holdings) if connected_accounts else []

    for mf in broker_mf:
        mf.setdefault("source", "zerodha")

    entries = _fetch_manual_entries(user, "mutual_funds")
    for m in entries:
        source = m.get("source", "manual")
        if source == "zerodha" and m.get("account", "") in connected_accounts:
            continue

        qty = float(m.get("qty") or 0)
        avg = float(m.get("avg_nav") or 0)
        # Column 0 is now "ISIN" (renamed from "Fund") — stores ISIN / trading symbol.
        isin = (m.get("isin") or "").upper()
        fund_name = m.get("fund_name") or isin
        # Use stored latest NAV if available, otherwise fall back to avg NAV.
        latest_nav = float(m.get("latest_nav") or 0)
        nav_date = m.get("nav_updated_date") or None
        broker_mf.append(
            {
                "fund": fund_name,
                "isin": isin,
                "quantity": qty,
                "average_price": avg,
                "last_price": latest_nav if latest_nav else avg,
                "invested": qty * avg,
                "account": m.get("account", "Manual") if source == "manual" else m.get("account", ""),
                "last_price_date": nav_date,
                "source": source,
                "row_number": m.get("row_number"),
            }
        )
    _normalize_mf_names(broker_mf)
    return sorted(broker_mf, key=lambda x: x.get("fund", ""))


def _normalize_mf_names(holdings: list[dict]) -> None:
    """Replace broker/sheet fund names with canonical names from mfapi.in.

    mfapi.in names take precedence over broker-reported names.  Equality is
    established via ISIN so entries that share an ISIN always display the
    same canonical name regardless of their source.
    """
    from .api.mf_market_data import mf_market_cache

    if not mf_market_cache.is_populated:
        return

    for mf in holdings:
        isin = (mf.get("isin") or "").upper()
        if not isin:
            continue
        scheme = mf_market_cache.get_by_isin(isin)
        if scheme:
            mf["fund"] = scheme.scheme_name.upper()


def _build_sips_data(user):
    """Build merged broker + manual SIPs list.

    Zerodha-sourced sheet entries are used as fallback when broker is offline.
    """
    google_id = user["google_id"]
    user_data = portfolio_cache.get(google_id)
    connected_accounts = user_data.connected_accounts
    broker_sips = list(user_data.sips) if connected_accounts else []

    for sip in broker_sips:
        sip.setdefault("source", "zerodha")

    entries = _fetch_manual_entries(user, "sips")
    for m in entries:
        source = m.get("source", "manual")
        if source == "zerodha" and m.get("account", "") in connected_accounts:
            continue

        fund_id = (m.get("fund") or "").upper()
        fund_display = m.get("fund_name") or fund_id
        broker_sips.append(
            {
                "fund": fund_display,
                "tradingsymbol": fund_id,
                "instalment_amount": float(m.get("amount") or 0),
                "frequency": m.get("frequency", "MONTHLY"),
                "instalments": int(m.get("installments") or -1),
                "completed_instalments": int(m.get("completed") or 0),
                "status": (m.get("status") or "ACTIVE").upper(),
                "next_instalment": m.get("next_due", ""),
                "account": m.get("account", "Manual") if source == "manual" else m.get("account", ""),
                "source": source,
                "row_number": m.get("row_number"),
            }
        )
    return sorted(broker_sips, key=lambda x: x.get("status", ""))


def _build_gold_data(user):
    """Build enriched physical gold holdings list."""
    gold, _ = _fetch_user_sheets_data(user)
    if gold is not None:
        enriched = enrich_holdings_with_prices(gold, market_cache.gold_prices)
        return sorted(enriched, key=lambda x: x.get("date", ""))
    return []


def _build_fd_data(user):
    """Build fixed deposits list."""
    _, deposits = _fetch_user_sheets_data(user)
    if deposits is not None:
        return sorted(deposits, key=lambda x: x.get("deposited_on", ""))
    return []


@app_ui.route("/api/stocks_data", methods=["GET"])
@pin_required
def stocks_data():
    """Return merged broker + manual stocks with live LTPs."""
    user = _current_user()
    return _json_response(_build_stocks_data(user))


@app_ui.route("/api/mf_holdings_data", methods=["GET"])
@pin_required
def mf_holdings_data():
    """Return merged broker + manual mutual fund holdings."""
    user = _current_user()
    return _json_response(_build_mf_data(user))


@app_ui.route("/api/mutual_funds/search", methods=["GET"])
@login_required
def mutual_funds_search():
    """Search mutual fund names from the in-memory mfapi.in cache.

    Query params:
      q (str): Search string — minimum 2 characters.

    Returns up to 20 matching scheme names as a JSON array.
    """
    from .api.mf_market_data import mf_market_cache

    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    return jsonify(mf_market_cache.search_names(q))


@app_ui.route("/api/sips_data", methods=["GET"])
@pin_required
def sips_data():
    """Return merged broker + manual SIPs."""
    user = _current_user()
    return _json_response(_build_sips_data(user))


@app_ui.route("/api/nifty50_data", methods=["GET"])
@app_only
def nifty50_data():
    """Return cached Nifty 50 constituent data."""
    return _json_response(market_cache.nifty50, sort_key="symbol")


@app_ui.route("/api/physical_gold_data", methods=["GET"])
@pin_required
def physical_gold_data():
    """Return enriched physical gold holdings with IBJA prices."""
    user = _current_user()
    return _json_response(_build_gold_data(user))


@app_ui.route("/api/fixed_deposits_data", methods=["GET"])
@pin_required
def fixed_deposits_data():
    """Return fixed deposits with maturity calculations."""
    user = _current_user()
    return _json_response(_build_fd_data(user))


@app_ui.route("/api/data/portfolio", methods=["GET"])
@pin_required
def portfolio_data():
    """Return broker-sourced portfolio data (stocks, MFs, SIPs) + status."""
    _t0 = time.monotonic()
    user = _current_user()
    google_id = user["google_id"]
    payload = {
        "stocks": _build_stocks_data(user),
        "mfHoldings": _build_mf_data(user),
        "sips": _build_sips_data(user),
        "status": _build_status_response(google_id),
    }
    logger.info("portfolio data served in %.2fs", time.monotonic() - _t0)
    resp = jsonify(payload)
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


@app_ui.route("/api/data/sheets", methods=["GET"])
@pin_required
def sheets_data():
    """Return Google Sheets data (gold, FDs) + status."""
    _t0 = time.monotonic()
    user = _current_user()
    google_id = user["google_id"]
    payload = {
        "physicalGold": _build_gold_data(user),
        "fixedDeposits": _build_fd_data(user),
        "status": _build_status_response(google_id),
    }
    logger.info("sheets data served in %.2fs", time.monotonic() - _t0)
    resp = jsonify(payload)
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


@app_ui.route("/api/all_data", methods=["GET"])
@pin_required
def all_data():
    """Return all portfolio data in a single response (legacy/initial load)."""
    _t0 = time.monotonic()
    user = _current_user()
    google_id = user["google_id"]
    payload = {
        "stocks": _build_stocks_data(user),
        "mfHoldings": _build_mf_data(user),
        "sips": _build_sips_data(user),
        "physicalGold": _build_gold_data(user),
        "fixedDeposits": _build_fd_data(user),
        "status": _build_status_response(google_id),
    }
    logger.info("all_data served in %.2fs", time.monotonic() - _t0)
    resp = jsonify(payload)
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


@app_ui.route("/api/fd_summary_data", methods=["GET"])
@pin_required
def fd_summary_data():
    """Return fixed deposit summary (currently unused, returns empty list)."""
    return _json_response([])


@app_ui.route("/api/market_indices", methods=["GET"])
@app_only
def market_indices():
    """Serve cached market index data.

    Market indices are fetched by ``run_background_fetch`` (on login and
    manual refresh) and stored in ``market_cache``.  This endpoint only
    serves the cached snapshot — it never triggers a Yahoo Finance call
    itself.
    """
    data = market_cache.market_indices or {}
    response = jsonify(data)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@app_ui.route("/api/refresh", methods=["POST"])
@pin_required
def refresh_route():
    """Trigger manual data refresh for the signed-in user."""
    from .fetchers import collect_manual_symbols, run_background_fetch

    user = _current_user()
    google_id = user["google_id"]

    if portfolio_cache.is_fetch_in_progress(google_id):
        logger.info("Manual refresh rejected: already in progress")
        return make_response(jsonify({"error": "Fetch already in progress"}), HTTP_CONFLICT)

    ensure_user_loaded(google_id)

    # Collect symbols before invalidation (cache will be cleared)
    manual_symbols = collect_manual_symbols(google_id)

    user_sheets_cache.invalidate(google_id)
    manual_ltp_cache.invalidate()

    authenticated = get_authenticated_accounts(google_id)
    logger.info("Manual refresh started")
    run_background_fetch(
        is_manual=True,
        accounts=authenticated,
        google_id=google_id,
        manual_symbols=manual_symbols,
    )

    return make_response(jsonify({"status": "started"}), HTTP_ACCEPTED)


@app_ui.route("/", methods=["GET"])
def portfolio_page():
    """Serve landing page or portfolio dashboard with inlined data.

    For return visits with warm caches the page is rendered with inlined
    data (zero JS round-trips).  For first login or cold caches the page
    is rendered immediately with empty data and the frontend fetches
    asynchronously via ``/api/all_data``.
    """
    user = _current_user()
    if not user:
        return render_template("landing.html")

    google_id = user.get("google_id", "")
    pin_verified = session.get("pin_verified", False)

    # Validate that the in-memory PIN is still present — the session
    # cookie can be stale after a server restart.
    if pin_verified and not session_manager.get_pin(google_id):
        logger.info("portfolio_page: stale pin_verified — clearing")
        session["pin_verified"] = False
        session.modified = True
        pin_verified = False

    # Only kick off background fetches if PIN is verified *and* in memory.
    # For first login / unverified sessions the frontend shows the PIN
    # overlay first, and the pin_verify / pin_setup endpoints trigger
    # the load afterward.
    if pin_verified:
        threading.Thread(
            target=ensure_user_loaded,
            args=(google_id,),
            name=f"EnsureLoaded-{google_id[:8]}",
            daemon=True,
        ).start()

    # Try to serve inlined data from warm caches (return visits with PIN).
    # Without PIN verification the overlay blocks the UI anyway, so skip
    # the expensive Google Sheets batch-fetch.
    initial_data = None
    if pin_verified and user_sheets_cache.is_fully_cached(google_id):
        try:
            initial_data = {
                "stocks": _build_stocks_data(user),
                "mfHoldings": _build_mf_data(user),
                "sips": _build_sips_data(user),
                "physicalGold": _build_gold_data(user),
                "fixedDeposits": _build_fd_data(user),
                "fdSummary": [],
                "status": _build_status_response(google_id),
            }
        except Exception:
            logger.debug("Cache miss building initial data for %s", google_id)
            initial_data = None

    from .firebase_store import has_pin as _has_pin

    user_has_pin = _has_pin(google_id)

    logger.info(
        "portfolio_page: pin_verified=%s inlined=%s has_pin=%s",
        pin_verified,
        initial_data is not None,
        user_has_pin,
    )

    return render_template(
        "portfolio.html",
        physical_gold_enabled=True,
        fixed_deposits_enabled=True,
        user=user,
        initial_data_json=json.dumps(initial_data, default=str) if initial_data else None,
        table_row_limit=PORTFOLIO_TABLE_ROW_LIMIT,
        pin_verified=session.get("pin_verified", False),
        has_pin=user_has_pin,
    )


# ---------------------------------------------------------------------------
# Standalone table detail page (full table view with pagination)
# ---------------------------------------------------------------------------
# Valid table keys — prevents arbitrary template injection
_VALID_TABLE_KEYS = frozenset(
    {
        "stocks",
        "etfs",
        "mutual-funds",
        "physical-gold",
        "fixed-deposits",
        "sips",
    }
)

_TABLE_DISPLAY_NAMES = {
    "stocks": "Stocks",
    "etfs": "ETFs",
    "mutual-funds": "Mutual Funds",
    "physical-gold": "Physical Gold",
    "fixed-deposits": "Fixed Deposits",
    "sips": "SIPs",
}


@app_ui.route("/details/<table_key>", methods=["GET"])
@login_required
def standalone_table_page(table_key):
    """Serve a standalone full-table view with pagination for a given table."""
    if table_key not in _VALID_TABLE_KEYS:
        return redirect("/")

    user = _current_user()

    return render_template(
        "table_detail.html",
        table_key=table_key,
        table_title=_TABLE_DISPLAY_NAMES.get(table_key, table_key.replace("-", " ").title()),
        user=user,
    )


@app_ui.route("/nifty50", methods=["GET"])
@login_required
def nifty50_page():
    """Serve the Nifty 50 stocks page."""
    user = _current_user()
    response = make_response(render_template("nifty50.html", user=user))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@app_ui.route("/privacy", methods=["GET"])
def privacy_page():
    """Serve the Privacy Policy page."""
    return render_template("privacy.html")


@app_ui.route("/terms", methods=["GET"])
def terms_page():
    """Serve the Terms & Conditions page."""
    return render_template("terms.html")


@app_ui.route("/contact", methods=["GET"])
def contact_page():
    """Serve the Contact Us page."""
    return render_template("contact.html")


@app_ui.route("/api/settings", methods=["GET"])
@pin_required
def get_settings():
    """Return user's Zerodha accounts, session validity, and login URLs."""
    user = _current_user()
    from .firebase_store import get_zerodha_accounts

    google_id = user["google_id"]
    pin = session_manager.get_pin(google_id) or ""
    accounts = get_zerodha_accounts(google_id, pin)
    names = [acc["name"] for acc in accounts]
    validity = session_manager.get_validity(google_id, names)

    login_urls = {}
    for acc in accounts:
        if not session_manager.is_valid(google_id, acc["name"]):
            try:
                from kiteconnect import KiteConnect

                login_urls[acc["name"]] = KiteConnect(api_key=acc["api_key"]).login_url()
            except Exception:
                pass

    return jsonify({"zerodha_accounts": names, "session_validity": validity, "login_urls": login_urls})


@app_ui.route("/api/settings/zerodha", methods=["POST"])
@pin_required
def add_zerodha():
    """Add a new Zerodha account for the signed-in user."""
    user = _current_user()
    data = request.get_json(silent=True) or {}
    account_name = (data.get("account_name") or "").strip()
    api_key = (data.get("api_key") or "").strip()
    api_secret = (data.get("api_secret") or "").strip()

    if not account_name or not api_key or not api_secret:
        return jsonify({"error": "account_name, api_key, and api_secret are required"}), 400

    google_id = user["google_id"]
    pin = session_manager.get_pin(google_id) or ""
    if not pin:
        # Defensive: decorator should catch this, but clear flag just in case
        session["pin_verified"] = False
        session.modified = True
        return jsonify({"error": "pin_required"}), 403

    from .firebase_store import add_zerodha_account

    try:
        add_zerodha_account(google_id, account_name, api_key, api_secret, pin=pin)
    except ValueError as exc:
        logger.warning("add_zerodha conflict: user=%s account=%s reason=%s", google_id[:8], account_name, exc)
        return jsonify({"error": str(exc)}), 409

    logger.info("add_zerodha: user=%s account=%s", google_id[:8], account_name)
    return jsonify({"status": "saved", "account_name": account_name})


@app_ui.route("/api/settings/zerodha/<account_name>", methods=["DELETE"])
@pin_required
def remove_zerodha(account_name):
    """Remove a Zerodha account by name."""
    user = _current_user()
    google_id = user["google_id"]
    from .firebase_store import remove_zerodha_account

    try:
        remove_zerodha_account(google_id, account_name)
    except ValueError as exc:
        logger.warning("remove_zerodha not found: user=%s account=%s", google_id[:8], account_name)
        return jsonify({"error": str(exc)}), 404

    # Clean up session token and cached portfolio data for the removed account
    session_manager.invalidate(google_id, account_name)
    portfolio_cache.clear(google_id)

    # Remove this account's synced rows from Google Sheets
    from .broker_sync import delete_account_from_sheets

    try:
        delete_account_from_sheets(google_id, account_name)
    except Exception:
        logger.warning("remove_zerodha: sheet cleanup failed for %s", account_name)

    logger.info("remove_zerodha: user=%s account=%s (session+cache+sheet cleared)", google_id[:8], account_name)

    return jsonify({"status": "removed"})


# ---------------------------------------------------------------------------
# Manual-entry CRUD  (Google Sheets backed)
# ---------------------------------------------------------------------------


def _get_sheets_client():
    """Return an authenticated GoogleSheetsClient for the current user."""
    from .api.google_auth import credentials_from_dict
    from .api.google_sheets_client import GoogleSheetsClient

    user = _current_user()
    creds_dict = _get_google_creds_dict(user)
    if not creds_dict:
        return None, None, "Google credentials not available"
    creds = credentials_from_dict(creds_dict)
    client = GoogleSheetsClient(user_credentials=creds)
    spreadsheet_id = user.get("spreadsheet_id")
    if not spreadsheet_id:
        return None, None, "No spreadsheet linked"
    return client, spreadsheet_id, None


# Mapping: sheet_type → frontend data key for CRUD response
_SHEET_TYPE_DATA_KEY = {
    "stocks": "stocks",
    "etfs": "stocks",  # ETFs merge into the stocks table
    "mutual_funds": "mfHoldings",
    "sips": "sips",
    "physical_gold": "physicalGold",
    "fixed_deposits": "fixedDeposits",
}


def _refresh_single_sheet_cache(client, spreadsheet_id, google_id, sheet_type):
    """Re-fetch and re-cache a single sheet type after a CRUD mutation.

    Reads only the affected sheet from Google Sheets (not all 6),
    preserving cache entries for every other type.
    """
    from .api.user_sheets import SHEET_CONFIGS

    cfg = SHEET_CONFIGS.get(sheet_type)
    if not cfg:
        return

    try:
        raw = client.fetch_sheet_data_until_blank(spreadsheet_id, cfg["sheet_name"])
    except Exception:
        logger.exception("Error re-reading %s after CRUD", sheet_type)
        user_sheets_cache.invalidate(google_id)
        return

    if sheet_type == "physical_gold":
        from .api.google_sheets_client import PhysicalGoldService

        svc = PhysicalGoldService(client)
        parsed = svc._parse_batch_data(raw)
        user_sheets_cache.put(google_id, physical_gold=parsed)

    elif sheet_type == "fixed_deposits":
        from .api.fixed_deposits import calculate_current_value
        from .api.google_sheets_client import FixedDepositsService

        svc = FixedDepositsService(client)
        parsed = calculate_current_value(svc._parse_batch_data(raw))
        user_sheets_cache.put(google_id, fixed_deposits=parsed)

    else:
        # Manual types: stocks, etfs, mutual_funds, sips
        rows = []
        if raw and len(raw) >= 2:
            fields = cfg["fields"]
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
        user_sheets_cache.put_manual(google_id, sheet_type, rows)


def _build_data_for_type(user, sheet_type):
    """Build and return ``{data_key: [rows]}`` for a single sheet type.

    Called after a CRUD mutation so the response can carry the refreshed
    dataset and the frontend can skip a full ``/api/all_data`` call.
    """
    data_key = _SHEET_TYPE_DATA_KEY.get(sheet_type)
    if not data_key:
        return {}

    builders = {
        "stocks": _build_stocks_data,
        "mfHoldings": _build_mf_data,
        "sips": _build_sips_data,
        "physicalGold": _build_gold_data,
        "fixedDeposits": _build_fd_data,
    }
    builder = builders.get(data_key)
    if not builder:  # pragma: no cover – all valid data_keys have builders
        return {}

    try:
        return {data_key: builder(user)}
    except Exception:
        logger.exception("Error building data for %s after CRUD", sheet_type)
        return {}


@app_ui.route("/api/sheets/<sheet_type>", methods=["GET"])
@protected_api
def sheets_list(sheet_type):
    """List all rows from a manual-entry sheet tab."""
    from .api.user_sheets import SHEET_CONFIGS

    cfg = SHEET_CONFIGS.get(sheet_type)
    if not cfg:
        return jsonify({"error": "Unknown sheet type"}), 400

    client, spreadsheet_id, err = _get_sheets_client()
    if err:
        return jsonify({"error": err}), 400

    try:
        client.ensure_sheet_tab(spreadsheet_id, cfg["sheet_name"], cfg["headers"])
        raw = client.fetch_sheet_data_until_blank(spreadsheet_id, cfg["sheet_name"])
    except Exception as e:
        return _sheets_error_response(e, "listing", sheet_type)

    if not raw or len(raw) < 2:
        return jsonify([])

    fields = cfg["fields"]
    rows = []
    for idx, row in enumerate(raw[1:], start=2):
        if is_blank_row(row):
            break
        entry = {"row_number": idx}
        for fi, fname in enumerate(fields):
            entry[fname] = row[fi] if fi < len(row) else ""
        rows.append(entry)
    return jsonify(rows)


@app_ui.route("/api/sheets/<sheet_type>", methods=["POST"])
@protected_api
def sheets_add(sheet_type):
    """Add a new row to a manual-entry sheet tab."""
    from .api.user_sheets import SHEET_CONFIGS

    cfg = SHEET_CONFIGS.get(sheet_type)
    if not cfg:
        return jsonify({"error": "Unknown sheet type"}), 400

    client, spreadsheet_id, err = _get_sheets_client()
    if err:
        return jsonify({"error": err}), 400

    data = request.get_json(silent=True) or {}
    symbol = (data.get("symbol") or "").upper()

    # Validate stock/ETF symbols against NSE before saving.
    nse_isin = ""
    if sheet_type in ("stocks", "etfs") and symbol:
        quote = _validate_nse_symbol(symbol)
        if not quote:
            return jsonify({"error": f"Symbol {symbol} doesn't exist on exchange."}), 400
        # Cache the validated LTP immediately.
        manual_ltp_cache.put(symbol, quote)
        nse_isin = quote.get("isin", "")

    values = [data.get(f, "") for f in cfg["fields"]]
    _normalize_date_values(cfg["fields"], values)
    # Auto-fill ISIN from NSE when the user left it blank.
    if nse_isin and "isin" in cfg["fields"]:
        isin_idx = cfg["fields"].index("isin")
        if not values[isin_idx]:
            values[isin_idx] = nse_isin
    # Default source to "manual" for user-added entries
    if "source" in cfg["fields"]:
        si = cfg["fields"].index("source")
        if not values[si]:
            values[si] = "manual"
    # Auto-copy fund to fund_name for manual entries
    if "fund_name" in cfg["fields"] and "fund" in cfg["fields"]:
        ni = cfg["fields"].index("fund_name")
        fi = cfg["fields"].index("fund")
        if not values[ni] and values[fi]:
            values[ni] = values[fi]
    # Auto-populate ISIN and latest NAV from in-memory MF cache when fund name matches.
    if sheet_type == "mutual_funds":
        _autofill_mf_nav_from_cache(cfg["fields"], values)

    try:
        client.ensure_sheet_tab(spreadsheet_id, cfg["sheet_name"], cfg["headers"])
        row_num = client.append_row(spreadsheet_id, cfg["sheet_name"], values)
        user = _current_user()
        google_id = user.get("google_id", "")
        _refresh_single_sheet_cache(client, spreadsheet_id, google_id, sheet_type)

        # Fetch LTPs for any other uncached manual symbols.
        if sheet_type in ("stocks", "etfs"):
            _fetch_uncached_manual_ltps(user, symbol)
    except Exception as e:
        return _sheets_error_response(e, "adding", sheet_type)

    logger.info("sheets_add: type=%s row=%d", sheet_type, row_num)
    result = {"status": "added", "row_number": row_num}
    refreshed = _build_data_for_type(user, sheet_type)
    if refreshed:
        result["data"] = refreshed
    return jsonify(result)


@app_ui.route("/api/sheets/<sheet_type>/<int:row_number>", methods=["PUT"])
@protected_api
def sheets_update(sheet_type, row_number):
    """Update a specific row in a manual-entry sheet tab."""
    from .api.user_sheets import SHEET_CONFIGS

    cfg = SHEET_CONFIGS.get(sheet_type)
    if not cfg:
        return jsonify({"error": "Unknown sheet type"}), 400

    if row_number < 2:
        return jsonify({"error": "Cannot edit header row"}), 400

    client, spreadsheet_id, err = _get_sheets_client()
    if err:
        return jsonify({"error": err}), 400

    data = request.get_json(silent=True) or {}
    symbol = (data.get("symbol") or "").upper()

    # Validate stock/ETF symbols against NSE before saving.
    nse_isin = ""
    if sheet_type in ("stocks", "etfs") and symbol:
        quote = _validate_nse_symbol(symbol)
        if not quote:
            return jsonify({"error": f"Symbol {symbol} doesn't exist on exchange."}), 400
        manual_ltp_cache.put(symbol, quote)
        nse_isin = quote.get("isin", "")

    values = [data.get(f, "") for f in cfg["fields"]]
    _normalize_date_values(cfg["fields"], values)
    # Auto-fill ISIN from NSE so existing ISIN data is preserved/refreshed on edit.
    if nse_isin and "isin" in cfg["fields"]:
        isin_idx = cfg["fields"].index("isin")
        if not values[isin_idx]:
            values[isin_idx] = nse_isin
    # Default source to "manual" for user-edited entries
    if "source" in cfg["fields"]:
        si = cfg["fields"].index("source")
        if not values[si]:
            values[si] = "manual"
    # Auto-copy fund to fund_name for manual entries
    if "fund_name" in cfg["fields"] and "fund" in cfg["fields"]:
        ni = cfg["fields"].index("fund_name")
        fi = cfg["fields"].index("fund")
        if not values[ni] and values[fi]:
            values[ni] = values[fi]
    # Auto-populate ISIN and latest NAV from in-memory MF cache when fund name matches.
    if sheet_type == "mutual_funds":
        _autofill_mf_nav_from_cache(cfg["fields"], values)

    try:
        client.update_row(spreadsheet_id, cfg["sheet_name"], row_number, values)
        user = _current_user()
        google_id = user.get("google_id", "")
        _refresh_single_sheet_cache(client, spreadsheet_id, google_id, sheet_type)
    except Exception as e:
        return _sheets_error_response(e, "updating", sheet_type)

    result = {"status": "updated"}
    refreshed = _build_data_for_type(user, sheet_type)
    if refreshed:
        result["data"] = refreshed
    return jsonify(result)


@app_ui.route("/api/sheets/<sheet_type>/<int:row_number>", methods=["DELETE"])
@protected_api
def sheets_delete(sheet_type, row_number):
    """Delete a specific row from a manual-entry sheet tab."""
    from .api.user_sheets import SHEET_CONFIGS

    cfg = SHEET_CONFIGS.get(sheet_type)
    if not cfg:
        return jsonify({"error": "Unknown sheet type"}), 400

    if row_number < 2:
        return jsonify({"error": "Cannot delete header row"}), 400

    client, spreadsheet_id, err = _get_sheets_client()
    if err:
        return jsonify({"error": err}), 400

    try:
        client.delete_row(spreadsheet_id, cfg["sheet_name"], row_number)
        # Refresh only the changed sheet in cache (not all 6).
        user = _current_user()
        google_id = user.get("google_id", "")
        _refresh_single_sheet_cache(client, spreadsheet_id, google_id, sheet_type)
    except Exception as e:
        return _sheets_error_response(e, "deleting", sheet_type)

    result = {"status": "deleted"}
    refreshed = _build_data_for_type(user, sheet_type)
    if refreshed:
        result["data"] = refreshed
    return jsonify(result)
