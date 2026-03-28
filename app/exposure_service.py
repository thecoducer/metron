"""Exposure analysis orchestration — manages background analysis threads."""

import threading
from typing import Any

from .constants import HTTP_ACCEPTED, HTTP_CONFLICT
from .logging_config import logger
from .services import _serialise_exposure, state_manager


def get_or_start_analysis(
    google_id: str,
    stocks_and_etfs: list[dict[str, Any]],
    mf_data: list[dict[str, Any]],
) -> tuple[dict[str, Any], int]:
    """Return cached exposure data or start background analysis.

    Returns (payload_dict, http_status_code).
    """
    from .api.exposure import exposure_cache

    # 1. Serve from cache if warm.
    cached = exposure_cache.get(google_id)
    if cached:
        return _serialise_exposure(cached), 200

    # 2. No data from previous analysis.
    if exposure_cache.has_no_data(google_id):
        return _no_data_payload(), 200

    # 3. Already running — tell client to wait.
    if exposure_cache.is_in_progress(google_id):
        return {"status": "processing"}, HTTP_ACCEPTED

    # 4. No holdings to analyse.
    if not stocks_and_etfs and not mf_data:
        return _no_data_payload(), 200

    # 5. Kick off background analysis.
    exposure_cache.set_in_progress(google_id)
    _start_analysis_thread(
        google_id,
        stocks_and_etfs,
        mf_data,
        name_prefix="ExposureAnalysis",
    )
    return {"status": "processing"}, HTTP_ACCEPTED


def refresh_analysis(
    google_id: str,
    stocks_and_etfs: list[dict[str, Any]],
    mf_data: list[dict[str, Any]],
) -> tuple[dict[str, Any], int]:
    """Invalidate cache and re-trigger exposure analysis.

    Returns (payload_dict, http_status_code).
    """
    from .api.exposure import exposure_cache

    if exposure_cache.is_in_progress(google_id):
        return {"status": "processing"}, HTTP_CONFLICT

    exposure_cache.invalidate(google_id)

    if not stocks_and_etfs and not mf_data:
        return _no_data_payload(), 200

    exposure_cache.set_in_progress(google_id)
    _start_analysis_thread(
        google_id,
        stocks_and_etfs,
        mf_data,
        name_prefix="ExposureRefresh",
    )
    return {"status": "processing"}, HTTP_ACCEPTED


def _no_data_payload() -> dict[str, Any]:
    """Return the standard 'no data' exposure payload."""
    return {
        "has_data": False,
        "companies": [],
        "sector_totals": {},
        "total_portfolio_value": 0,
    }


def _start_analysis_thread(
    google_id: str,
    stocks_and_etfs: list[dict[str, Any]],
    mf_data: list[dict[str, Any]],
    *,
    name_prefix: str,
) -> None:
    """Start a daemon thread to run exposure analysis."""
    from .api.exposure import (
        ExposureResult,
        build_exposure_data,
        exposure_cache,
    )

    def _run_analysis() -> None:
        try:
            result: ExposureResult | None = build_exposure_data(google_id, stocks_and_etfs, mf_data)
            if result is not None:
                state_manager.set_exposure_updated(google_id)
                exposure_cache.put(google_id, result)
            else:
                logger.info(
                    "%s returned no data for user=%s",
                    name_prefix,
                    google_id[:8],
                )
                exposure_cache.mark_no_data(google_id)
        except Exception as exc:
            logger.exception(
                "%s failed for user=%s: %s",
                name_prefix,
                google_id[:8],
                exc,
            )
            exposure_cache.mark_no_data(google_id)
        finally:
            exposure_cache.clear_in_progress(google_id)

    threading.Thread(
        target=_run_analysis,
        name=f"{name_prefix}-{google_id[:8]}",
        daemon=True,
    ).start()
