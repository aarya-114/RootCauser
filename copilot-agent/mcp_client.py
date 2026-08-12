"""SigNoz REST client used by the RootCauser investigation pipeline."""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from typing import Any

import requests
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()

_BASE_URL = os.environ.get("SIGNOZ_BASE_URL", "http://localhost:8080").rstrip("/")
_API_KEY = os.environ.get("SIGNOZ_API_KEY", "")
_QUERY_RANGE_URL = f"{_BASE_URL}/api/v5/query_range"
_RULES_URL = f"{_BASE_URL}/api/v2/rules"
_RETRY_DELAY_SECONDS = 2.0
MAX_METRIC_SERIES = 20
MAX_METRIC_POINTS = 200


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if _API_KEY:
        headers["SIGNOZ-API-KEY"] = _API_KEY
    return headers


def _to_epoch_ms(dt: datetime | int | float) -> int:
    if isinstance(dt, datetime):
        return int(dt.timestamp() * 1000)
    value = float(dt)
    return int(value if value > 1e12 else value * 1000)


def _post_with_retry(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    for attempt in (1, 2):
        try:
            response = requests.post(url, json=payload, headers=_headers(), timeout=30)
            if response.status_code >= 400:
                logger.error(
                    "SigNoz POST failed: status=%s body=%s", response.status_code, response.text
                )
            response.raise_for_status()
            return response.json()
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
            if attempt == 1:
                logger.warning("SigNoz POST failed (attempt 1/2): %s; retrying", exc)
                time.sleep(_RETRY_DELAY_SECONDS)
                continue
            logger.error("SigNoz POST failed on both attempts: %s", exc)
            raise
    raise RuntimeError("Unexpected retry state")


def _get_with_retry(url: str) -> dict[str, Any]:
    for attempt in (1, 2):
        try:
            response = requests.get(url, headers=_headers(), timeout=30)
            if response.status_code >= 400:
                logger.error(
                    "SigNoz GET failed: status=%s body=%s", response.status_code, response.text
                )
            response.raise_for_status()
            return response.json()
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
            if attempt == 1:
                logger.warning("SigNoz GET failed (attempt 1/2): %s; retrying", exc)
                time.sleep(_RETRY_DELAY_SECONDS)
                continue
            logger.error("SigNoz GET failed on both attempts: %s", exc)
            raise
    raise RuntimeError("Unexpected retry state")


def query_traces(
    service_name: str,
    start_time: datetime | int | float,
    end_time: datetime | int | float,
    min_duration_ms: int | None = None,
) -> list[dict[str, Any]]:
    start_ms, end_ms = _to_epoch_ms(start_time), _to_epoch_ms(end_time)
    filters = [f"service.name = '{service_name}'"]
    if min_duration_ms is not None:
        filters.append(f"durationNano >= {min_duration_ms * 1_000_000}")
    payload = _raw_payload(
        "traces",
        start_ms,
        end_ms,
        " AND ".join(filters),
        [
            {"name": field, "fieldContext": context}
            for field, context in (
                ("service.name", "resource"),
                ("name", "span"),
                ("durationNano", "span"),
                ("statusCode", "span"),
                ("traceID", "span"),
                ("spanID", "span"),
                ("timestamp", "span"),
            )
        ],
    )
    rows = _extract_list(_post_with_retry(_QUERY_RANGE_URL, payload), "traces")
    normalized = [_normalize_trace(row) for row in rows]
    logger.info(
        "SigNoz traces: service=%s raw=%d normalized=%d", service_name, len(rows), len(normalized)
    )
    return normalized


def query_logs(
    service_name: str,
    start_time: datetime | int | float,
    end_time: datetime | int | float,
    severity: str | None = None,
) -> list[dict[str, Any]]:
    start_ms, end_ms = _to_epoch_ms(start_time), _to_epoch_ms(end_time)
    filters = [f"service.name = '{service_name}'"]
    if severity:
        logger.info(
            "SigNoz log severity filter omitted because this deployment "
            "does not support JSON* extraction"
        )
    payload = _raw_payload(
        "logs",
        start_ms,
        end_ms,
        " AND ".join(filters),
        [],
    )
    # Let SigNoz return its native raw-log columns. Selecting severityText causes
    # JSON_VALUE/JSON_EXISTS in older ClickHouse-backed SigNoz installations.
    payload["compositeQuery"]["queries"][0]["spec"].pop("selectFields", None)
    try:
        rows = _extract_list(_post_with_retry(_QUERY_RANGE_URL, payload), "logs")
    except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
        logger.warning("SigNoz log query failed; continuing investigation without logs: %s", exc)
        return []
    normalized = [_normalize_log(row) for row in rows]
    logger.info(
        "SigNoz logs: service=%s raw=%d normalized=%d", service_name, len(rows), len(normalized)
    )
    return normalized


def query_metrics(
    service_name: str,
    metric_name: str,
    start_time: datetime | int | float,
    end_time: datetime | int | float,
) -> list[dict[str, Any]]:
    start_ms, end_ms = _to_epoch_ms(start_time), _to_epoch_ms(end_time)
    step_s = max(60, (end_ms - start_ms) // 100_000)
    payload: dict[str, Any] = {
        "start": start_ms,
        "end": end_ms,
        "requestType": "time_series",
        "variables": {},
        "compositeQuery": {
            "queries": [
                {
                    "type": "builder_query",
                    "spec": {
                        "name": "A",
                        "signal": "metrics",
                        "stepInterval": step_s,
                        "aggregations": [
                            {
                                "metricName": metric_name,
                                "timeAggregation": "avg",
                                "spaceAggregation": "sum",
                            }
                        ],
                        "filter": {"expression": f"service.name = '{service_name}'"},
                        "groupBy": [],
                        "disabled": False,
                    },
                }
            ]
        },
    }
    response = _post_with_retry(_QUERY_RANGE_URL, payload)
    series = _extract_series(response)
    normalized = [_normalize_series(item, metric_name) for item in series[:MAX_METRIC_SERIES]]
    points = sum(len(item["points"]) for item in normalized)
    if not normalized or not points:
        logger.info(
            "SigNoz metric query returned no usable data: service=%s metric=%s",
            service_name,
            metric_name,
        )
    logger.info(
        "SigNoz metrics: service=%s metric=%s series=%d points=%d",
        service_name,
        metric_name,
        len(normalized),
        points,
    )
    return normalized


def get_alert_details(alert_id: str) -> dict[str, Any]:
    """Get a SigNoz v2 alert rule. Alert identifiers are UUIDs, not numeric IDs."""
    data = _get_with_retry(f"{_RULES_URL}/{alert_id}")
    return data.get("data", data) if isinstance(data, dict) else {}


def _raw_payload(
    signal: str, start_ms: int, end_ms: int, expression: str, select_fields: list[dict[str, str]]
) -> dict[str, Any]:
    return {
        "start": start_ms,
        "end": end_ms,
        "requestType": "raw",
        "variables": {},
        "compositeQuery": {
            "queries": [
                {
                    "type": "builder_query",
                    "spec": {
                        "name": "A",
                        "signal": signal,
                        "filter": {"expression": expression},
                        "selectFields": select_fields,
                        "order": [{"key": {"name": "timestamp"}, "direction": "desc"}],
                        "limit": 100,
                        "offset": 0,
                        "disabled": False,
                    },
                }
            ]
        },
    }


def _results(response: dict[str, Any]) -> list[Any]:
    current: Any = response
    for key in ("data", "data", "results"):
        if not isinstance(current, dict) or key not in current:
            logger.warning(
                "Unsupported SigNoz response shape: top_level_keys=%s response=%r",
                list(response) if isinstance(response, dict) else type(response).__name__,
                response,
            )
            return []
        current = current[key]
    return current if isinstance(current, list) else []


def _extract_list(response: dict[str, Any], signal: str) -> list[dict[str, Any]]:
    results = _results(response)
    rows: list[dict[str, Any]] = []
    for result in results:
        if isinstance(result, dict) and isinstance(result.get("rows"), list):
            rows.extend(item for item in result["rows"] if isinstance(item, dict))
    if not rows and results:
        logger.warning("Unsupported SigNoz %s result shape: %r", signal, results[:1])
    return rows


def _extract_series(response: dict[str, Any]) -> list[dict[str, Any]]:
    results = _results(response)
    series: list[dict[str, Any]] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        # SigNoz v5 metric builder responses place time series beneath each
        # aggregation: results[].aggregations[].series[].values[].
        aggregations = result.get("aggregations")
        if isinstance(aggregations, list):
            for aggregation in aggregations:
                if not isinstance(aggregation, dict):
                    continue
                aggregation_series = aggregation.get("series")
                if not isinstance(aggregation_series, list):
                    continue
                for item in aggregation_series:
                    if isinstance(item, dict):
                        series.append(
                            {
                                **item,
                                "queryName": result.get("queryName"),
                                "aggregationAlias": aggregation.get("alias"),
                                "aggregationMeta": aggregation.get("meta", {}),
                            }
                        )
            continue
        candidates = result.get("series") or result.get("data") or result.get("values")
        if isinstance(candidates, list):
            series.extend(item for item in candidates if isinstance(item, dict))
        elif "values" in result or "points" in result:
            series.append(result)
    if not series and results:
        logger.warning("Unsupported SigNoz metric result shape: %r", results[:1])
    else:
        logger.debug("SigNoz metric response normalized into %d raw series", len(series))
    return series


def _unwrap(row: dict[str, Any]) -> dict[str, Any]:
    data = row.get("data")
    if isinstance(data, dict):
        return {**row, **data}
    return row


def _value(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if row.get(key) not in (None, ""):
            return row[key]
    return None


def _normalize_trace(row: dict[str, Any]) -> dict[str, Any]:
    record = _unwrap(row)
    return {
        "traceID": _value(record, "traceID", "traceId", "trace_id") or "",
        "spanID": _value(record, "spanID", "spanId", "span_id") or "",
        "name": _value(record, "name", "spanName", "operationName") or "unknown-span",
        "durationNano": _value(record, "durationNano", "duration_nano", "duration") or 0,
        "service.name": _value(record, "service.name", "serviceName")
        or _resource_value(record, "service.name"),
        "timestamp": _value(record, "timestamp", "startTime", "start_time") or "",
        "statusCode": _value(record, "statusCode", "status_code", "status") or "",
    }


def _normalize_log(row: dict[str, Any]) -> dict[str, Any]:
    record = _unwrap(row)
    return {
        "body": _value(record, "body", "message", "msg") or "",
        "severityText": _value(record, "severityText", "severity_text", "severity", "level")
        or "INFO",
        "traceID": _value(record, "traceID", "traceId", "trace_id") or "",
        "spanID": _value(record, "spanID", "spanId", "span_id") or "",
        "timestamp": _value(record, "timestamp", "time", "observedTimestamp") or "",
        "resources_string": _value(record, "resources_string") or "",
        "attributes_string": _value(record, "attributes_string") or "",
        "attributes_number": _value(record, "attributes_number") or {},
    }


def _normalize_series(raw: dict[str, Any], requested_name: str) -> dict[str, Any]:
    record = _unwrap(raw)
    labels: dict[str, Any] = {}
    for candidate in (
        record.get("metric"),
        record.get("metadata"),
        record.get("labels"),
        record.get("aggregationMeta"),
    ):
        if isinstance(candidate, dict):
            labels.update(candidate)
    name = (
        _value(record, "name", "metricName", "metric_name")
        or labels.get("__name__")
        or labels.get("metricName")
        or requested_name
    )
    points = record.get("points") or record.get("values") or record.get("data") or []
    if isinstance(points, dict):
        points = points.get("values") or points.get("points") or []
    if not isinstance(points, list):
        logger.warning("Unsupported SigNoz metric series shape: %r", raw)
        points = []
    return {
        "name": str(name),
        "labels": labels,
        "points": points[:MAX_METRIC_POINTS],
    }


def _resource_value(row: dict[str, Any], key: str) -> Any:
    resource = row.get("resource") or row.get("resources")
    return resource.get(key) if isinstance(resource, dict) else None
