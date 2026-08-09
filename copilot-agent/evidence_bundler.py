"""Deterministic evidence ranking and structuring for RootCauser."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field


class SpanEvidence(BaseModel):
    trace_id: str
    span_id: str
    name: str
    duration_ms: float
    is_error: bool = False


class LogEvidence(BaseModel):
    timestamp: str
    severity: str
    body: str
    trace_id: str | None = None
    span_id: str | None = None


class MetricPoint(BaseModel):
    timestamp: str | int | float
    value: float


class MetricSeries(BaseModel):
    name: str
    labels: dict[str, Any] = Field(default_factory=dict)
    points: list[MetricPoint] = Field(default_factory=list)
    min_value: float | None = None
    max_value: float | None = None
    anomaly_point: MetricPoint | None = None


class EvidenceBundle(BaseModel):
    spans: list[SpanEvidence] = Field(default_factory=list)
    logs: list[LogEvidence] = Field(default_factory=list)
    metrics: list[MetricSeries] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return (
            not self.spans and not self.logs and not any(metric.points for metric in self.metrics)
        )

    def searchable_text(self) -> str:
        """Return stable JSON text used for literal citation validation."""
        return json.dumps(self.model_dump(mode="json"), sort_keys=True)


def build_evidence_bundle(
    traces: list[dict[str, Any]] | None,
    logs: list[dict[str, Any]] | None,
    metrics: list[dict[str, Any]] | None,
    incident_keywords: list[str] | None = None,
    alert_timestamp: str | None = None,
    service_name: str | None = None,
) -> EvidenceBundle:
    """Build a ranked bundle from raw SigNoz trace, log, and metric records."""

    raw_traces = traces or []
    keywords = _keywords(incident_keywords)
    spans = [(_span_from_raw(span), span) for span in raw_traces]
    spans.sort(
        key=lambda item: _span_score(item[0], item[1], keywords, alert_timestamp, service_name),
        reverse=True,
    )
    spans = [span for span, _ in spans[:5]]

    span_trace_ids = {span.trace_id for span in spans if span.trace_id}

    ranked_logs = sorted(
        (_log_from_raw(log) for log in logs or []),
        key=lambda log: (
            _log_score(log, span_trace_ids),
            str(log.timestamp),
        ),
        reverse=True,
    )[:5]

    metric_series = [_metric_from_raw(metric) for metric in metrics or []]

    return EvidenceBundle(
        spans=spans,
        logs=ranked_logs,
        metrics=metric_series,
    )


def _unwrap_data(raw: dict[str, Any]) -> dict[str, Any]:
    """
    SigNoz query_range records can wrap the actual record inside `data`.

    Example:

        {
            "data": {
                "traceID": "...",
                "spanID": "...",
                "name": "GET /orders"
            },
            "timestamp": "..."
        }

    Return the inner record when present.
    """
    data = raw.get("data")

    if isinstance(data, dict):
        # Retain outer timestamp and resource fields when only the record is nested.
        return {**raw, **data}

    return raw


def _span_from_raw(raw: dict[str, Any]) -> SpanEvidence:
    """Convert a raw SigNoz trace record into normalized span evidence."""

    raw = _unwrap_data(raw)

    trace_id = (
        _first(
            raw,
            "traceID",
            "trace_id",
            "traceId",
            "trace_id_hex",
        )
        or ""
    )

    span_id = (
        _first(
            raw,
            "spanID",
            "span_id",
            "spanId",
            "span_id_hex",
        )
        or ""
    )

    duration = (
        _first(
            raw,
            "durationMs",
            "duration_ms",
            "durationNano",
            "duration_nano",
            "duration",
        )
        or 0
    )

    duration_ms = _duration_to_ms(duration)

    status = str(
        _first(
            raw,
            "statusCode",
            "status_code",
            "status",
            "statusMessage",
        )
        or ""
    ).lower()

    name = str(
        _first(
            raw,
            "name",
            "spanName",
            "operationName",
        )
        or "unknown-span"
    )

    is_error = "error" in status or bool(
        _first(
            raw,
            "hasError",
            "is_error",
            "error",
        )
    )

    return SpanEvidence(
        trace_id=str(trace_id),
        span_id=str(span_id),
        name=name,
        duration_ms=duration_ms,
        is_error=is_error,
    )


def _log_from_raw(raw: dict[str, Any]) -> LogEvidence:
    """Convert a raw SigNoz log record into normalized log evidence."""

    raw = _unwrap_data(raw)

    body = _first(
        raw,
        "body",
        "message",
        "msg",
        "log",
    )

    if body is None:
        body = raw.get("attributes_string") or raw.get("resources_string", "")

    if isinstance(body, (dict, list)):
        body = json.dumps(body, sort_keys=True)

    return LogEvidence(
        timestamp=str(
            _first(
                raw,
                "timestamp",
                "time",
                "observedTimestamp",
                "ts",
            )
            or ""
        ),
        severity=str(
            _first(
                raw,
                "severityText",
                "severity_text",
                "severity",
                "level",
            )
            or "INFO"
        ).upper(),
        body=str(body),
        trace_id=_optional_str(
            _first(
                raw,
                "traceID",
                "trace_id",
                "traceId",
            )
        ),
        span_id=_optional_str(
            _first(
                raw,
                "spanID",
                "span_id",
                "spanId",
            )
        ),
    )


def _metric_from_raw(raw: dict[str, Any]) -> MetricSeries:
    """
    Normalize a metric record.

    Supports the existing RootCauser metric shape and a few common
    SigNoz response shapes.
    """

    # Some responses may wrap the metric inside `data`.
    raw = _unwrap_data(raw)

    labels: dict[str, Any] = {}

    if isinstance(raw.get("metric"), dict):
        labels = raw["metric"].copy()

    # Some metric responses expose labels directly.
    if isinstance(raw.get("labels"), dict):
        labels.update(raw["labels"])

    name = str(
        raw.get("name")
        or raw.get("metricName")
        or raw.get("metric_name")
        or labels.get("__name__")
        or labels.get("metricName")
        or labels.get("metric_name")
        or "unknown-metric"
    )

    raw_values = raw.get("values") or raw.get("points") or raw.get("data") or []

    # Avoid treating an unexpected dictionary as a list of values.
    if isinstance(raw_values, dict):
        raw_values = []

    points = [_point_from_raw(value) for value in raw_values]

    # Remove invalid/empty points.
    points = [point for point in points if point.timestamp != "" or point.value != 0]

    values = [point.value for point in points]

    max_point = max(points, key=lambda point: point.value) if points else None

    return MetricSeries(
        name=name,
        labels=labels,
        points=points,
        min_value=min(values) if values else None,
        max_value=max(values) if values else None,
        anomaly_point=max_point,
    )


def _point_from_raw(raw: Any) -> MetricPoint:
    """Normalize one metric datapoint."""

    if isinstance(raw, dict):
        timestamp = raw.get("timestamp") or raw.get("time") or raw.get("ts") or ""

        value = raw.get(
            "value",
            raw.get("val", 0),
        )

    elif isinstance(raw, (list, tuple)) and len(raw) >= 2:
        timestamp = raw[0]
        value = raw[1]

    else:
        timestamp = ""
        value = 0

    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        numeric_value = 0.0

    return MetricPoint(
        timestamp=timestamp,
        value=numeric_value,
    )


def _log_score(
    log: LogEvidence,
    trace_ids: set[str],
) -> int:
    score = 0

    if log.trace_id and log.trace_id in trace_ids:
        score += 10

    if log.severity == "ERROR":
        score += 5
    elif log.severity in {"WARN", "WARNING"}:
        score += 3

    return score


def _keywords(values: list[str] | None) -> set[str]:
    terms = {"slow", "query", "db", "orders", "error", "downstream", "api"}
    for value in values or []:
        terms.update(
            token
            for token in str(value).lower().replace(".", " ").replace("/", " ").split()
            if len(token) > 1
        )
    return terms


def _span_score(
    span: SpanEvidence,
    raw: dict[str, Any],
    keywords: set[str],
    alert_timestamp: str | None,
    service_name: str | None,
) -> tuple[int, float, str]:
    """Rank incident evidence, not merely the longest span in the window."""
    record = _unwrap_data(raw)
    name = span.name.lower()
    score = 0
    score += 30 * sum(term in name for term in keywords)
    if any(term in name for term in ("health", "readiness", "liveness")):
        score -= 120
    if span.is_error:
        score += 35
    if span.duration_ms >= 1_000:
        score += 20
    elif span.duration_ms >= 100:
        score += 8
    record_service = str(record.get("service.name") or record.get("serviceName") or "")
    if service_name and record_service == service_name:
        score += 10
    # Timestamp is a stable tie breaker; raw query is already bounded to the incident window.
    if alert_timestamp and str(record.get("timestamp", "")) == str(alert_timestamp):
        score += 5
    return score, span.duration_ms, span.span_id


def _duration_to_ms(value: Any) -> float:
    """
    Convert duration to milliseconds.

    SigNoz commonly returns durationNano for spans.
    """

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0

    if numeric > 1_000_000:
        return numeric / 1_000_000

    return numeric


def _first(
    raw: dict[str, Any],
    *keys: str,
) -> Any:
    """Return the first non-empty value for the supplied keys."""

    for key in keys:
        if key in raw and raw[key] not in (None, ""):
            return raw[key]

    return None


def _optional_str(value: Any) -> str | None:
    if value in (None, ""):
        return None

    return str(value)
