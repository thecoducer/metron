"""Zerodha KiteConnect authentication and session management."""

from typing import Any

from kiteconnect import KiteConnect
from requests.exceptions import ConnectionError, ReadTimeout

from ..logging_config import logger


class AuthenticationManager:
    """Authenticates Zerodha accounts via cached token or token renewal.

    All operations are scoped by ``google_id`` from the account config.
    """

    def __init__(self, session_manager):
        self.session_manager = session_manager

    def _validate_token(self, kite: KiteConnect, google_id: str, name: str) -> bool:
        """Check if the current token is valid by calling the profile API."""
        try:
            kite.profile()
            return True
        except (ReadTimeout, ConnectionError):
            raise
        except Exception as e:
            logger.warning("Token validation failed for %s: %s", name, e)
            self.session_manager.invalidate(google_id, name)
            return False

    def _try_cached_token(self, kite: KiteConnect, google_id: str, name: str) -> bool:
        """Try to authenticate using a cached, non-expired session token."""
        token = self.session_manager.get_token(google_id, name)
        if not token or not self.session_manager.is_valid(google_id, name):
            return False
        logger.info("Using cached token for %s", name)
        kite.set_access_token(token)
        return self._validate_token(kite, google_id, name)

    def _store_token(self, kite: KiteConnect, google_id: str, name: str, token: str) -> None:
        """Store a new access token and persist it to Firestore."""
        kite.set_access_token(token)
        self.session_manager.set_token(google_id, name, token)
        self.session_manager.save(google_id)

    def _try_renew_token(self, kite: KiteConnect, google_id: str, name: str, api_secret: str) -> bool:
        """Attempt to renew an expired token using Kite's renewal API."""
        old_token = self.session_manager.get_token(google_id, name)
        if not old_token:
            return False
        logger.info("Renewing session for %s...", name)
        try:
            new_token = kite.renew_access_token(old_token, api_secret).get("access_token")  # type: ignore[union-attr]
            if not new_token:
                return False
            logger.info("Renewed session for %s", name)
            self._store_token(kite, google_id, name, new_token)
            return True
        except (ReadTimeout, ConnectionError):
            raise
        except Exception as e:
            logger.warning("Renewal failed for %s: %s", name, e)
            return False

    def authenticate(self, account_config: dict[str, Any]) -> KiteConnect:
        """Return an authenticated KiteConnect instance.

        Tries cached token, then renewal. Raises RuntimeError if both fail.
        """
        gid = account_config["google_id"]
        name = account_config["name"]
        kite = KiteConnect(api_key=account_config["api_key"])

        if self._try_cached_token(kite, gid, name):
            return kite
        if self._try_renew_token(kite, gid, name, account_config["api_secret"]):
            return kite

        raise RuntimeError(f"Session expired for {name}. Please log in via the app.")
