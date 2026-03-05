"""API security middleware for the Metron application.

Decorators
----------
- ``login_required``  – rejects unauthenticated requests (401).
- ``app_only``        – rejects requests not originating from the app UI (403).
- ``protected_api``   – combines both (auth first, then origin).

Origin detection uses two signals:
1. Custom header ``X-Requested-With: MetronApp`` set by frontend fetch calls.
2. Browser-supplied ``Sec-Fetch-Mode``; ``navigate`` = address-bar / link
   (blocked), ``cors`` / ``same-origin`` = programmatic (allowed).

The feature flag ``features.allow_browser_api_access`` in ``config/config.json``
bypasses the origin check for local debugging.  Must remain ``false`` in
production.
"""

import functools

from flask import jsonify, request, session

from .config import app_config
from .logging_config import logger

APP_REQUEST_HEADER = "X-Requested-With"
APP_REQUEST_HEADER_VALUE = "MetronApp"
_PROGRAMMATIC_FETCH_MODES = frozenset({"cors", "same-origin", "no-cors"})


def _is_authenticated():
    """Return ``True`` when a signed-in user is present in the session."""
    return session.get("user") is not None


def _is_app_request():
    """Return ``True`` when the request originates from the app frontend."""
    if request.headers.get(APP_REQUEST_HEADER) == APP_REQUEST_HEADER_VALUE:
        return True
    return request.headers.get("Sec-Fetch-Mode", "") in _PROGRAMMATIC_FETCH_MODES


def _allow_browser_api_access():
    """Return ``True`` when the debug feature flag is enabled in config."""
    return app_config.features.get("allow_browser_api_access", False)


def _deny_non_app_request():
    """If the request did not originate from the app, return a 403 response.

    Returns ``None`` when the request is allowed through.
    """
    if _allow_browser_api_access() or _is_app_request():
        return None
    logger.warning(
        "Blocked direct API access: %s %s from %s",
        request.method,
        request.path,
        request.remote_addr,
    )
    return jsonify({"error": "Forbidden"}), 403


def login_required(f):
    """Reject unauthenticated requests with 401."""

    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not _is_authenticated():
            logger.debug("login_required: rejected %s %s", request.method, request.path)
            return jsonify({"error": "Authentication required"}), 401
        return f(*args, **kwargs)

    return decorated_function


def app_only(f):
    """Reject requests that did not originate from the application frontend."""

    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        denied = _deny_non_app_request()
        if denied:
            return denied
        return f(*args, **kwargs)

    return decorated_function


def protected_api(f):
    """Require authentication *and* app-origin verification."""

    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not _is_authenticated():
            return jsonify({"error": "Authentication required"}), 401
        denied = _deny_non_app_request()
        if denied:
            return denied
        return f(*args, **kwargs)

    return decorated_function


def pin_required(f):
    """Require authentication, app-origin, *and* a verified security PIN.

    Returns a JSON ``{"error": "pin_required"}`` with status 403 when the
    user hasn't entered their PIN yet.  The frontend uses this to show the
    PIN overlay.

    Also verifies that the user's PIN is still held in server memory
    (it is lost on server restart).  If the session cookie says
    ``pin_verified`` but the in-memory PIN is gone, the session flag is
    cleared so the frontend will re-prompt for the PIN.
    """

    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not _is_authenticated():
            logger.debug("pin_required: auth rejected %s %s", request.method, request.path)
            return jsonify({"error": "Authentication required"}), 401
        denied = _deny_non_app_request()
        if denied:
            return denied
        if not session.get("pin_verified"):
            logger.debug("pin_required: PIN not verified for %s %s", request.method, request.path)
            return jsonify({"error": "pin_required"}), 403

        # Ensure the PIN is still in server memory (lost on restart).
        from .services import session_manager
        user = session.get("user")
        if user:
            google_id = user.get("google_id", "")
            if google_id and not session_manager.get_pin(google_id):
                logger.info(
                    "pin_required: in-memory PIN lost for %s %s — clearing session flag",
                    request.method, request.path,
                )
                session["pin_verified"] = False
                session.modified = True
                return jsonify({"error": "pin_required"}), 403

        return f(*args, **kwargs)

    return decorated_function
