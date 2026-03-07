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
# Two-tier Fernet encryption
#
# Tier 1 – Zerodha credentials (api_key, api_secret, access_token)
#   Key = HMAC-SHA256(ZERODHA_TOKEN_SECRET, user_pin)
#   The 6-character alphanumeric PIN is provided by the user at login
#   and NEVER stored on the server.  Even a full database +
#   secrets-manager leak cannot decrypt credentials without the user's PIN.
#
# Tier 2 – Google OAuth credentials (token, refresh_token, …)
#   Key = SHA-256(FLASK_SECRET_KEY)
#   Server-side only; no user input needed.  Protects Google tokens at
#   rest in Firestore.
#
# A special sentinel field ("pin_check") is stored per-user so the
# backend can verify a PIN without exposing any real credential.  It
# contains encrypt("METRON_PIN_OK", pin).  If decryption succeeds and
# the plaintext matches, the PIN is correct.
# ---------------------------------------------------------------------------

_PIN_CHECK_SENTINEL = "METRON_PIN_OK"


def _get_base_secret() -> bytes:
    """Return the base secret used for Zerodha per-user key derivation."""
    secret = os.environ.get("ZERODHA_TOKEN_SECRET")
    if secret:
        return secret.encode()
    machine_id = platform.node() + platform.machine()
    logger.warning("ZERODHA_TOKEN_SECRET not set — using machine-specific key")
    return machine_id.encode()


_base_secret: bytes = _get_base_secret()


# ── Tier 1: Zerodha (server secret + PIN) ─────────────────────────────────

def _derive_zerodha_cipher(pin: str) -> Fernet:
    """Derive a Fernet cipher from the server secret and user PIN."""
    key_material = hmac.new(_base_secret, pin.encode(), hashlib.sha256).digest()
    return Fernet(urlsafe_b64encode(key_material))


def encrypt_credential(value: str, pin: str) -> str:
    """Encrypt a Zerodha credential with the user's PIN-derived Fernet key."""
    return _derive_zerodha_cipher(pin).encrypt(value.encode()).decode()


def decrypt_credential(encrypted: str, pin: str) -> str:
    """Decrypt a Zerodha credential with the user's PIN-derived Fernet key.

    Raises ``cryptography.fernet.InvalidToken`` if decryption fails
    (wrong PIN or corrupted data).  No plaintext fallback.
    """
    return _derive_zerodha_cipher(pin).decrypt(encrypted.encode()).decode()


def create_pin_check(pin: str) -> str:
    """Return an encrypted sentinel that can later verify the PIN."""
    return encrypt_credential(_PIN_CHECK_SENTINEL, pin)


def verify_pin(pin_check_token: str, pin: str) -> bool:
    """Return True if *pin* decrypts the stored sentinel correctly."""
    try:
        plaintext = decrypt_credential(pin_check_token, pin)
        return plaintext == _PIN_CHECK_SENTINEL
    except (InvalidToken, Exception):
        return False


# ── Tier 2: Google OAuth creds (FLASK_SECRET_KEY, server-side only) ────────

def _get_flask_secret() -> bytes:
    """Return the Flask secret key for Google credential encryption."""
    secret = os.environ.get("FLASK_SECRET_KEY", "")
    if not secret:
        logger.warning("FLASK_SECRET_KEY not set — Google creds encryption weakened")
        secret = platform.node() + platform.machine()
    return secret.encode()


def _google_creds_cipher() -> Fernet:
    """Fernet cipher for encrypting Google OAuth credentials at rest."""
    key_material = hashlib.sha256(_get_flask_secret()).digest()
    return Fernet(urlsafe_b64encode(key_material))


def encrypt_google_credentials(creds_dict: dict) -> str:
    """Serialize + encrypt a Google credentials dict."""
    payload = json.dumps(creds_dict).encode()
    return _google_creds_cipher().encrypt(payload).decode()


