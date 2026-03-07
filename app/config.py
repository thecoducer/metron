"""
Application configuration loaded from environment variables.
"""

import os
from dataclasses import dataclass, field

from .constants import (DEFAULT_AUTO_REFRESH_INTERVAL,
                        DEFAULT_REQUEST_TOKEN_TIMEOUT,
                        DEFAULT_UI_HOST, DEFAULT_UI_PORT)


def _env_bool(key: str, default: bool = False) -> bool:
    """Read an env var as a boolean (true/1/yes → True)."""
    return os.environ.get(key, str(default)).lower() in ("true", "1", "yes")


@dataclass
class AppConfig:
    """Application configuration loaded from environment variables."""
    ui_host: str
    ui_port: int
    request_token_timeout: int
    auto_refresh_interval: int
    auto_refresh_outside_market_hours: bool
    features: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> 'AppConfig':
        """Build configuration from environment variables."""
        allow_browser_api = _env_bool("METRON_ALLOW_BROWSER_API_ACCESS", False)
        return cls(
            ui_host=os.environ.get("METRON_UI_HOST", DEFAULT_UI_HOST),
            ui_port=int(os.environ.get("METRON_UI_PORT", DEFAULT_UI_PORT)),
            request_token_timeout=int(os.environ.get("METRON_REQUEST_TOKEN_TIMEOUT", DEFAULT_REQUEST_TOKEN_TIMEOUT)),
            auto_refresh_interval=int(os.environ.get("METRON_AUTO_REFRESH_INTERVAL", DEFAULT_AUTO_REFRESH_INTERVAL)),
            auto_refresh_outside_market_hours=_env_bool("METRON_AUTO_REFRESH_OUTSIDE_MARKET_HOURS", False),
            features={"allow_browser_api_access": allow_browser_api},
        )


# Module-level singleton
app_config = AppConfig.from_env()
