"""Flask route definitions. All user data is scoped via session."""

import json
import os
import secrets
import threading
from queue import Empty, Queue
from typing import Any, Dict, List, Optional

from flask import (Flask, Response, jsonify, make_response, redirect,
                   render_template, request, session)
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.middleware.proxy_fix import ProxyFix

from .api.physical_gold import enrich_holdings_with_prices
from .cache import market_cache, manual_ltp_cache, portfolio_cache, user_sheets_cache
from .constants import (HTTP_ACCEPTED, HTTP_CONFLICT, MARKET_INDEX_CACHE_TTL,
                         PORTFOLIO_TABLE_ROW_LIMIT,
                         SSE_KEEPALIVE_INTERVAL, SSE_TOKEN_MAX_AGE)
from .logging_config import logger
from .middleware import app_only, login_required, pin_required, protected_api
from .services import (_build_status_response, broadcast_state_change,
                       ensure_user_loaded, get_authenticated_accounts,
                       get_user_accounts, session_manager, sse_manager)
from .sse import EVICT_SENTINEL, SSE_MAX_CONNECTION_AGE, SSE_QUEUE_SIZE, SSE_RETRY_MS
from .firebase_store import reset_zerodha_data, verify_user_pin
from .utils import pin_rate_limiter

# ---------------------------------------------------------------------------
# Cloud Run direct URL for SSE (bypasses Firebase Hosting CDN buffering)
# ---------------------------------------------------------------------------
CLOUD_RUN_URL = os.environ.get("CLOUD_RUN_URL", "").rstrip("/")

# ---------------------------------------------------------------------------
# SSE token signing (allows direct Cloud Run SSE without cookies)
# ---------------------------------------------------------------------------
_SSE_TOKEN_SALT = "sse-auth-token"


def _create_flask_app(name: str, enable_static: bool = False) -> Flask:
    app = Flask(name)
    base_dir = os.path.dirname(__file__)
    app.template_folder = os.path.join(base_dir, "templates")
    if enable_static:
        app.static_folder = os.path.join(base_dir, "static")
        app.config['JSON_SORT_KEYS'] = False
        app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False
    return app


app_ui = _create_flask_app("ui_server", enable_static=True)

# Trust proxy headers from Cloud Run / load balancers so request.url_root
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
# IMPORTANT: Firebase Hosting strips ALL cookies except ``__session`` from both
# incoming requests and outgoing responses.  Flask's default cookie name is
# "session" which gets silently dropped, breaking OAuth and any session state.
app_ui.config.update(
    SESSION_COOKIE_NAME="__session",       # Firebase Hosting requirement
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("FLASK_ENV") != "development",
)


# ---------------------------------------------------------------------------
# SSE token helpers (for direct Cloud Run SSE, bypassing Firebase CDN)
# ---------------------------------------------------------------------------

def _generate_sse_token(google_id: str) -> str:
    """Create a short-lived signed token for SSE authentication."""
    s = URLSafeTimedSerializer(app_ui.secret_key)
    return s.dumps({"gid": google_id}, salt=_SSE_TOKEN_SALT)


def _validate_sse_token(token: str) -> Optional[str]:
    """Validate an SSE token. Returns google_id or None."""
    s = URLSafeTimedSerializer(app_ui.secret_key)
    try:
        data = s.loads(token, salt=_SSE_TOKEN_SALT, max_age=SSE_TOKEN_MAX_AGE)
        return data.get("gid")
    except (BadSignature, SignatureExpired):
        return None


# ---------------------------------------------------------------------------
# Firebase Hosting detection
# ---------------------------------------------------------------------------
_FIREBASE_HOSTING_DOMAINS = frozenset({"metron.web.app", "metron.firebaseapp.com"})


def _is_firebase_hosting_request() -> bool:
    """Return True when the request was served through Firebase Hosting.

    When Firebase Hosting rewrites to Cloud Run the ``Host`` header is
    that of the Firebase domain (metron.web.app).  When the user browses
    Cloud Run directly, the Host is the ``*.run.app`` URL — in that case
    SSE can use the relative ``/events`` path with session cookies.
    """
    host = request.host.split(":")[0].lower()  # strip port
    return host in _FIREBASE_HOSTING_DOMAINS


def _add_cors_headers(response: Response) -> Response:
    """Add CORS headers for direct Cloud Run SSE access from Firebase Hosting."""
    origin = request.headers.get("Origin", "")
    allowed = False

    if origin:
        # Always allow Firebase Hosting origins
        try:
            from urllib.parse import urlparse
            host = urlparse(origin).hostname or ""
        except Exception:
            host = ""

        if host in _FIREBASE_HOSTING_DOMAINS:
            allowed = True
        # Allow any *.run.app origin (Cloud Run URL formats vary)
        elif host.endswith(".run.app"):
            allowed = True
        # Dev origins
        elif os.environ.get("FLASK_ENV") == "development" and host in ("localhost", "127.0.0.1"):
            allowed = True

    if allowed:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Requested-With"
    return response


