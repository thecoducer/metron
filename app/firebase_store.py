"""Firestore user store – persists per-user profile, OAuth tokens, and sheet IDs."""

import os
from datetime import datetime, timezone
from typing import Any, Optional

from google.api_core import exceptions as gcp_exceptions

from .logging_config import logger

_firestore_client = None

_CREDENTIALS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "config", "firebase-credentials.json"
)
_DATABASE_ID = "investment-portfolio-tracker"
_USERS = "users"


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

    if not os.path.exists(_CREDENTIALS_PATH):
        raise FileNotFoundError(
            f"Firebase credentials not found at {_CREDENTIALS_PATH}. "
            "Download your service-account JSON from the Firebase Console."
        )

    if not firebase_admin._apps:
        firebase_admin.initialize_app(
            fb_credentials.Certificate(_CREDENTIALS_PATH)
        )

    app = firebase_admin.get_app()
    _firestore_client = gc_firestore.Client(
        project=app.project_id,
        credentials=app.credential.get_credential(),
        database=_DATABASE_ID,
    )
    logger.info("Firestore client initialised (db=%s)", _DATABASE_ID)
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
    """Add a Zerodha account to the user's list of connected accounts."""
    ref = _user_ref(google_id)
    doc = ref.get()
    data = doc.to_dict() if doc.exists else {}
    accounts: list[dict] = data.get("zerodha_accounts", [])

    # Migrate legacy single-key fields if present
    if not accounts and data.get("zerodha_api_key"):
        accounts.append({
            "account_name": "Primary",
            "api_key": data["zerodha_api_key"],
            "api_secret": data.get("zerodha_api_secret", ""),
        })

    # Prevent duplicate account names
    if any(a["account_name"] == account_name for a in accounts):
        raise ValueError(f"Account '{account_name}' already exists")

    accounts.append({
        "account_name": account_name,
        "api_key": api_key,
        "api_secret": api_secret,
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

    # Migrate legacy single-key fields if present
    if not accounts and data.get("zerodha_api_key"):
        return ["Primary"]

    return [a["account_name"] for a in accounts]


def get_zerodha_accounts(google_id: str) -> list[dict]:
    """Return the user's Zerodha accounts in auth-compatible format.

    Each dict has keys: ``name``, ``api_key``, ``api_secret``.
    """
    doc = _user_ref(google_id).get()
    data = doc.to_dict() if doc.exists else {}
    accounts: list[dict] = data.get("zerodha_accounts", [])

    # Migrate legacy single-key fields if present
    if not accounts and data.get("zerodha_api_key"):
        accounts = [{
            "account_name": "Primary",
            "api_key": data["zerodha_api_key"],
            "api_secret": data.get("zerodha_api_secret", ""),
        }]

    return [
        {
            "name": a["account_name"],
            "api_key": a["api_key"],
            "api_secret": a["api_secret"],
        }
        for a in accounts
    ]


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
