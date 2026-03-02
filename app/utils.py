"""
Utility functions for session management, market operations, and common patterns.
"""
import hashlib
import json
import os
import platform
import time
from base64 import urlsafe_b64encode
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet

from .constants import (MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE,
                        MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE, STATE_ERROR,
                        STATE_UPDATED, STATE_UPDATING, WEEKEND_SATURDAY)
from .logging_config import logger


class SessionManager:
    """Manages Zerodha session tokens with Firestore persistence and Fernet encryption.

    Tokens are stored per-user in Firebase Firestore and cached in memory for
    fast access.  Encryption uses a secret from the ``ZERODHA_TOKEN_SECRET``
    environment variable (falls back to a machine-specific key for local
    development when the variable is unset).

    Usage::

        sm = SessionManager()
        sm.set_user("google_id_123")   # loads sessions from Firestore
        sm.set_token("AccountName", "access_token_xyz")
        sm.save()                       # persists to Firestore
    """

    def __init__(self):
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self._cipher = self._get_cipher()
        self._google_id: str = None

    # ------------------------------------------------------------------
    # Encryption
    # ------------------------------------------------------------------

    @staticmethod
    def _get_cipher() -> Fernet:
        """Build a Fernet cipher.

        Key source priority:
        1. ``ZERODHA_TOKEN_SECRET`` env var  (production)
        2. Machine-specific fallback          (local development)
        """
        secret = os.environ.get("ZERODHA_TOKEN_SECRET")
        if secret:
            key_material = hashlib.sha256(secret.encode()).digest()
        else:
            machine_id = platform.node() + platform.machine()
            key_material = hashlib.sha256(machine_id.encode()).digest()
            logger.warning(
                "ZERODHA_TOKEN_SECRET not set – using machine-specific key "
                "(not suitable for production)"
            )
        key = urlsafe_b64encode(key_material)
        return Fernet(key)

    def _encrypt_token(self, token: str) -> str:
        """Encrypt an access token."""
        return self._cipher.encrypt(token.encode()).decode()

    def _decrypt_token(self, encrypted_token: str) -> str:
        """Decrypt an access token."""
        try:
            return self._cipher.decrypt(encrypted_token.encode()).decode()
        except Exception:
            return encrypted_token

    # ------------------------------------------------------------------
    # User scoping
    # ------------------------------------------------------------------

    def set_user(self, google_id: str) -> None:
        """Set the active user and load their sessions from Firestore.

        If *google_id* is the same as the current user the call is a no-op.
        """
        if not google_id:
            return
        if self._google_id == google_id:
            return
        self._google_id = google_id
        self.sessions = {}
        self.load()

    # ------------------------------------------------------------------
    # Firestore persistence
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load session tokens from Firestore for the active user."""
        if not self._google_id:
            return

        try:
            from .firebase_store import get_zerodha_sessions
            stored = get_zerodha_sessions(self._google_id)
        except Exception as e:
            logger.exception("Error loading sessions from Firestore: %s", e)
            return

        for account_name, session_info in stored.items():
            expiry_str = session_info.get("expiry")
            try:
                expiry = datetime.fromisoformat(expiry_str)
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue

            encrypted_token = session_info.get("access_token")
            access_token = self._decrypt_token(encrypted_token)

            self.sessions[account_name] = {
                "access_token": access_token,
                "expiry": expiry,
            }

        if self.sessions:
            logger.info(
                "Loaded cached sessions for: %s",
                ", ".join(self.sessions.keys()),
            )

    def save(self) -> None:
        """Persist session tokens to Firestore for the active user."""
        if not self._google_id:
            logger.warning("Cannot save sessions – no active user set")
            return

        stored: Dict[str, Dict[str, str]] = {}
        for account_name, info in self.sessions.items():
            stored[account_name] = {
                "access_token": self._encrypt_token(info["access_token"]),
                "expiry": info["expiry"].isoformat(),
            }

        try:
            from .firebase_store import save_zerodha_sessions
            save_zerodha_sessions(self._google_id, stored)
            logger.info(
                "Saved encrypted sessions to Firestore for: %s",
                ", ".join(stored.keys()),
            )
        except Exception as e:
            logger.exception("Error saving sessions to Firestore: %s", e)

    # ------------------------------------------------------------------
    # Token operations (interface unchanged)
    # ------------------------------------------------------------------

    def _is_token_expired(self, expiry: datetime) -> bool:
        """Check if a token has expired."""
        return datetime.now(timezone.utc) >= expiry

    def is_valid(self, account_name: str) -> bool:
        """Check if account session token is still valid."""
        sess = self.sessions.get(account_name)
        if not sess:
            return False
        return not self._is_token_expired(sess["expiry"])

    def set_token(self, account_name: str, access_token: str, hours: int = 23, minutes: int = 50):
        """Store a new access token with expiry."""
        self.sessions[account_name] = {
            "access_token": access_token,
            "expiry": datetime.now(timezone.utc) + timedelta(hours=hours, minutes=minutes),
        }

    def get_token(self, account_name: str) -> str:
        """Get access token for account."""
        return self.sessions.get(account_name, {}).get("access_token")

    def invalidate(self, account_name: str):
        """Invalidate (remove) the session for an account."""
        if account_name in self.sessions:
            del self.sessions[account_name]
            logger.info("Invalidated session for account: %s", account_name)
            self.save()

    def get_validity(self, all_accounts: List[str] = None) -> Dict[str, bool]:
        """Get validity status for all accounts.

        Args:
            all_accounts: Optional list of all account names from config.
                         If provided, ensures all accounts are included in result.

        Returns:
            Dict mapping account name to validity status (True if valid, False otherwise)
        """
        if all_accounts:
            return {name: self.is_valid(name) for name in all_accounts}
        else:
            return {name: self.is_valid(name) for name in self.sessions.keys()}


class StateManager:
    """Manages application state with thread safety."""
    
    # State type names for dynamic attribute access
    STATE_TYPES = ('portfolio', 'nifty50', 'physical_gold', 'fixed_deposits')
    
    def __init__(self):
        # Initialize all state types dynamically
        for state_type in self.STATE_TYPES:
            setattr(self, f'{state_type}_state', None)
            setattr(self, f'{state_type}_last_updated', None)
        
        self.last_error: str = None
        self._change_listeners = []
    
    def _notify_change(self):
        """Notify all listeners that state has changed."""
        for listener in self._change_listeners:
            try:
                listener()
            except Exception as e:
                logger.exception("Error notifying listener: %s", e)
    
    def add_change_listener(self, callback):
        """Add a callback to be notified on state changes."""
        self._change_listeners.append(callback)
    
    def _set_updating(self, state_type: str, error: str = None):
        """Generic method to set any state type to updating."""
        setattr(self, f'{state_type}_state', STATE_UPDATING)
        if error:
            self.last_error = error
        self._notify_change()
    
    def _set_updated(self, state_type: str, error: str = None, clear_global_error: bool = False):
        """Generic method to mark any state type as updated.
        
        Args:
            state_type: Type of state (portfolio, nifty50, etc.)
            error: Optional error message. If provided, state is set to ERROR.
            clear_global_error: If True and no error, clear last_error.
        """
        if error:
            self.last_error = error
            setattr(self, f'{state_type}_state', STATE_ERROR)
        else:
            setattr(self, f'{state_type}_last_updated', time.time())
            if clear_global_error:
                self.last_error = None
            setattr(self, f'{state_type}_state', STATE_UPDATED)
        self._notify_change()
    
    # Portfolio-specific methods
    def set_portfolio_updating(self, error: str = None):
        self._set_updating('portfolio', error)
    
    def set_portfolio_updated(self, error: str = None):
        self._set_updated('portfolio', error, clear_global_error=True)
    
    def __getattr__(self, name: str):
        """Dynamically handle set_<state_type>_updating / set_<state_type>_updated calls.

        For non-portfolio state types (nifty50, physical_gold, fixed_deposits),
        the updating/updated setters are identical one-liners delegating to
        _set_updating / _set_updated. Instead of declaring each explicitly,
        we generate them on the fly.
        """
        for state_type in self.STATE_TYPES:
            if state_type == 'portfolio':  # portfolio has custom methods above
                continue
            if name == f'set_{state_type}_updating':
                def _updating(error: str = None, _st=state_type):
                    self._set_updating(_st, error)
                return _updating
            if name == f'set_{state_type}_updated':
                def _updated(error: str = None, _st=state_type):
                    self._set_updated(_st, error)
                return _updated
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}')")
    
    def is_any_running(self) -> bool:
        """Check if any operation is currently updating."""
        return any(
            getattr(self, f'{st}_state') == STATE_UPDATING 
            for st in self.STATE_TYPES
        )
    
    def clear_error(self):
        """Clear the last error message."""
        self.last_error = None
        self._notify_change()


def format_timestamp(ts: float) -> str:
    """Format Unix timestamp to readable format."""
    if ts is None:
        return None
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))


def is_market_open_ist() -> bool:
    """Check if equity market is currently open.
    
    Market hours: 9:00 AM - 4:30 PM IST, Monday-Friday
    """
    ist = ZoneInfo("Asia/Kolkata")
    now = datetime.now(ist)
    
    # Check if weekend
    if now.weekday() >= WEEKEND_SATURDAY:
        return False
    
    # Define market hours
    market_open = now.replace(
        hour=MARKET_OPEN_HOUR,
        minute=MARKET_OPEN_MINUTE,
        second=0,
        microsecond=0
    )
    market_close = now.replace(
        hour=MARKET_CLOSE_HOUR,
        minute=MARKET_CLOSE_MINUTE,
        second=0,
        microsecond=0
    )
    
    return market_open <= now <= market_close


def load_config(config_path: str) -> Dict[str, Any]:
    """Load configuration from JSON file.

    Returns an empty dict on any error (file missing, invalid JSON, etc.).
    """
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("Config file not found: %s", config_path)
        return {}
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON in %s: %s", config_path, e)
        return {}
    except Exception as e:
        logger.exception("Error loading config %s: %s", config_path, e)
        return {}