def decrypt_google_credentials(encrypted: str) -> dict:
    """Decrypt + deserialize a Google credentials dict.

    Raises ``InvalidToken`` on decryption failure.
    """
    plaintext = _google_creds_cipher().decrypt(encrypted.encode())
    return json.loads(plaintext)


class SessionManager:
    """Per-user Zerodha session token store with PIN-based Fernet encryption.

    Sessions: ``{ google_id: { account_name: { "access_token", "expiry" } } }``

    The user's 6-character alphanumeric PIN is held **only in server memory**
    (never persisted).  It is required to encrypt/decrypt Zerodha access
    tokens at rest.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._user_sessions: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._user_pins: Dict[str, str] = {}  # google_id → PIN (memory only)

    # ── PIN management (in-memory only) ───────────────────────────

    def set_pin(self, google_id: str, pin: str) -> None:
        """Store the user's PIN in memory for the current server lifetime."""
        with self._lock:
            self._user_pins[google_id] = pin

    def get_pin(self, google_id: str) -> str | None:
        """Return the user's PIN if available, else None."""
        with self._lock:
            return self._user_pins.get(google_id)

    def clear_pin(self, google_id: str) -> None:
        """Remove the user's PIN from memory."""
        with self._lock:
            self._user_pins.pop(google_id, None)

    # ── Encryption helpers ────────────────────────────────────────

    def _encrypt(self, token: str, google_id: str) -> str:
        pin = self.get_pin(google_id)
        if not pin:
            raise ValueError("PIN required to encrypt Zerodha tokens")
        return encrypt_credential(token, pin)

    def _decrypt(self, encrypted: str, google_id: str) -> str:
        pin = self.get_pin(google_id)
        if not pin:
            raise ValueError("PIN required to decrypt Zerodha tokens")
        return decrypt_credential(encrypted, pin)

    def _sessions_for(self, google_id: str) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return self._user_sessions.setdefault(google_id, {})

    def load_user(self, google_id: str) -> None:
        """Load session tokens from Firestore.  Requires PIN in memory."""
        if not google_id:
            return
        pin = self.get_pin(google_id)
        if not pin:
            logger.info("Skipping session load for %s — PIN not yet provided", google_id[:8])
            return
        t0 = time.monotonic()
        try:
            from .firebase_store import get_zerodha_sessions
            stored = get_zerodha_sessions(google_id)
        except Exception as e:
            logger.exception("Error loading sessions from Firestore: %s", e)
            return

        sessions: Dict[str, Dict[str, Any]] = {}
        skipped = 0
        for name, info in stored.items():
            try:
                expiry = datetime.fromisoformat(info.get("expiry", ""))
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                skipped += 1
                continue
            try:
                access_token = self._decrypt(info.get("access_token", ""), google_id)
            except (InvalidToken, Exception):
                logger.warning("Failed to decrypt session for %s/%s — skipping",
                               google_id[:8], name)
                skipped += 1
                continue
            sessions[name] = {
                "access_token": access_token,
                "expiry": expiry,
            }

        with self._lock:
            self._user_sessions[google_id] = sessions
        elapsed = time.monotonic() - t0
        if sessions:
            logger.info("Loaded %d sessions for %s in %.2fs (skipped=%d): %s",
                        len(sessions), google_id[:8], elapsed, skipped,
                        ", ".join(sessions))
        elif stored:
            logger.warning("No valid sessions loaded for %s (stored=%d skipped=%d) in %.2fs",
                           google_id[:8], len(stored), skipped, elapsed)

    def save(self, google_id: str) -> None:
        """Persist encrypted session tokens to Firestore.  Requires PIN."""
        if not google_id:
            logger.warning("Cannot save sessions — no google_id")
            return
        pin = self.get_pin(google_id)
        if not pin:
            logger.warning("Cannot save sessions for %s — PIN not available", google_id[:8])
            return
        t0 = time.monotonic()
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
            logger.info("Saved %d sessions for %s in %.2fs",
                        len(stored), google_id[:8], time.monotonic() - t0)
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
            logger.info("Invalidated session for %s/%s", google_id[:8], account_name)
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


