"""
Authentication and session management for Zerodha KiteConnect.
"""
from typing import Any, Dict

from kiteconnect import KiteConnect
from requests.exceptions import ConnectionError, ReadTimeout

from ..logging_config import logger


class AuthenticationManager:
    """Handles authentication flow with KiteConnect API.

    Supports two authentication strategies:
    1. Cached token (fastest, if valid)
    2. Token renewal (if cached token expired but renewable)

    Full OAuth login is handled separately via the UI callback route,
    not by this manager.
    """

    def __init__(self, session_manager):
        self.session_manager = session_manager

    def _validate_token_with_api_call(self, kite: KiteConnect, account_name: str) -> bool:
        """Validate token by making a test API call. Returns True if valid."""
        try:
            kite.profile()
            return True
        except (ReadTimeout, ConnectionError) as e:
            logger.warning("Token validation timed out for %s: %s", account_name, str(e))
            # Don't invalidate on timeout - just raise to skip this account
            raise
        except Exception as e:
            logger.warning("Token validation failed for %s: %s", account_name, str(e))
            # Invalidate only on actual validation failures (not timeouts)
            self.session_manager.invalidate(account_name)
            return False
    
    def _try_cached_token(self, kite: KiteConnect, account_name: str) -> bool:
        """Try to use cached token. Returns True if successful."""
        token = self.session_manager.get_token(account_name)
        if not token or not self.session_manager.is_valid(account_name):
            return False
        logger.info("Using cached token for %s", account_name)
        kite.set_access_token(token)
        return self._validate_token_with_api_call(kite, account_name)
    
    def _store_token(self, kite: KiteConnect, account_name: str, access_token: str) -> None:
        """Store and apply access token to KiteConnect instance."""
        kite.set_access_token(access_token)
        self.session_manager.set_token(account_name, access_token)
        self.session_manager.save()
    
    def _try_renew_token(self, kite: KiteConnect, account_name: str, api_secret: str) -> bool:
        """Try to renew expired token. Returns True if successful."""
        old_token = self.session_manager.get_token(account_name)
        if not old_token:
            logger.info("No token found for %s, skipping renewal", account_name)
            return False

        logger.info("Attempting to renew session for %s...", account_name)
        try:
            renewed_session = kite.renew_access_token(old_token, api_secret)
            new_access_token = renewed_session.get("access_token")
            if not new_access_token:
                logger.warning("Renewal response missing access_token for %s", account_name)
                return False

            logger.info("Successfully renewed session for %s", account_name)
            self._store_token(kite, account_name, new_access_token)
            return True
        except (ReadTimeout, ConnectionError):
            logger.warning("Token renewal timed out for %s", account_name)
            raise  # Don't invalidate on network errors
        except Exception as e:
            logger.warning("Session renewal failed for %s: %s", account_name, e)
            return False

    def authenticate(self, account_config: Dict[str, Any]) -> KiteConnect:
        """Authenticate and return KiteConnect instance.

        Tries authentication strategies in order:
        1. Cached token
        2. Token renewal (if cached exists but expired)

        If both fail, raises RuntimeError.  Full OAuth login is handled
        separately via the UI callback route.

        Args:
            account_config: Account configuration with api_key, api_secret

        Returns:
            Authenticated KiteConnect instance
        """
        account_name = account_config["name"]
        api_key = account_config["api_key"]
        api_secret = account_config["api_secret"]

        kite = KiteConnect(api_key=api_key)

        # Strategy 1: Try cached token
        if self._try_cached_token(kite, account_name):
            return kite

        # Strategy 2: Try token renewal
        if self._try_renew_token(kite, account_name, api_secret):
            return kite

        # No more strategies — login must happen via the UI
        raise RuntimeError(
            f"Session expired for {account_name}. "
            "Please log in via the Zerodha login link in the app."
        )
