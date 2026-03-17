"""Startup helpers for loading runtime configuration before app imports."""

from __future__ import annotations

import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_DIR = _PROJECT_ROOT / "config"
_SECRET_FILE_MAP = {
    "FLASK_SECRET_KEY": _CONFIG_DIR / "flask-secret-key.txt",
    "ZERODHA_TOKEN_SECRET": _CONFIG_DIR / "zerodha-token-secret.txt",
}


def load_runtime_env() -> None:
    """Populate env vars from local secret files when they are unset.

    This keeps local Gunicorn startup aligned with production startup by
    ensuring file-backed secrets are available before Flask routes and crypto
    helpers are imported.
    """
    for env_name, file_path in _SECRET_FILE_MAP.items():
        if os.environ.get(env_name):
            continue
        try:
            secret = file_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            continue
        if secret:
            os.environ[env_name] = secret