# ---------------------------------------------------------------------------
# PIN Rate Limiter — escalating lockout on failed verify attempts
# ---------------------------------------------------------------------------

class PinRateLimiter:
    """Per-user rate limiter for PIN verification with escalating lockouts.

    Thresholds (cumulative wrong attempts → lockout duration):
      5 failures  → 15 minutes
      10 failures → 60 minutes
      15+ failures → 4 hours

    Lockout state is in-memory only — a server restart clears it.
    This is acceptable because the PIN is never stored; an attacker
    who restarts the server loses session cookies anyway.
    """

    # (cumulative_attempts, lockout_seconds)
    LOCKOUT_TIERS = [
        (3,  15 * 60),    # 15 minutes
        (6,  60 * 60),    # 1 hour
        (9,  4 * 60 * 60),  # 4 hours
    ]

    def __init__(self):
        self._lock = threading.Lock()
        # {google_id: {"attempts": int, "locked_until": float|None}}
        self._state: Dict[str, Dict] = {}

    def _get(self, google_id: str) -> Dict:
        if google_id not in self._state:
            self._state[google_id] = {"attempts": 0, "locked_until": None}
        return self._state[google_id]

    def check(self, google_id: str) -> tuple:
        """Check if user is locked out.

        Returns:
            (allowed: bool, retry_after: int|None)
            retry_after is seconds remaining when locked.
        """
        with self._lock:
            state = self._get(google_id)
            if state["locked_until"] is not None:
                remaining = state["locked_until"] - time.time()
                if remaining > 0:
                    return False, int(remaining) + 1
                # Lockout expired — don't reset attempts (they're cumulative)
                state["locked_until"] = None
            return True, None

    def record_failure(self, google_id: str) -> tuple:
        """Record a failed PIN attempt and apply lockout if threshold hit.

        Returns:
            (attempts: int, locked_until_seconds: int|None)
        """
        with self._lock:
            state = self._get(google_id)
            state["attempts"] += 1
            attempts = state["attempts"]

            # Find applicable lockout tier
            lockout_secs = None
            for threshold, duration in self.LOCKOUT_TIERS:
                if attempts >= threshold:
                    lockout_secs = duration

            if lockout_secs and (attempts % 3 == 0 or attempts >= self.LOCKOUT_TIERS[-1][0]):
                # Apply lockout on every 5th failure or beyond max tier
                state["locked_until"] = time.time() + lockout_secs
                return attempts, lockout_secs

            return attempts, None

    def record_success(self, google_id: str) -> None:
        """Clear rate-limit state on successful verification."""
        with self._lock:
            self._state.pop(google_id, None)

    def clear(self, google_id: str) -> None:
        """Clear state for a user (e.g. on PIN reset)."""
        with self._lock:
            self._state.pop(google_id, None)

    def get_attempts(self, google_id: str) -> int:
        """Return the current failure count for *google_id* (0 if absent)."""
        with self._lock:
            return self._get(google_id)["attempts"]


# ---------------------------------------------------------------------------
# Date Parsing — shared across PF, FD, and other sheet-based services
# ---------------------------------------------------------------------------

from dateutil.parser import parse as _dateutil_parse


def parse_date(raw):
    """Parse a flexible date string into a ``datetime.date``, or *None*.

    Uses ``python-dateutil`` so it handles ISO-8601, US, long-month
    and many other formats automatically.
    """
    if not raw or not str(raw).strip():
        return None
    try:
        return _dateutil_parse(str(raw).strip()).date()
    except (ValueError, OverflowError):
        return None

    def get_attempts(self, google_id: str) -> int:
        """Return current attempt count for a user."""
        with self._lock:
            return self._get(google_id)["attempts"]


# Singleton instance
pin_rate_limiter = PinRateLimiter()

