"""
RootCauser Demo Service — OpenTelemetry Configuration
======================================================
Centralised setup for TracerProvider, MeterProvider, and LoggerProvider.
All three export via OTLP (gRPC) to the OTel Collector whose address is
read from the OTEL_EXPORTER_OTLP_ENDPOINT environment variable.

Usage:
    Call ``init_telemetry()`` once at application startup (before any
    requests are served).  The function is idempotent — repeated calls
    are harmless.
"""

import os
import logging

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter

# ---------------------------------------------------------------------------
# Module-level flag to prevent double-initialisation
# ---------------------------------------------------------------------------
_initialised = False

# Service identity attached to every piece of telemetry
SERVICE = "demo-service"


def init_telemetry() -> None:
    """
    Configure and install the three OTel providers (traces, metrics, logs).

    The OTLP endpoint defaults to ``http://otel-collector:4317`` when
    ``OTEL_EXPORTER_OTLP_ENDPOINT`` is not set, which matches the
    Docker Compose network layout.
    """
    global _initialised
    if _initialised:
        return

    endpoint = os.environ.get(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://otel-collector:4317",
    )

    resource = Resource.create({SERVICE_NAME: SERVICE})

    # ── Traces ───────────────────────────────────────────────────────────
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )
    trace.set_tracer_provider(tracer_provider)

    # ── Metrics ──────────────────────────────────────────────────────────
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=endpoint, insecure=True),
        export_interval_millis=15_000,
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    # ── Logs ─────────────────────────────────────────────────────────────
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint, insecure=True))
    )

    # Bridge Python's stdlib logging → OTel log pipeline
    handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
    logging.getLogger().addHandler(handler)

    _initialised = True
