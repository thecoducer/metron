"""Session management, state tracking, and utility functions."""

import hashlib
import hmac
import json
import os
import platform
import threading
import time
from base64 import urlsafe_b64encode
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet, InvalidToken

from .constants import (MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE,
                        MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE, STATE_ERROR,
                        STATE_UPDATED, STATE_UPDATING, WEEKEND_SATURDAY)
from .logging_config import logger


# ---------------------------------------------------------------------------
# Per-user Fernet encryption for Zerodha credentials at rest
#
# Each user's credentials are encrypted with a key derived from
#   HMAC-SHA256(server_secret, google_id)
# so that:
#   • A database leak alone reveals only ciphertext.
#   • The server secret alone is useless without the ciphertext.
#   • There is no single "master key" that decrypts all users at once.
# ---------------------------------------------------------------------------

def _get_base_secret() -> bytes:
    """Return the base secret used for per-user key derivation."""
    secret = os.environ.get("ZERODHA_TOKEN_SECRET")
    if secret:
        return secret.encode()
    machine_id = platform.node() + platform.machine()
    logger.warning("ZERODHA_TOKEN_SECRET not set — using machine-specific key")
    return machine_id.encode()


_base_secret: bytes = _get_base_secret()


def _derive_user_cipher(google_id: str) -> Fernet:
    """Derive a per-user Fernet cipher from the server secret and user ID."""
    key_material = hmac.new(
        _base_secret, google_id.encode(), hashlib.sha256
    ).digest()
    return Fernet(urlsafe_b64encode(key_material))


def encrypt_credential(value: str, google_id: str) -> str:
    """Encrypt a credential with a per-user Fernet key."""
    return _derive_user_cipher(google_id).encrypt(value.encode()).decode()


def decrypt_credential(encrypted: str, google_id: str) -> str:
    """Decrypt a credential with a per-user Fernet key.

    Raises ``cryptography.fernet.InvalidToken`` if decryption fails.
    No plaintext fallback — callers must handle the error.
    """
    return _derive_user_cipher(google_id).decrypt(encrypted.encode()).decode()


