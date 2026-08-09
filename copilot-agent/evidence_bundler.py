"""Deterministic evidence ranking and structuring for RootCauser."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class SpanEvidence(BaseModel):
    trace_id: str
    span_id: str
    name: str
    duration_ms: float
    is_error: bool = False
    relevance_score: int = 0
    relevance_reasons: list[str] = Field(default_factory=list)


class LogEvidence(BaseModel):
    timestamp: str
    severity: str
    body: str
    trace_id: str | None = None
    span_id: str | None = None
    relevance_score: int = 0
    relevance_reasons: list[str] = Field(default_factory=list)


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
    incident_context: dict[str, Any] | None = None,
) -> EvidenceBundle:
    """Build a ranked bundle from raw SigNoz trace, log, and metric records."""

    context = incident_context or {}
    keywords = _keywords(context.get("semantic_terms") or incident_keywords)
    alert_time = context.get("alert_timestamp") or alert_timestamp
    expected_service = context.get("service_name") or service_name
    health_alert = bool(context.get("is_health_alert"))
    normalized_logs = [_log_from_raw(log) for log in logs or []]
    log_trace_ids = {log.trace_id for log in normalized_logs if log.trace_id}
    log_span_ids = {log.span_id for log in normalized_logs if log.span_id}
    trace_counts = _trace_counts(traces or [])
    candidates: list[SpanEvidence] = []
    for raw in traces or []:
        span = _span_from_raw(raw)
        span.relevance_score, span.relevance_reasons = _span_score(
            span, raw, keywords, alert_time, expected_service, health_alert,
            log_trace_ids, log_span_ids, trace_counts,
        )
        candidates.append(span)
    spans = _select_diverse_spans(candidates)
    selected_trace_ids = {span.trace_id for span in spans if span.trace_id}
    selected_span_ids = {span.span_id for span in spans if span.span_id}
    for log in normalized_logs:
        log.relevance_score, log.relevance_reasons = _log_score(
            log, selected_trace_ids, selected_span_ids, alert_time
        )
    ranked_logs = sorted(normalized_logs, key=lambda log: (log.relevance_score, str(log.timestamp)), reverse=True)[:5]

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
    span_ids: set[str],
    alert_timestamp: str | int | float | None,
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    if log.trace_id and log.trace_id in trace_ids:
        score += 60
        reasons.append("trace_id matches selected span")
    if log.span_id and log.span_id in span_ids:
        score += 80
        reasons.append("span_id matches selected span")

    if log.severity == "ERROR":
        score += 30
        reasons.append("ERROR severity")
    elif log.severity in {"WARN", "WARNING"}:
        score += 20
        reasons.append("WARN severity")

    proximity = _temporal_proximity(log.timestamp, alert_timestamp)
    if proximity is not None:
        score += proximity
        reasons.append("near alert time")

    return score, reasons


def _keywords(values: list[str] | None) -> set[str]:
    terms: set[str] = set()
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
    alert_timestamp: str | int | float | None,
    service_name: str | None,
    health_alert: bool,
    log_trace_ids: set[str],
    log_span_ids: set[str],
    trace_counts: dict[str, int],
) -> tuple[int, list[str]]:
    """Rank incident evidence; correlation deliberately outweighs duration."""
    record = _unwrap_data(raw)
    name = span.name.lower()
    score = 0
    reasons: list[str] = []
    matches = [term for term in keywords if term in name]
    if matches:
        score += 35 * len(matches)
        reasons.append("alert semantic match: " + ", ".join(sorted(matches)))
    if not health_alert and any(term in name for term in ("health", "readiness", "liveness")):
        score -= 120
        reasons.append("routine health span penalty")
    if span.span_id and span.span_id in log_span_ids:
        score += 100
        reasons.append("correlated log span_id")
    elif span.trace_id and span.trace_id in log_trace_ids:
        score += 70
        reasons.append("correlated log trace_id")
    if span.trace_id and trace_counts.get(span.trace_id, 0) > 1:
        score += 20
        reasons.append("trace contains correlated spans")
    if span.is_error:
        score += 40
        reasons.append("error status")
    if span.duration_ms >= 1_000:
        score += 10
        reasons.append("long duration")
    elif span.duration_ms >= 100:
        score += 5
        reasons.append("elevated duration")
    record_service = str(record.get("service.name") or record.get("serviceName") or "")
    if service_name and record_service == service_name:
        score += 25
        reasons.append("service match")
    proximity = _temporal_proximity(record.get("timestamp"), alert_timestamp)
    if proximity is not None:
        score += proximity
        reasons.append("near alert time")
    return score, reasons


def _select_diverse_spans(spans: list[SpanEvidence]) -> list[SpanEvidence]:
    selected: list[SpanEvidence] = []
    seen: set[tuple[str, str, str, float]] = set()
    per_trace: dict[str, int] = {}
    for span in sorted(spans, key=lambda item: (item.relevance_score, item.duration_ms), reverse=True):
        signature = (span.trace_id, span.span_id, span.name, span.duration_ms)
        if signature in seen or per_trace.get(span.trace_id, 0) >= 2:
            continue
        seen.add(signature)
        per_trace[span.trace_id] = per_trace.get(span.trace_id, 0) + 1
        selected.append(span)
        if len(selected) == 5:
            break
    return selected


def _trace_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        trace_id = _first(_unwrap_data(record), "traceID", "trace_id", "traceId")
        if trace_id:
            counts[str(trace_id)] = counts.get(str(trace_id), 0) + 1
    return counts


def _temporal_proximity(value: Any, alert_value: Any) -> int | None:
    timestamp, alert_timestamp = _parse_timestamp(value), _parse_timestamp(alert_value)
    if timestamp is None or alert_timestamp is None:
        return None
    seconds = abs((timestamp - alert_timestamp).total_seconds())
    if seconds <= 60:
        return 30
    if seconds <= 300:
        return 15
    return 0


def _parse_timestamp(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            numeric = float(value)
            return datetime.fromtimestamp(
                numeric / 1000 if numeric > 1e12 else numeric, tz=UTC
            )
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError, OSError):
        return None


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
