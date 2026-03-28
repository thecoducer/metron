"""OpenTelemetry instrumentation for the Metron Flask application.

Exports logs, traces, and metrics to SigNoz via OTLP/HTTP.
Controlled entirely by environment variables:

  OTEL_EXPORTER_OTLP_ENDPOINT  – e.g. http://signoz-otel-collector:4318
  OTEL_SERVICE_NAME             – defaults to "metron"

When no endpoint is configured, instrumentation is silently skipped
so local dev runs without SigNoz are unaffected.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from flask import Flask, g, request

from .logging_config import logger

# Module-level meter reference so other modules can record metrics
_meter: Any = None


def get_meter() -> Any:
    """Return the OTEL meter, or None if telemetry is disabled."""
    return _meter


def _otel_enabled() -> bool:
    return bool(os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"))


def init_telemetry(app: Flask) -> None:
    """Wire OpenTelemetry into the Flask app if OTLP endpoint is set."""
    if not _otel_enabled():
        logger.info("OTEL_EXPORTER_OTLP_ENDPOINT not set — telemetry disabled")
        return

    try:
        _setup_tracing(app)
        _setup_metrics(app)
        _setup_log_export()
        logger.info("OpenTelemetry instrumentation initialized")
    except Exception:
        logger.exception(
            "Failed to initialize OpenTelemetry — continuing without telemetry"
        )


def _setup_tracing(app: Flask) -> None:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter,
    )
    from opentelemetry.instrumentation.flask import FlaskInstrumentor
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    service = os.environ.get("OTEL_SERVICE_NAME", "metron")
    endpoint = os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"]

    resource = Resource(attributes={SERVICE_NAME: service})
    provider = TracerProvider(resource=resource)

    exporter = OTLPSpanExporter(
        endpoint=f"{endpoint}/v1/traces",
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    FlaskInstrumentor().instrument_app(
        app,
        excluded_urls="health,healthz,static",
    )


def _setup_metrics(app: Flask) -> None:
    global _meter

    from opentelemetry import metrics
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
        OTLPMetricExporter,
    )
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME

    service = os.environ.get("OTEL_SERVICE_NAME", "metron")
    endpoint = os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"]

    resource = Resource(attributes={SERVICE_NAME: service})

    exporter = OTLPMetricExporter(
        endpoint=f"{endpoint}/v1/metrics",
    )
    reader = PeriodicExportingMetricReader(
        exporter, export_interval_millis=30_000
    )
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(provider)

    _meter = metrics.get_meter("metron")

    # --- HTTP request metrics ---
    request_counter = _meter.create_counter(
        "http_requests_total",
        description="Total HTTP requests",
    )
    request_duration = _meter.create_histogram(
        "http_request_duration_seconds",
        description="HTTP request latency in seconds",
        unit="s",
    )
    active_requests = _meter.create_up_down_counter(
        "http_requests_active",
        description="Active in-flight HTTP requests",
    )

    # --- Business metrics ---
    _meter.create_counter(
        "portfolio_fetches_total",
        description="Portfolio data fetches from broker APIs",
    )
    _meter.create_histogram(
        "portfolio_fetch_duration_seconds",
        description="Time to fetch portfolio from broker",
        unit="s",
    )
    _meter.create_counter(
        "sheets_operations_total",
        description="Google Sheets CRUD operations",
    )
    _meter.create_counter(
        "broker_sync_total",
        description="Broker-to-Sheets sync operations",
    )
    _meter.create_counter(
        "external_api_calls_total",
        description="Calls to external APIs",
    )
    _meter.create_histogram(
        "external_api_duration_seconds",
        description="External API call latency",
        unit="s",
    )
    _meter.create_counter(
        "external_api_errors_total",
        description="Failed external API calls",
    )
    _meter.create_counter(
        "cache_hits_total",
        description="Cache hit count by cache type",
    )
    _meter.create_counter(
        "cache_misses_total",
        description="Cache miss count by cache type",
    )
    _meter.create_counter(
        "auth_events_total",
        description="Authentication events (login, logout, pin)",
    )
    _meter.create_counter(
        "cas_uploads_total",
        description="CAS PDF upload attempts",
    )
    _meter.create_counter(
        "exposure_analysis_total",
        description="Company exposure analysis runs",
    )
    _meter.create_counter(
        "errors_total",
        description="Application errors by category",
    )

    @app.before_request
    def _before() -> None:
        g._otel_start = time.perf_counter()
        active_requests.add(1)

    @app.after_request
    def _after(response):  # type: ignore[no-untyped-def]
        duration = time.perf_counter() - getattr(
            g, "_otel_start", time.perf_counter()
        )
        endpoint_name = request.endpoint or "unknown"
        attrs = {
            "http.method": request.method,
            "http.route": (
                request.url_rule.rule
                if request.url_rule
                else request.path
            ),
            "http.status_code": response.status_code,
            "http.endpoint": endpoint_name,
        }
        request_counter.add(1, attrs)
        request_duration.record(duration, attrs)
        active_requests.add(-1)
        return response


# --- Helper functions for recording business metrics ---


def record_external_api_call(
    api_name: str,
    duration: float,
    success: bool,
) -> None:
    """Record an external API call metric."""
    if _meter is None:
        return
    attrs = {"api.name": api_name, "api.success": str(success)}
    _meter.create_counter("external_api_calls_total").add(1, attrs)
    _meter.create_histogram("external_api_duration_seconds").record(
        duration, attrs
    )
    if not success:
        _meter.create_counter("external_api_errors_total").add(1, attrs)


def record_cache_event(
    cache_name: str,
    hit: bool,
) -> None:
    """Record a cache hit or miss."""
    if _meter is None:
        return
    attrs = {"cache.name": cache_name}
    if hit:
        _meter.create_counter("cache_hits_total").add(1, attrs)
    else:
        _meter.create_counter("cache_misses_total").add(1, attrs)


def record_auth_event(event_type: str, success: bool) -> None:
    """Record an authentication event (login, logout, pin_verify, etc.)."""
    if _meter is None:
        return
    attrs = {"auth.event": event_type, "auth.success": str(success)}
    _meter.create_counter("auth_events_total").add(1, attrs)


def record_portfolio_fetch(
    duration: float,
    accounts: int,
    success: bool,
) -> None:
    """Record a portfolio fetch from broker."""
    if _meter is None:
        return
    attrs = {
        "fetch.accounts": str(accounts),
        "fetch.success": str(success),
    }
    _meter.create_counter("portfolio_fetches_total").add(1, attrs)
    _meter.create_histogram("portfolio_fetch_duration_seconds").record(
        duration, attrs
    )


def record_sheets_operation(
    operation: str,
    sheet_type: str,
    success: bool,
) -> None:
    """Record a Google Sheets CRUD operation."""
    if _meter is None:
        return
    attrs = {
        "sheets.operation": operation,
        "sheets.type": sheet_type,
        "sheets.success": str(success),
    }
    _meter.create_counter("sheets_operations_total").add(1, attrs)


def record_error(category: str, endpoint: str) -> None:
    """Record an application error."""
    if _meter is None:
        return
    attrs = {"error.category": category, "error.endpoint": endpoint}
    _meter.create_counter("errors_total").add(1, attrs)


def _setup_log_export() -> None:
    from opentelemetry._logs import set_logger_provider
    from opentelemetry.exporter.otlp.proto.http._log_exporter import (
        OTLPLogExporter,
    )
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME

    service = os.environ.get("OTEL_SERVICE_NAME", "metron")
    endpoint = os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"]

    resource = Resource(attributes={SERVICE_NAME: service})
    log_provider = LoggerProvider(resource=resource)

    exporter = OTLPLogExporter(
        endpoint=f"{endpoint}/v1/logs",
    )
    log_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
    set_logger_provider(log_provider)

    otel_handler = LoggingHandler(
        level=logging.INFO,
        logger_provider=log_provider,
    )
    logging.getLogger().addHandler(otel_handler)