class SessionManager:
    """Per-user Zerodha session token store with Fernet encryption.

    Sessions: ``{ google_id: { account_name: { "access_token", "expiry" } } }``
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._user_sessions: Dict[str, Dict[str, Dict[str, Any]]] = {}

    def _encrypt(self, token: str, google_id: str) -> str:
        return encrypt_credential(token, google_id)

    def _decrypt(self, encrypted: str, google_id: str) -> str:
        return decrypt_credential(encrypted, google_id)

    def _sessions_for(self, google_id: str) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return self._user_sessions.setdefault(google_id, {})

    def load_user(self, google_id: str) -> None:
        """Load session tokens from Firestore. Idempotent."""
        if not google_id:
            return
        try:
            from .firebase_store import get_zerodha_sessions
            stored = get_zerodha_sessions(google_id)
        except Exception as e:
            logger.exception("Error loading sessions from Firestore: %s", e)
            return

        sessions: Dict[str, Dict[str, Any]] = {}
        for name, info in stored.items():
            try:
                expiry = datetime.fromisoformat(info.get("expiry", ""))
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue
            try:
                access_token = self._decrypt(info.get("access_token", ""), google_id)
            except (InvalidToken, Exception):
                logger.warning("Failed to decrypt session for %s/%s — skipping",
                               google_id, name)
                continue
            sessions[name] = {
                "access_token": access_token,
                "expiry": expiry,
            }

        with self._lock:
            self._user_sessions[google_id] = sessions
        if sessions:
            logger.info("Loaded sessions for %s: %s", google_id, ", ".join(sessions))

    def save(self, google_id: str) -> None:
        """Persist encrypted session tokens to Firestore."""
        if not google_id:
            logger.warning("Cannot save sessions — no google_id")
            return
        with self._lock:
            user_sessions = dict(self._user_sessions.get(google_id, {}))

        stored = {
            name: {"access_token": self._encrypt(info["access_token"], google_id),
                    "expiry": info["expiry"].isoformat()}
            for name, info in user_sessions.items()
        }
        try:
            from .firebase_store import save_zerodha_sessions
            save_zerodha_sessions(google_id, stored)
            logger.info("Saved sessions for %s: %s", google_id, ", ".join(stored))
        except Exception as e:
            logger.exception("Error saving sessions to Firestore: %s", e)

    def is_valid(self, google_id: str, account_name: str) -> bool:
        sess = self._sessions_for(google_id).get(account_name)
        return bool(sess and datetime.now(timezone.utc) < sess["expiry"])

    def set_token(self, google_id: str, account_name: str,
                  access_token: str, hours: int = 23, minutes: int = 50) -> None:
        self._sessions_for(google_id)[account_name] = {
            "access_token": access_token,
            "expiry": datetime.now(timezone.utc) + timedelta(hours=hours, minutes=minutes),
        }

    def get_token(self, google_id: str, account_name: str) -> str:
        return self._sessions_for(google_id).get(account_name, {}).get("access_token")

    def invalidate(self, google_id: str, account_name: str) -> None:
        sessions = self._sessions_for(google_id)
        if account_name in sessions:
            del sessions[account_name]
            logger.info("Invalidated session for %s/%s", google_id, account_name)
            self.save(google_id)

    def get_validity(self, google_id: str, all_accounts: List[str] = None) -> Dict[str, bool]:
        names = all_accounts or list(self._sessions_for(google_id))
        return {name: self.is_valid(google_id, name) for name in names}


class StateManager:
    """Per-user portfolio state + global market-data state with change notification.

    Per-user: ``portfolio``
    Global:   ``nifty50``, ``physical_gold``, ``fixed_deposits``
    """

    GLOBAL_STATE_TYPES = ('nifty50', 'physical_gold', 'fixed_deposits')
    PER_USER_STATE_TYPE = 'portfolio'
    STATE_TYPES = ('portfolio',) + GLOBAL_STATE_TYPES

    def __init__(self):
        self._lock = threading.Lock()
        for st in self.GLOBAL_STATE_TYPES:
            setattr(self, f'{st}_state', None)
            setattr(self, f'{st}_last_updated', None)
        self._user_state: Dict[str, Dict[str, Any]] = {}
        self.last_error: str = None
        self._change_listeners = []

    def _get_user_state(self, google_id: str) -> Dict[str, Any]:
        with self._lock:
            return self._user_state.setdefault(google_id, {
                "portfolio_state": None,
                "portfolio_last_updated": time.time(),
                "last_error": None,
            })

    def _notify_change(self, google_id: str = None):
        for listener in self._change_listeners:
            try:
                listener(google_id=google_id)
            except TypeError:
                try:
                    listener()
                except Exception as e:
                    logger.exception("Error notifying listener: %s", e)
            except Exception as e:
                logger.exception("Error notifying listener: %s", e)

    def add_change_listener(self, callback):
        self._change_listeners.append(callback)

    # Per-user portfolio state

    def set_portfolio_updating(self, google_id: str = None, error: str = None):
        if google_id:
            us = self._get_user_state(google_id)
            us["portfolio_state"] = STATE_UPDATING
            if error:
                us["last_error"] = error
        self._notify_change(google_id)

    def set_portfolio_updated(self, google_id: str = None, error: str = None):
        if google_id:
            us = self._get_user_state(google_id)
            if error:
                us["last_error"] = error
                us["portfolio_state"] = STATE_ERROR
            else:
                us["portfolio_last_updated"] = time.time()
                us["last_error"] = None
                us["portfolio_state"] = STATE_UPDATED
        self._notify_change(google_id)

    def get_portfolio_state(self, google_id: str) -> Any:
        return self._get_user_state(google_id).get("portfolio_state")

    def get_portfolio_last_updated(self, google_id: str) -> Any:
        return self._get_user_state(google_id).get("portfolio_last_updated")

    def get_user_last_error(self, google_id: str) -> Any:
        return self._get_user_state(google_id).get("last_error")

    # Global state (dynamic set_<type>_updating / set_<type>_updated)

    def _set_updating(self, state_type: str, error: str = None):
        setattr(self, f'{state_type}_state', STATE_UPDATING)
        if error:
            self.last_error = error
        self._notify_change()

    def _set_updated(self, state_type: str, error: str = None, clear_global_error: bool = False):
        if error:
            self.last_error = error
            setattr(self, f'{state_type}_state', STATE_ERROR)
        else:
            setattr(self, f'{state_type}_last_updated', time.time())
            if clear_global_error:
                self.last_error = None
            setattr(self, f'{state_type}_state', STATE_UPDATED)
        self._notify_change()

    def __getattr__(self, name: str):
        for st in self.GLOBAL_STATE_TYPES:
            if name == f'set_{st}_updating':
                return lambda error=None, _st=st: self._set_updating(_st, error)
            if name == f'set_{st}_updated':
                return lambda error=None, _st=st: self._set_updated(_st, error)
        raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")

    def is_any_running(self, google_id: str = None) -> bool:
        if any(getattr(self, f'{st}_state', None) == STATE_UPDATING for st in self.GLOBAL_STATE_TYPES):
            return True
        if google_id:
            return self._get_user_state(google_id).get("portfolio_state") == STATE_UPDATING
        return False

    def clear_error(self, google_id: str = None):
        self.last_error = None
        if google_id:
            self._get_user_state(google_id)["last_error"] = None
        self._notify_change(google_id)


def format_timestamp(ts: float) -> str:
    if ts is None:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def is_market_open_ist() -> bool:
    """Check if equity market is open (9:00–16:30 IST, Mon–Fri)."""
    ist = ZoneInfo("Asia/Kolkata")
    now = datetime.now(ist)
    if now.weekday() >= WEEKEND_SATURDAY:
        return False
    market_open = now.replace(hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MINUTE, second=0, microsecond=0)
    market_close = now.replace(hour=MARKET_CLOSE_HOUR, minute=MARKET_CLOSE_MINUTE, second=0, microsecond=0)
    return market_open <= now <= market_close


def load_config(config_path: str) -> Dict[str, Any]:
    """Load JSON config file. Returns empty dict on error."""
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

