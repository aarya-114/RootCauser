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
) -> EvidenceBundle:
    """Build a ranked bundle from raw SigNoz trace, log, and metric records."""
    spans = sorted(
        (_span_from_raw(span) for span in traces or []),
        key=lambda span: (span.is_error, span.duration_ms),
        reverse=True,
    )[:5]

    span_trace_ids = {span.trace_id for span in spans if span.trace_id}
    ranked_logs = sorted(
        (_log_from_raw(log) for log in logs or []),
        key=lambda log: (_log_score(log, span_trace_ids), str(log.timestamp)),
        reverse=True,
    )[:5]

    metric_series = [_metric_from_raw(metric) for metric in metrics or []]

    return EvidenceBundle(spans=spans, logs=ranked_logs, metrics=metric_series)


def _span_from_raw(raw: dict[str, Any]) -> SpanEvidence:
    trace_id = _first(raw, "traceID", "trace_id", "traceId", "trace_id_hex") or ""
    span_id = _first(raw, "spanID", "span_id", "spanId", "span_id_hex") or ""
    duration = (
        _first(raw, "durationMs", "duration_ms", "durationNano", "duration_nano", "duration") or 0
    )
    duration_ms = _duration_to_ms(duration)
    status = str(_first(raw, "statusCode", "status_code", "status", "statusMessage") or "").lower()
    name = str(_first(raw, "name", "spanName", "operationName") or "unknown-span")
    is_error = "error" in status or bool(_first(raw, "hasError", "is_error", "error"))
    return SpanEvidence(
        trace_id=str(trace_id),
        span_id=str(span_id),
        name=name,
        duration_ms=duration_ms,
        is_error=is_error,
    )


def _log_from_raw(raw: dict[str, Any]) -> LogEvidence:
    body = _first(raw, "body", "message", "msg", "log") or raw.get("resources_string", "")
    if isinstance(body, (dict, list)):
        body = json.dumps(body, sort_keys=True)
    return LogEvidence(
        timestamp=str(_first(raw, "timestamp", "time", "observedTimestamp", "ts") or ""),
        severity=str(
            _first(raw, "severityText", "severity_text", "severity", "level") or "INFO"
        ).upper(),
        body=str(body),
        trace_id=_optional_str(_first(raw, "traceID", "trace_id", "traceId")),
        span_id=_optional_str(_first(raw, "spanID", "span_id", "spanId")),
    )


def _metric_from_raw(raw: dict[str, Any]) -> MetricSeries:
    labels = raw.get("metric") if isinstance(raw.get("metric"), dict) else {}
    name = str(
        raw.get("name")
        or labels.get("__name__")
        or labels.get("metric_name")
        or labels.get("metricName")
        or "unknown-metric"
    )
    points = [_point_from_raw(value) for value in raw.get("values", [])]
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
    if isinstance(raw, dict):
        timestamp = raw.get("timestamp") or raw.get("time") or raw.get("ts") or ""
        value = raw.get("value", 0)
    elif isinstance(raw, (list, tuple)) and len(raw) >= 2:
        timestamp, value = raw[0], raw[1]
    else:
        timestamp, value = "", 0
    return MetricPoint(timestamp=timestamp, value=float(value))


def _log_score(log: LogEvidence, trace_ids: set[str]) -> int:
    score = 0
    if log.trace_id and log.trace_id in trace_ids:
        score += 10
    if log.severity == "ERROR":
        score += 5
    elif log.severity in {"WARN", "WARNING"}:
        score += 3
    return score


def _duration_to_ms(value: Any) -> float:
    numeric = float(value)
    return numeric / 1_000_000 if numeric > 1_000_000 else numeric


def _first(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in raw and raw[key] not in (None, ""):
            return raw[key]
    return None


def _optional_str(value: Any) -> str | None:
    return None if value in (None, "") else str(value)
