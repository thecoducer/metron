"""Structured logging wrappers for Metron business events.

Records key application events (API calls, auth, portfolio fetches,
sheets operations) as structured log messages.  Promtail scrapes these
logs and ships them to Loki for querying in Grafana.
"""

from __future__ import annotations

from .logging_config import logger


def record_external_api_call(
    api_name: str,
    duration: float,
    success: bool,
) -> None:
    """Log an external API call."""
    logger.info(
        "external_api_call api=%s duration=%.3fs success=%s",
        api_name,
        duration,
        success,
    )


def record_auth_event(event_type: str, success: bool) -> None:
    """Log an authentication event."""
    logger.info(
        "auth_event event=%s success=%s",
        event_type,
        success,
    )


def record_portfolio_fetch(
    duration: float,
    accounts: int,
    success: bool,
) -> None:
    """Log a portfolio fetch from broker."""
    logger.info(
        "portfolio_fetch duration=%.3fs accounts=%d success=%s",
        duration,
        accounts,
        success,
    )


def record_sheets_operation(
    operation: str,
    sheet_type: str,
    success: bool,
) -> None:
    """Log a Google Sheets CRUD operation."""
    logger.info(
        "sheets_operation op=%s type=%s success=%s",
        operation,
        sheet_type,
        success,
    )
