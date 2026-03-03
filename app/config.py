"""
Application configuration loaded from config.json.
"""

import os
from dataclasses import dataclass

from .constants import (CONFIG_DIR_NAME, CONFIG_FILENAME,
                        DEFAULT_AUTO_REFRESH_INTERVAL,
                        DEFAULT_REQUEST_TOKEN_TIMEOUT,
                        DEFAULT_UI_HOST, DEFAULT_UI_PORT)
from .utils import load_config


@dataclass
class AppConfig:
    """Application configuration loaded from config.json."""
    ui_host: str
    ui_port: int
    request_token_timeout: int
    auto_refresh_interval: int
    auto_refresh_outside_market_hours: bool
    features: dict

    @classmethod
    def from_file(cls, config_path: str) -> 'AppConfig':
        """Load and parse application configuration from config.json."""
        config = load_config(config_path)

        server = config.get("server", {})
        timeouts = config.get("timeouts", {})
        features = config.get("features", {})

        return cls(
            ui_host=server.get("ui_host", DEFAULT_UI_HOST),
            ui_port=server.get("ui_port", DEFAULT_UI_PORT),
            request_token_timeout=timeouts.get("request_token_timeout_seconds", DEFAULT_REQUEST_TOKEN_TIMEOUT),
            auto_refresh_interval=timeouts.get("auto_refresh_interval_seconds", DEFAULT_AUTO_REFRESH_INTERVAL),
            auto_refresh_outside_market_hours=features.get("auto_refresh_outside_market_hours", False),
            features=features,
        )


# Module-level singleton
_project_root = os.path.dirname(os.path.dirname(__file__))
app_config = AppConfig.from_file(os.path.join(_project_root, CONFIG_DIR_NAME, CONFIG_FILENAME))
