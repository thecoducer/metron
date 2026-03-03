"""
Google OAuth 2.0 authentication for end users.

Handles the OAuth flow so each user can grant the app permission
to create/read spreadsheets in *their* Google Drive.
"""

import os

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


def _get_client_secrets_file() -> str:
    """Return the path to the Google OAuth client‑secrets JSON file."""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    return os.path.join(base_dir, "config", "google-oauth-credentials.json")


def build_oauth_flow(redirect_uri: str) -> Flow:
    """Create a Google OAuth 2.0 :class:`Flow` for user sign‑in.

    Args:
        redirect_uri: The OAuth callback URL registered in Google Cloud Console.

    Returns:
        An initialised :class:`google_auth_oauthlib.flow.Flow`.
    """
    client_secrets = _get_client_secrets_file()
    if not os.path.exists(client_secrets):
        raise FileNotFoundError(
            f"Google OAuth client‑secrets file not found at {client_secrets}. "
            "Download it from the Google Cloud Console → APIs & Services → Credentials."
        )

    flow = Flow.from_client_secrets_file(
        client_secrets,
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
    return flow.credentials


def credentials_from_dict(data: dict) -> Credentials:
    """Re‑hydrate a :class:`Credentials` object from a serialised dict.

    The dict is the format stored in Firebase (token, refresh_token, etc.).
    """
    return Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=data.get("client_id"),
        client_secret=data.get("client_secret"),
        scopes=data.get("scopes", USER_SCOPES),
    )


def credentials_to_dict(creds: Credentials) -> dict:
    """Serialise a :class:`Credentials` object to a plain dict for storage."""
    return {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else USER_SCOPES,
    }


def get_user_info(credentials: Credentials) -> dict:
    """Fetch basic profile information for the authenticated user.

    Returns:
        Dict with ``id``, ``email``, ``name``, ``picture``.
    """
    from googleapiclient.discovery import build as google_build

    service = google_build("oauth2", "v2", credentials=credentials)
    user_info = service.userinfo().get().execute()
    return {
        "id": user_info.get("id"),
        "email": user_info.get("email"),
        "name": user_info.get("name"),
        "picture": user_info.get("picture"),
    }
