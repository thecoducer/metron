"""Firestore user store – persists per-user profile, OAuth tokens, and sheet IDs.

Credential resolution order:
1. ``FIREBASE_CREDENTIALS`` env var — JSON string of service-account key.
2. ``GOOGLE_APPLICATION_CREDENTIALS`` env var — path to a JSON key file
   (set automatically on Cloud Run when a service account is attached).
3. Local file at ``config/firebase-credentials.json`` (development fallback).
4. Application Default Credentials (Cloud Run's built-in service identity).
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Optional

from google.api_core import exceptions as gcp_exceptions

from .logging_config import logger
from .utils import decrypt_credential, encrypt_credential

_firestore_client = None

_LOCAL_CREDENTIALS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "config", "firebase-credentials.json"
)
_USERS = "users"


def _resolve_firebase_credential():
    """Resolve Firebase credentials from env vars or local file.

    Returns a ``firebase_admin.credentials.Base`` instance, or ``None``
    to fall back to Application Default Credentials.
    """
    from firebase_admin import credentials as fb_credentials

    # 1. JSON string in env var (ideal for Cloud Run secrets)
    creds_json = os.environ.get("FIREBASE_CREDENTIALS")
    if creds_json:
        try:
            info = json.loads(creds_json)
            logger.info("Using Firebase credentials from FIREBASE_CREDENTIALS env var")
            return fb_credentials.Certificate(info)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error("Invalid FIREBASE_CREDENTIALS JSON: %s", exc)

    # 2. GOOGLE_APPLICATION_CREDENTIALS points to a file
    gac = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if gac and os.path.exists(gac):
        logger.info("Using Firebase credentials from GOOGLE_APPLICATION_CREDENTIALS")
        return fb_credentials.Certificate(gac)

    # 3. Local file (development)
    if os.path.exists(_LOCAL_CREDENTIALS_PATH):
        logger.info("Using Firebase credentials from %s", _LOCAL_CREDENTIALS_PATH)
        return fb_credentials.Certificate(_LOCAL_CREDENTIALS_PATH)

    # 4. Fall back to ADC (works on Cloud Run with an attached service account)
    logger.info("Using Application Default Credentials for Firebase")
    return fb_credentials.ApplicationDefault()


def _db():
    """Return the Firestore client, lazily initialising on first call."""
    global _firestore_client
    if _firestore_client is not None:
        return _firestore_client

    try:
        import firebase_admin
        from firebase_admin import credentials as fb_credentials
        from google.cloud import firestore as gc_firestore
    except ImportError as exc:
        raise RuntimeError(
            "firebase-admin is not installed. Run: pip install firebase-admin"
        ) from exc

    if not firebase_admin._apps:
        cred = _resolve_firebase_credential()
        firebase_admin.initialize_app(cred)

    app = firebase_admin.get_app()
    _firestore_client = gc_firestore.Client(
        project=app.project_id,
        credentials=app.credential.get_credential(),
    )
    logger.info("Firestore client initialised with project %s", app.project_id)
    return _firestore_client


def _user_ref(google_id: str):
    """Return a Firestore document reference for the given user."""
    return _db().collection(_USERS).document(google_id)


def get_user(google_id: str) -> Optional[dict[str, Any]]:
    """Return the user dict, or None if not found."""
    try:
        doc = _user_ref(google_id).get()
        return doc.to_dict() if doc.exists else None
    except gcp_exceptions.GoogleAPICallError:
        logger.exception("Firestore read failed for user %s", google_id)
        raise


def upsert_user(
    google_id: str,
    email: str,
    name: str,
    picture: str,
    google_credentials: dict,
    spreadsheet_id: Optional[str] = None,
) -> dict[str, Any]:
    """Create or update a user record. Returns the saved document."""
    ref = _user_ref(google_id)
    now = datetime.now(timezone.utc).isoformat()

    data: dict[str, Any] = {
        "google_id": google_id,
        "email": email,
        "name": name,
        "picture": picture,
        "google_credentials": google_credentials,
        "last_login": now,
    }

    doc = ref.get()
    if doc.exists:
        if spreadsheet_id:
            data["spreadsheet_id"] = spreadsheet_id
        ref.update(data)
        logger.info("Updated user %s (%s)", google_id, email)
    else:
        data.update({"spreadsheet_id": spreadsheet_id or "", "created_at": now})
        ref.set(data)
        logger.info("Created user %s (%s)", google_id, email)

    return ref.get().to_dict()


def update_spreadsheet_id(google_id: str, spreadsheet_id: str) -> None:
    """Persist the user's portfolio spreadsheet ID."""
    _user_ref(google_id).update({"spreadsheet_id": spreadsheet_id})
    logger.info("Stored spreadsheet_id for user %s", google_id)


