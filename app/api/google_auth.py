"""
Google OAuth 2.0 authentication for end users.

Handles the OAuth flow so each user can grant the app permission
to create/read spreadsheets in *their* Google Drive.
"""

import os
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from ..logging_config import logger

# ---------------------------------------------------------------------------
# Scopes required for per‑user spreadsheet management
# ---------------------------------------------------------------------------
USER_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/drive.file",
]


_LOCAL_CLIENT_SECRETS = Path(__file__).resolve().parent.parent.parent / "config" / "google-oauth-credentials.json"


def _get_client_config() -> dict:
    """Resolve Google OAuth client config from env var or local file.

    Resolution order:
    1. ``GOOGLE_OAUTH_CREDENTIALS`` env var — JSON string of client secrets.
    2. Local file at ``config/google-oauth-credentials.json``.
    """
    import json as _json

    # 1. Env var (ideal for Cloud Run secrets)
    env_json = os.environ.get("GOOGLE_OAUTH_CREDENTIALS")
    if env_json:
        try:
            return _json.loads(env_json)
        except _json.JSONDecodeError as exc:
            raise ValueError(f"GOOGLE_OAUTH_CREDENTIALS env var contains invalid JSON: {exc}") from exc

    # 2. Local file
    if os.path.exists(_LOCAL_CLIENT_SECRETS):
        with open(_LOCAL_CLIENT_SECRETS) as fh:
            return _json.load(fh)

    raise FileNotFoundError(
        "Google OAuth client secrets not found. Either set the "
        "GOOGLE_OAUTH_CREDENTIALS env var with the JSON content, or place "
        f"the file at {_LOCAL_CLIENT_SECRETS}."
    )


def build_oauth_flow(redirect_uri: str) -> Flow:
    """Create a Google OAuth 2.0 :class:`Flow` for user sign‑in.

    Args:
        redirect_uri: The OAuth callback URL registered in Google Cloud Console.

    Returns:
        An initialised :class:`google_auth_oauthlib.flow.Flow`.
    """
    client_config = _get_client_config()

    flow = Flow.from_client_config(
        client_config,
        scopes=USER_SCOPES,
        redirect_uri=redirect_uri,
    )
    return flow


def exchange_code_for_credentials(code: str, redirect_uri: str) -> Credentials:
    """Exchange an authorization code for user credentials.

    Args:
        code: The authorization code returned by Google.
        redirect_uri: The same redirect URI used when the flow was started.

    Returns:
        A :class:`google.oauth2.credentials.Credentials` object with
        access token, refresh token, scopes, etc.
    """
    flow = build_oauth_flow(redirect_uri)
    # Allow Google to return fewer scopes than requested (e.g. user
    # unchecked optional scopes on the consent screen).
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
    flow.fetch_token(code=code)
    return flow.credentials  # type: ignore[return-value]


def credentials_from_dict(data: dict) -> Credentials:
    """Re‑hydrate a :class:`Credentials` object from a serialised dict.

    The dict is the format stored in Firebase (token, refresh_token, etc.).
    """
    from datetime import datetime

    expiry = None
    raw_expiry = data.get("expiry")
    if raw_expiry:
        try:
            expiry = datetime.fromisoformat(raw_expiry)
            if expiry.tzinfo is not None:
                expiry = expiry.replace(tzinfo=None)
        except (ValueError, TypeError):
            pass

    return Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=data.get("client_id"),
        client_secret=data.get("client_secret"),
        scopes=data.get("scopes", USER_SCOPES),
        expiry=expiry,
    )


def credentials_to_dict(creds: Credentials) -> dict:
    """Serialise a :class:`Credentials` object to a plain dict for storage."""
    d = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else USER_SCOPES,
    }
    if creds.expiry:
        d["expiry"] = creds.expiry.isoformat()
    return d


def persist_refreshed_credentials(creds: Credentials, google_id: str) -> None:
    """If the library auto-refreshed the token, persist the new credentials."""
    if not creds.token or not google_id:
        return
    try:
        from ..firebase_store import update_google_credentials

        update_google_credentials(google_id, credentials_to_dict(creds))
        logger.debug("Persisted refreshed Google credentials for %s", google_id[:8])
    except Exception:
        logger.warning("Failed to persist refreshed credentials for %s", google_id[:8])


def get_user_info(credentials: Credentials) -> dict:
    """Fetch basic profile information for the authenticated user.

    Returns:
        Dict with ``id``, ``email``, ``name``, ``picture``.
    """
    from googleapiclient.discovery import build as google_build

    service = google_build("oauth2", "v2", credentials=credentials, static_discovery=True)
    user_info = service.userinfo().get().execute()
    return {
        "id": user_info.get("id"),
        "email": user_info.get("email"),
        "name": user_info.get("name"),
        "picture": user_info.get("picture"),
    }