# ---------------------------------------------------------------------------
# Health check (Cloud Run liveness / readiness probe)
# ---------------------------------------------------------------------------

@app_ui.route("/healthz", methods=["GET"])
def healthz():
    """Lightweight health check for Cloud Run / load balancer probes."""
    return jsonify({"status": "ok"}), 200


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


def _json_response(data: List[Dict[str, Any]], sort_key: Optional[str] = None) -> Response:
    """JSON response with no-cache headers and optional sorting."""
    sorted_data = sorted(data, key=lambda x: x.get(sort_key, "")) if sort_key else data
    resp = jsonify(sorted_data)
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp


def _current_user() -> Optional[Dict[str, Any]]:
    return session.get("user")


def _get_google_creds_dict(user: Optional[Dict[str, Any]] = None) -> Optional[dict]:
    """Return decrypted Google OAuth credentials for the current/given user.

    Checks the session first (populated at OAuth callback) and falls back
    to the encrypted copy in Firestore when the session value is missing or
    is already an encrypted string.
    """
    if user is None:
        user = _current_user()
    if not user:
        return None

    creds = user.get("google_credentials")
    # The session stores creds as a plain dict right after OAuth login.
    if isinstance(creds, dict):
        return creds

    # Fallback: fetch & decrypt from Firestore
    from .firebase_store import get_google_credentials
    return get_google_credentials(user.get("google_id", ""))


_user_fetch_locks: Dict[str, threading.Lock] = {}
_user_fetch_locks_guard = threading.Lock()
_USER_FETCH_LOCKS_MAX = 500  # prevent unbounded growth