def update_google_credentials(google_id: str, google_credentials: dict) -> None:
    """Persist refreshed Google OAuth credentials."""
    _user_ref(google_id).update({"google_credentials": google_credentials})


def add_zerodha_account(
    google_id: str, account_name: str, api_key: str, api_secret: str
) -> None:
    """Add a Zerodha account to the user's list of connected accounts.

    The *api_key* and *api_secret* are encrypted at rest with a per-user
    Fernet key before being persisted to Firestore.
    """
    ref = _user_ref(google_id)
    doc = ref.get()
    data = doc.to_dict() if doc.exists else {}
    accounts: list[dict] = data.get("zerodha_accounts", [])

    # Prevent duplicate account names
    if any(a["account_name"] == account_name for a in accounts):
        raise ValueError(f"Account '{account_name}' already exists")

    accounts.append({
        "account_name": account_name,
        "api_key": encrypt_credential(api_key, google_id),
        "api_secret": encrypt_credential(api_secret, google_id),
    })
    ref.update({"zerodha_accounts": accounts})
    logger.info("Added Zerodha account '%s' for user %s", account_name, google_id)


def remove_zerodha_account(google_id: str, account_name: str) -> None:
    """Remove a Zerodha account by name from the user's list."""
    ref = _user_ref(google_id)
    doc = ref.get()
    data = doc.to_dict() if doc.exists else {}
    accounts: list[dict] = data.get("zerodha_accounts", [])

    updated = [a for a in accounts if a["account_name"] != account_name]
    if len(updated) == len(accounts):
        raise ValueError(f"Account '{account_name}' not found")

    ref.update({"zerodha_accounts": updated})
    logger.info("Removed Zerodha account '%s' for user %s", account_name, google_id)


def get_zerodha_account_names(google_id: str) -> list[str]:
    """Return the names of the user's connected Zerodha accounts (no secrets)."""
    doc = _user_ref(google_id).get()
    data = doc.to_dict() if doc.exists else {}
    accounts: list[dict] = data.get("zerodha_accounts", [])
    return [a["account_name"] for a in accounts]


def get_zerodha_accounts(google_id: str) -> list[dict]:
    """Return the user's Zerodha accounts in auth-compatible format.

    Each dict has keys: ``name``, ``api_key``, ``api_secret``.
    Credentials are decrypted with the user's per-user Fernet key.
    Accounts whose credentials cannot be decrypted are skipped with a
    warning — the user must re-add them via the UI.
    """
    doc = _user_ref(google_id).get()
    data = doc.to_dict() if doc.exists else {}
    accounts: list[dict] = data.get("zerodha_accounts", [])

    result: list[dict] = []
    for a in accounts:
        try:
            result.append({
                "name": a["account_name"],
                "api_key": decrypt_credential(a["api_key"], google_id),
                "api_secret": decrypt_credential(a["api_secret"], google_id),
            })
        except Exception:
            logger.warning(
                "Failed to decrypt credentials for account '%s' of user %s "
                "— please re-add the account via Settings",
                a["account_name"], google_id,
            )
    return result


# --------------------------
# ZERODHA SESSION TOKENS
# --------------------------


def get_zerodha_sessions(google_id: str) -> dict[str, dict]:
    """Return encrypted Zerodha session tokens for a user.

    Returns a dict mapping account name → {"access_token": ..., "expiry": ...}.
    """
    doc = _user_ref(google_id).get()
    data = doc.to_dict() if doc.exists else {}
    return data.get("zerodha_sessions", {})


def save_zerodha_sessions(google_id: str, sessions: dict[str, dict]) -> None:
    """Persist encrypted Zerodha session tokens for a user.

    Args:
        google_id: The user's Google ID.
        sessions: Dict mapping account name → {"access_token": ..., "expiry": ...}.
    """
    _user_ref(google_id).update({"zerodha_sessions": sessions})


def clear_zerodha_sessions(google_id: str) -> None:
    """Remove all stored Zerodha session tokens for a user."""
    from google.cloud.firestore_v1 import DELETE_FIELD
    _user_ref(google_id).update({"zerodha_sessions": DELETE_FIELD})