def _get_user_fetch_lock(google_id: str) -> threading.Lock:
    with _user_fetch_locks_guard:
        # Evict oldest entries if the dict grows too large
        if len(_user_fetch_locks) >= _USER_FETCH_LOCKS_MAX:
            # Remove the first (oldest) half of entries
            keys_to_remove = list(_user_fetch_locks.keys())[: _USER_FETCH_LOCKS_MAX // 2]
            for k in keys_to_remove:
                _user_fetch_locks.pop(k, None)
        return _user_fetch_locks.setdefault(google_id, threading.Lock())


def _fetch_user_sheets_data(user):
    """Return (physical_gold, fixed_deposits) with TTL caching and per-user locking."""
    google_id = user.get("google_id", "")
    spreadsheet_id = user.get("spreadsheet_id")
    creds_dict = _get_google_creds_dict(user)
    if not spreadsheet_id or not creds_dict:
        return None, None

    # Batch-fetch populates *all* sheet types into the cache in one API call.
    _prefetch_all_user_sheets(user)

    cached = user_sheets_cache.get(google_id)
    if cached:
        return cached.physical_gold, cached.fixed_deposits
    return None, None


def _fetch_manual_entries(user, sheet_type):
    """Fetch manual entries from a Google Sheet tab, returning a list of dicts.

    Results are cached per-user with the same TTL as gold/FD data.
    """
    from .api.user_sheets import SHEET_CONFIGS

    cfg = SHEET_CONFIGS.get(sheet_type)
    if not cfg:
        return []

    google_id = user.get("google_id", "")
    spreadsheet_id = user.get("spreadsheet_id")
    creds_dict = _get_google_creds_dict(user)
    if not spreadsheet_id or not creds_dict:
        return []

    # Batch-fetch populates *all* sheet types into the cache in one API call.
    _prefetch_all_user_sheets(user)

    cached = user_sheets_cache.get_manual(google_id, sheet_type)
    return cached if cached is not None else []


def _prefetch_all_user_sheets(user):
    """Batch-fetch all 6 sheet tabs in a single Google Sheets API call.

    On a cache miss this acquires the per-user lock, double-checks the
    cache, and issues one ``batchGet`` request for Gold, FixedDeposits,
    Stocks, ETFs, MutualFunds, and SIPs.  The parsed results are stored
    in `user_sheets_cache` so that subsequent calls (from concurrent HTTP
    requests) find data already cached.
    """
    google_id = user.get("google_id", "")
    spreadsheet_id = user.get("spreadsheet_id")
    creds_dict = _get_google_creds_dict(user)
    if not spreadsheet_id or not creds_dict:
        return

    # Fast path — everything already in cache.
    if user_sheets_cache.is_fully_cached(google_id):
        logger.debug("Sheets cache hit for user=%s", google_id[:8])
        return

    with _get_user_fetch_lock(google_id):
        # Double-check after acquiring lock.
        if user_sheets_cache.is_fully_cached(google_id):
            return

        import time as _time
        _t0 = _time.monotonic()
        logger.info("Sheets batch-fetch started for user=%s", google_id[:8])

        try:
            from .api.google_auth import credentials_from_dict
            from .api.google_sheets_client import (
                GoogleSheetsClient, PhysicalGoldService, FixedDepositsService,
            )
            from .api.fixed_deposits import calculate_current_value
            from .api.user_sheets import SHEET_CONFIGS

            creds = credentials_from_dict(creds_dict)
            client = GoogleSheetsClient(user_credentials=creds)

            # Ensure all manual tabs exist (single metadata call + create
            # any missing tabs) before the batch read.
            for stype in ("stocks", "etfs", "mutual_funds", "sips"):
                cfg = SHEET_CONFIGS[stype]
                client.ensure_sheet_tab(spreadsheet_id, cfg["sheet_name"], cfg["headers"])

            # All 6 sheet names to fetch.
            sheet_names = [
                "Gold", "FixedDeposits",
                *(SHEET_CONFIGS[st]["sheet_name"] for st in ("stocks", "etfs", "mutual_funds", "sips")),
            ]

            batch = client.batch_fetch_sheet_data_until_blank(spreadsheet_id, sheet_names)

            # ── Parse gold & FD using existing service parsers ──
            gold_svc = PhysicalGoldService(client)
            fd_svc = FixedDepositsService(client)
            gold = gold_svc._parse_batch_data(batch.get("Gold", []))
            deposits = calculate_current_value(
                fd_svc._parse_batch_data(batch.get("FixedDeposits", []))
            )

            # ── Parse manual entry tabs ──
            manual: dict = {}
            for sheet_type in ("stocks", "etfs", "mutual_funds", "sips"):
                cfg = SHEET_CONFIGS[sheet_type]
                raw = batch.get(cfg["sheet_name"], [])
                if not raw or len(raw) < 2:
                    manual[sheet_type] = []
                    continue
                fields = cfg["fields"]
                rows = []
                for idx, row in enumerate(raw[1:], start=2):
                    if not row or all(not v or str(v).strip() == "" for v in row):
                        break
                    entry = {"row_number": idx, "source": "manual"}
                    for fi, fname in enumerate(fields):
                        entry[fname] = row[fi] if fi < len(row) else ""
                    rows.append(entry)
                manual[sheet_type] = rows

            # Store everything in one atomic cache write.
            user_sheets_cache.put_all(
                google_id,
                physical_gold=gold,
                fixed_deposits=deposits,
                manual=manual,
            )
            _elapsed = _time.monotonic() - _t0
            manual_counts = {k: len(v) for k, v in manual.items() if v}
            logger.info(
                "Sheets batch-fetch done for user=%s in %.1fs: "
                "gold=%d fds=%d manual=%s",
                google_id[:8], _elapsed, len(gold), len(deposits), manual_counts,
            )
        except Exception:
            _elapsed = _time.monotonic() - _t0
            logger.exception(
                "Sheets batch-fetch FAILED for user=%s after %.1fs",
                google_id[:8], _elapsed,
            )

@app_ui.route("/api/auth/google/login", methods=["GET"])
def google_login():
    """Redirect to Google OAuth consent screen."""
    from .api.google_auth import build_oauth_flow

    try:
        redirect_uri = request.url_root.rstrip("/") + "/api/auth/google/callback"
        logger.info("OAuth login initiated from ip=%s redirect_uri=%s",
                    request.remote_addr, redirect_uri)
        flow = build_oauth_flow(redirect_uri)
        authorization_url, state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
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
        logger.info(
            "OAuth callback success: user=%s email=%s new_user=%s",
            google_id[:8], email, is_new_user,
        )

        user_doc = upsert_user(
            google_id=google_id,
            email=email,
            name=name,
            picture=picture,
            google_credentials=creds_dict,
            spreadsheet_id=spreadsheet_id,
        )

        if not spreadsheet_id:
            def _create_sheet_bg(creds, title, gid):
                try:
                    sid = create_portfolio_sheet(creds, title=title)
                    update_spreadsheet_id(gid, sid)
                    logger.info("Background sheet creation done for %s", gid)
                except Exception:
                    logger.exception("Background sheet creation failed for %s", gid)
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
    return jsonify({
        "authenticated": True,
        "email": user.get("email"),
        "name": user.get("name"),
        "picture": user.get("picture"),
        "spreadsheet_id": user.get("spreadsheet_id"),
    })


@app_ui.route("/api/auth/logout", methods=["POST"])
@app_only
def auth_logout():
    """Sign out the current user and clear PIN from memory."""
    user = _current_user()
    if user:
        gid = user.get("google_id", "")
        logger.info("User logout: user=%s", gid[:8])
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

    return jsonify({
        "has_pin": has_setup_pin,
        "has_zerodha_accounts": has_accounts,
        "pin_verified": pin_verified,
        "needs_pin": needs_pin,
    })


@app_ui.route("/api/pin/verify", methods=["POST"])
@protected_api
def pin_verify():
    """Verify the user's security PIN.  Stores PIN in memory on success."""
    user = _current_user()
    google_id = user["google_id"]

    # ── Rate-limit check ──
    allowed, retry_after = pin_rate_limiter.check(google_id)
    if not allowed:
        logger.warning(
            "PIN verify rate-limited: user=%s retry_after=%ds",
            google_id[:8], retry_after,
        )
        resp = jsonify({
            "error": "Too many failed attempts",
            "retry_after": retry_after,
            "locked": True,
        })
        resp.status_code = 429
        resp.headers["Retry-After"] = str(retry_after)
        return resp

    data = request.get_json(silent=True) or {}
    pin = (data.get("pin") or "").strip()

    if not pin or len(pin) != 6 or not pin.isalnum():
        logger.info("PIN verify: invalid format from user=%s", google_id[:8])
        return jsonify({"error": "PIN must be exactly 6 alphanumeric characters"}), 400

    if not verify_user_pin(google_id, pin):
        attempts, lockout_secs = pin_rate_limiter.record_failure(google_id)
        logger.warning(
            "PIN verify failed: user=%s attempts=%d lockout=%s",
            google_id[:8], attempts, f"{lockout_secs}s" if lockout_secs else "none",
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
    logger.info("PIN verified successfully: user=%s", google_id[:8])

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
        logger.warning("PIN setup rejected: user=%s already has PIN", google_id[:8])
        return jsonify({"error": "PIN already set. Use reset to change it."}), 409

    store_pin_check(google_id, pin)
    session_manager.set_pin(google_id, pin)
    session["pin_verified"] = True
    session.modified = True
    logger.info("PIN created for user=%s", google_id[:8])

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
    logger.info("PIN reset complete: user=%s (all Zerodha data wiped)", google_id[:8])

    return jsonify({"status": "reset_complete"})


@app_ui.route("/api/sse-token", methods=["GET"])
@protected_api
def sse_token():
    """Issue a short-lived signed token for direct Cloud Run SSE access.

    The token lets the browser open an EventSource directly to Cloud Run
    (bypassing Firebase Hosting CDN, which buffers streaming responses).
    """
    user = _current_user()
    google_id = user["google_id"]
    logger.debug("SSE token requested: user=%s", google_id[:8])
    token = _generate_sse_token(user["google_id"])
    resp = jsonify({"token": token, "ttl": SSE_TOKEN_MAX_AGE})
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app_ui.route("/api/callback", methods=["GET"])
def zerodha_callback():
    """Handle Zerodha KiteConnect OAuth callback."""
    req_token = request.args.get("request_token")
    if not req_token:
        logger.warning("Zerodha callback missing request_token")
        return render_template("callback_error.html")

    user = session.get("user")
    if not user or not user.get("google_id"):
        logger.warning("Zerodha callback without active session from ip=%s", request.remote_addr)
        return render_template("callback_error.html")

    google_id = user["google_id"]
    logger.info("Zerodha callback started: user=%s", google_id[:8])

    # PIN must be available to decrypt account credentials
    pin = session_manager.get_pin(google_id)
    if not pin:
        logger.warning("Zerodha callback: PIN not in memory for user=%s", google_id[:8])
        return render_template("callback_error.html")

    ensure_user_loaded(google_id)

    accounts = get_user_accounts(google_id)
    authenticated_account = None
    for acc in accounts:
        if session_manager.is_valid(google_id, acc["name"]):
            logger.debug("Zerodha callback: skipping already-valid account=%s", acc["name"])
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
            logger.warning("Zerodha callback: session generation failed for account=%s: %s",
                          acc["name"], e)
            continue

    if not authenticated_account:
        logger.warning("Zerodha callback: no account authenticated for user=%s (tried %d)",
                      google_id[:8], len(accounts))
        return render_template("callback_error.html")

    logger.info("Zerodha login succeeded: user=%s account=%s", google_id[:8], authenticated_account)

    # Immediately broadcast updated auth state so the banner hides right away
    broadcast_state_change(google_id)

    auth_accounts = [acc for acc in accounts if session_manager.is_valid(google_id, acc["name"])]
    if auth_accounts and not portfolio_cache.is_fetch_in_progress(google_id):
        from .fetchers import run_background_fetch
        run_background_fetch(google_id=google_id, accounts=auth_accounts)

    return render_template("callback_success.html")



@app_ui.route("/api/status", methods=["GET"])
@protected_api
def status():
    user = _current_user()
    google_id = user.get("google_id")
    response = jsonify(_build_status_response(google_id))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


@app_ui.route("/api/events", methods=["GET", "OPTIONS"])
def events():
    """SSE endpoint for real-time per-user status updates.

    Authentication:
    - Via ``__session`` cookie (requests through Firebase Hosting), OR
    - Via ``?token=`` query param (direct Cloud Run access — Firebase CDN
      buffers streaming responses so the browser connects directly).

    Production hardening:
    - Connection age limit prevents zombie connections on GCloud.
    - ``retry:`` field tells browsers the reconnect interval.
    - Handles BrokenPipeError / ConnectionResetError gracefully.
    - Returns 503 when client limits are exceeded.
    - Queue size is bounded to prevent memory bloat.
    """
    # CORS preflight for direct Cloud Run access from Firebase domain
    if request.method == "OPTIONS":
        resp = Response("", status=204)
        return _add_cors_headers(resp)

    import time as _time

    # --- Authenticate: session cookie OR signed token ---
    google_id = None
    user = _current_user()
    if user:
        google_id = user.get("google_id")
    else:
        token = request.args.get("token")
        if token:
            google_id = _validate_sse_token(token)

    if not google_id:
        logger.debug("SSE rejected: no auth (ip=%s)", request.remote_addr)
        resp = jsonify({"error": "Authentication required"})
        resp.status_code = 401
        return _add_cors_headers(resp)

    def event_stream():
        client_queue = Queue(maxsize=SSE_QUEUE_SIZE)
        accepted = sse_manager.add_client(client_queue, google_id)
        if not accepted:
            # Limit exceeded — yield an error event and stop.
            logger.warning("SSE rejected (limit): user=%s", google_id[:8])
            yield f"retry: {SSE_RETRY_MS}\ndata: {{\"error\": \"too_many_connections\"}}\n\n"
            return

        started = _time.monotonic()
        msg_count = 0
        try:
            # Send retry hint so browsers reconnect at a controlled interval
            yield f"retry: {SSE_RETRY_MS}\n"
            # Send initial state immediately
            yield f"data: {json.dumps(_build_status_response(google_id))}\n\n"
            msg_count += 1
            while True:
                # Enforce max connection age (GCloud / load balancer timeouts)
                elapsed = _time.monotonic() - started
                if elapsed >= SSE_MAX_CONNECTION_AGE:
                    logger.info(
                        "SSE connection aged out: user=%s duration=%ds messages=%d",
                        google_id[:8], int(elapsed), msg_count,
                    )
                    # Send a reconnect hint before closing
                    yield f"data: {{\"reconnect\": true}}\n\n"
                    break

                try:
                    message = client_queue.get(timeout=SSE_KEEPALIVE_INTERVAL)
                    if message is EVICT_SENTINEL:
                        logger.info(
                            "SSE connection evicted: user=%s duration=%ds messages=%d",
                            google_id[:8], int(_time.monotonic() - started), msg_count,
                        )
                        # Tell client to reconnect immediately
                        yield f"data: {{\"reconnect\": true}}\n\n"
                        break
                    yield f"data: {message}\n\n"
                    msg_count += 1
                except Empty:
                    # SSE keepalive comment to prevent proxy/LB idle timeouts
                    yield ": keepalive\n\n"
        except GeneratorExit:
            # Client disconnected normally
            duration = int(_time.monotonic() - started)
            logger.info("SSE client disconnected: user=%s duration=%ds messages=%d",
                       google_id[:8], duration, msg_count)
        except (BrokenPipeError, ConnectionResetError, OSError):
            # Client disconnected abnormally (common in production)
            duration = int(_time.monotonic() - started)
            logger.info("SSE broken pipe: user=%s duration=%ds messages=%d",
                       google_id[:8], duration, msg_count)
        except Exception:
            logger.exception("SSE unexpected error: user=%s", google_id[:8])
        finally:
            sse_manager.remove_client(client_queue, google_id)

    resp = Response(event_stream(), mimetype='text/event-stream', headers={
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',              # HTTP/1.0 compat
        'X-Accel-Buffering': 'no',         # nginx / reverse proxies
        'X-Content-Type-Options': 'nosniff',
        'Connection': 'keep-alive',
        'Referrer-Policy': 'no-referrer',  # prevent token leaking via Referer header
    })
    return _add_cors_headers(resp)


def _build_stocks_data(user):
    """Build merged broker + manual stocks list with live LTPs."""
    user_data = portfolio_cache.get(user["google_id"])
    broker_stocks = list(user_data.stocks)

    manual_entries = []
    for sheet_type in ("stocks", "etfs"):
        manual = _fetch_manual_entries(user, sheet_type)
        for m in manual:
            qty = float(m.get("qty") or 0)
            avg = float(m.get("avg_price") or 0)
            manual_entries.append({
                "tradingsymbol": (m.get("symbol") or "").upper(),
                "quantity": qty,
                "average_price": avg,
                "last_price": avg,          # fallback; enriched below
                "invested": qty * avg,
                "exchange": m.get("exchange", "NSE"),
                "account": m.get("account", "Manual"),
                "day_change": 0,
                "day_change_percentage": 0,
                "isin": "",
                "source": "manual",
                "row_number": m.get("row_number"),
                "manual_type": sheet_type,
            })

    if manual_entries:
        _enrich_manual_entries_with_ltp(manual_entries)

    broker_stocks.extend(manual_entries)
    return sorted(broker_stocks, key=lambda x: x.get("tradingsymbol", ""))


def _validate_nse_symbol(symbol: str) -> dict | None:
    """Validate a symbol by fetching its quote via Yahoo Finance.

    Returns the quote dict (with 'ltp' > 0) if valid, or None if the
    symbol does not exist or the fetch fails.
    """
    from .api.market_data import MarketDataClient

    try:
        client = MarketDataClient()
        data = client.fetch_stock_quote(symbol)
        if data and data.get("ltp"):
            return data
    except Exception:
        logger.warning("Symbol validation failed for %s", symbol)
    return None


def _fetch_uncached_manual_ltps(user: dict, new_symbol: str = "") -> None:
    """Fetch LTPs for all uncached manual stock/ETF symbols after a CRUD add.

    Collects symbols from both stocks and etfs sheets, adds the newly-added
    symbol, then batch-fetches any that aren't already in the LTP cache.
    """
    try:
        from .api.market_data import MarketDataClient

        all_symbols: set[str] = set()
        for sheet_type in ("stocks", "etfs"):
            for entry in (_fetch_manual_entries(user, sheet_type) or []):
                sym = (entry.get("symbol") or "").upper()
                if sym:
                    all_symbols.add(sym)
        if new_symbol:
            all_symbols.add(new_symbol)

        to_fetch = [s for s in all_symbols
                    if not manual_ltp_cache.get(s)
                    and not manual_ltp_cache.is_negative(s)]
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
    """Build merged broker + manual mutual fund holdings list."""
    user_data = portfolio_cache.get(user["google_id"])
    broker_mf = list(user_data.mf_holdings)

    manual = _fetch_manual_entries(user, "mutual_funds")
    for m in manual:
        qty = float(m.get("qty") or 0)
        avg = float(m.get("avg_nav") or 0)
        broker_mf.append({
            "fund": (m.get("fund") or "").upper(),
            "tradingsymbol": (m.get("fund") or "").upper(),
            "quantity": qty,
            "average_price": avg,
            "last_price": avg,
            "invested": qty * avg,
            "account": m.get("account", "Manual"),
            "last_price_date": None,
            "source": "manual",
            "row_number": m.get("row_number"),
        })
    return sorted(broker_mf, key=lambda x: x.get("fund", ""))


def _build_sips_data(user):
    """Build merged broker + manual SIPs list."""
    user_data = portfolio_cache.get(user["google_id"])
    broker_sips = list(user_data.sips)

    manual = _fetch_manual_entries(user, "sips")
    for m in manual:
        broker_sips.append({
            "fund": (m.get("fund") or "").upper(),
            "tradingsymbol": (m.get("fund") or "").upper(),
            "instalment_amount": float(m.get("amount") or 0),
            "frequency": m.get("frequency", "MONTHLY"),
            "instalments": int(m.get("installments") or -1),
            "completed_instalments": int(m.get("completed") or 0),
            "status": (m.get("status") or "ACTIVE").upper(),
            "next_instalment": m.get("next_due", ""),
            "account": m.get("account", "Manual"),
            "source": "manual",
            "row_number": m.get("row_number"),
        })
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
    user = _current_user()
    return _json_response(_build_stocks_data(user))


@app_ui.route("/api/mf_holdings_data", methods=["GET"])
@pin_required
def mf_holdings_data():
    user = _current_user()
    return _json_response(_build_mf_data(user))


@app_ui.route("/api/sips_data", methods=["GET"])
@pin_required
def sips_data():
    user = _current_user()
    return _json_response(_build_sips_data(user))


@app_ui.route("/api/nifty50_data", methods=["GET"])
@app_only
def nifty50_data():
    return _json_response(market_cache.nifty50, sort_key="symbol")


@app_ui.route("/api/physical_gold_data", methods=["GET"])
@pin_required
def physical_gold_data():
    user = _current_user()
    return _json_response(_build_gold_data(user))


@app_ui.route("/api/fixed_deposits_data", methods=["GET"])
@pin_required
def fixed_deposits_data():
    user = _current_user()
    return _json_response(_build_fd_data(user))


@app_ui.route("/api/all_data", methods=["GET"])
@pin_required
def all_data():
    """Return all portfolio data in a single response.

    Replaces the need for 6 separate endpoint calls from the frontend.
    The backend batch-fetches all Google Sheets tabs in one API call,
    then assembles and returns the combined payload.
    """
    import time as _t
    _t0 = _t.monotonic()
    user = _current_user()
    google_id = user["google_id"]

    # Pre-populate the sheets cache (single batchGet) so the
    # individual _build_*_data helpers all hit cache.
    _prefetch_all_user_sheets(user)

    payload = {
        "stocks": _build_stocks_data(user),
        "mfHoldings": _build_mf_data(user),
        "sips": _build_sips_data(user),
        "physicalGold": _build_gold_data(user),
        "fixedDeposits": _build_fd_data(user),
        "status": _build_status_response(google_id),
    }
    _elapsed = _t.monotonic() - _t0
    logger.info(
        "all_data served: user=%s in %.2fs stocks=%d mf=%d sips=%d gold=%d fd=%d",
        google_id[:8], _elapsed,
        len(payload["stocks"]), len(payload["mfHoldings"]),
        len(payload["sips"]), len(payload["physicalGold"]),
        len(payload["fixedDeposits"]),
    )

    resp = jsonify(payload)
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp


@app_ui.route("/api/fd_summary_data", methods=["GET"])
@pin_required
def fd_summary_data():
    return _json_response([])


@app_ui.route("/api/market_indices", methods=["GET"])
@app_only
def market_indices():
    from datetime import datetime, timedelta
    from .api.market_data import MarketDataClient

    if (market_cache.market_indices and market_cache.market_indices_last_fetch and
            datetime.now() - market_cache.market_indices_last_fetch < timedelta(seconds=MARKET_INDEX_CACHE_TTL)):
        response = jsonify(market_cache.market_indices)
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return response

    client = MarketDataClient()
    data = client.fetch_market_indices()
    market_cache.market_indices = data
    market_cache.market_indices_last_fetch = datetime.now()

    response = jsonify(data)
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


@app_ui.route("/api/refresh", methods=["POST"])
@pin_required
def refresh_route():
    """Trigger manual data refresh for the signed-in user."""
    from .fetchers import run_background_fetch, collect_manual_symbols

    user = _current_user()
    google_id = user["google_id"]

    if portfolio_cache.is_fetch_in_progress(google_id):
        logger.info("Manual refresh rejected: already in progress for user=%s", google_id[:8])
        return make_response(jsonify({"error": "Fetch already in progress"}), HTTP_CONFLICT)

    ensure_user_loaded(google_id)

    # Collect symbols before invalidation (cache will be cleared)
    manual_symbols = collect_manual_symbols(google_id)

    user_sheets_cache.invalidate(google_id)
    manual_ltp_cache.invalidate()

    authenticated = get_authenticated_accounts(google_id)
    logger.info(
        "Manual refresh started: user=%s accounts=%d manual_symbols=%d",
        google_id[:8], len(authenticated), len(manual_symbols),
    )
    run_background_fetch(
        is_manual=True, accounts=authenticated, google_id=google_id,
        manual_symbols=manual_symbols,
    )

    return make_response(jsonify({"status": "started"}), HTTP_ACCEPTED)


@app_ui.route("/", methods=["GET"])
def portfolio_page():
    """Serve landing page or portfolio dashboard with inlined data.

    For return visits with warm caches the page is rendered with inlined
    data (zero JS round-trips).  For first login or cold caches the page
    is rendered immediately with empty data and the frontend fetches
    asynchronously via SSE + ``/api/all_data``.
    """
    user = _current_user()
    if not user:
        return render_template("landing.html")

    google_id = user.get("google_id", "")
    pin_verified = session.get("pin_verified", False)

    # Only kick off background fetches if PIN is already verified
    # (return visit with session cookie).  For first login / unverified
    # sessions the frontend shows the PIN overlay first, and the
    # pin_verify / pin_setup endpoints trigger the load afterward.
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

    # Only inject SSE direct config when the page is served through Firebase
    # Hosting (where the CDN buffers streaming responses).  When browsing
    # Cloud Run directly, relative /events works fine with session cookies.
    sse_base_url = CLOUD_RUN_URL if _is_firebase_hosting_request() else ""

    from .firebase_store import has_pin as _has_pin
    user_has_pin = _has_pin(google_id)

    logger.info(
        "portfolio_page: user=%s pin_verified=%s inlined=%s has_pin=%s",
        google_id[:8], pin_verified, initial_data is not None, user_has_pin,
    )

    return render_template(
        "portfolio.html",
        physical_gold_enabled=True,
        fixed_deposits_enabled=True,
        user=user,
        initial_data_json=json.dumps(initial_data, default=str) if initial_data else None,
        sse_base_url=sse_base_url,
        table_row_limit=PORTFOLIO_TABLE_ROW_LIMIT,
        pin_verified=session.get("pin_verified", False),
        has_pin=user_has_pin,
    )


# ---------------------------------------------------------------------------
# Standalone table detail page (full table view with pagination)
# ---------------------------------------------------------------------------
# Valid table keys — prevents arbitrary template injection
_VALID_TABLE_KEYS = frozenset({
    "stocks", "etfs", "mutual-funds", "physical-gold",
    "fixed-deposits", "sips",
})

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
    google_id = user.get("google_id", "") if user else ""
    sse_base_url = CLOUD_RUN_URL if _is_firebase_hosting_request() else ""

    return render_template(
        "table_detail.html",
        table_key=table_key,
        table_title=_TABLE_DISPLAY_NAMES.get(table_key, table_key.replace("-", " ").title()),
        user=user,
        sse_base_url=sse_base_url,
    )


@app_ui.route("/nifty50", methods=["GET"])
def nifty50_page():
    """Serve the Nifty 50 stocks page."""
    user = _current_user()
    return render_template("nifty50.html", user=user)


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
    logger.info("remove_zerodha: user=%s account=%s (session+cache cleared)", google_id[:8], account_name)

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
    "etfs": "stocks",           # ETFs merge into the stocks table
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
        from .api.google_sheets_client import FixedDepositsService
        from .api.fixed_deposits import calculate_current_value
        svc = FixedDepositsService(client)
        parsed = calculate_current_value(svc._parse_batch_data(raw))
        user_sheets_cache.put(google_id, fixed_deposits=parsed)

    else:
        # Manual types: stocks, etfs, mutual_funds, sips
        rows = []
        if raw and len(raw) >= 2:
            fields = cfg["fields"]
            for idx, row in enumerate(raw[1:], start=2):
                if not row or all(not v or str(v).strip() == "" for v in row):
                    break
                entry = {"row_number": idx, "source": "manual"}
                for fi, fname in enumerate(fields):
                    entry[fname] = row[fi] if fi < len(row) else ""
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
        logger.exception("Error listing %s", sheet_type)
        return jsonify({"error": str(e)}), 500

    if not raw or len(raw) < 2:
        return jsonify([])

    fields = cfg["fields"]
    rows = []
    for idx, row in enumerate(raw[1:], start=2):
        if not row or all(not v or str(v).strip() == "" for v in row):
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
    if sheet_type in ("stocks", "etfs") and symbol:
        quote = _validate_nse_symbol(symbol)
        if not quote:
            return jsonify({"error": f"Symbol {symbol} doesn't exist on exchange."}), 400
        # Cache the validated LTP immediately.
        manual_ltp_cache.put(symbol, quote)

    values = [data.get(f, "") for f in cfg["fields"]]

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
        logger.exception("Error adding %s row", sheet_type)
        return jsonify({"error": str(e)}), 500

    logger.info("sheets_add: user=%s type=%s row=%d", google_id[:8], sheet_type, row_num)
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
    if sheet_type in ("stocks", "etfs") and symbol:
        quote = _validate_nse_symbol(symbol)
        if not quote:
            return jsonify({"error": f"Symbol {symbol} doesn't exist on exchange."}), 400
        manual_ltp_cache.put(symbol, quote)

    values = [data.get(f, "") for f in cfg["fields"]]

    try:
        client.update_row(spreadsheet_id, cfg["sheet_name"], row_number, values)
        user = _current_user()
        google_id = user.get("google_id", "")
        _refresh_single_sheet_cache(client, spreadsheet_id, google_id, sheet_type)
    except Exception as e:
        logger.exception("Error updating %s row %d", sheet_type, row_number)
        return jsonify({"error": str(e)}), 500

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
        logger.exception("Error deleting %s row %d", sheet_type, row_number)
        return jsonify({"error": str(e)}), 500

    result = {"status": "deleted"}
    refreshed = _build_data_for_type(user, sheet_type)
    if refreshed:
        result["data"] = refreshed
    return jsonify(result)
