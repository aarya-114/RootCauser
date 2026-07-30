"""
RootCauser MCP Client — ADR-04 REST Fallback
=============================================
Investigation Summary
---------------------
The local self-hosted SigNoz (v0.134.0) deployment does not expose a usable
MCP endpoint. Requests to /mcp return the frontend HTML rather than an MCP
protocol response.

Per ADR-04, this client uses the documented SigNoz REST API internally while
preserving the same public interface so that a future migration to a real MCP
server requires no downstream changes.

Public API
----------
    query_traces(service_name, start_time, end_time, min_duration_ms=None)
    query_logs(service_name, start_time, end_time, severity=None)
    query_metrics(service_name, metric_name, start_time, end_time)
    get_alert_details(alert_id)

Configuration (environment variables)
--------------------------------------
    SIGNOZ_BASE_URL   Base URL of the SigNoz instance, e.g. http://localhost:8080
    SIGNOZ_API_KEY    Service-account API key generated in SigNoz Settings
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from typing import Any

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — read once at import time so callers do not need to pass
# credentials on every call.
# ---------------------------------------------------------------------------
_BASE_URL: str = os.environ.get("SIGNOZ_BASE_URL", "http://localhost:8080").rstrip("/")
_API_KEY: str = os.environ.get("SIGNOZ_API_KEY", "")

# Retry policy
_RETRY_DELAY_SECONDS: float = 2.0

# SigNoz v5 query endpoint (composite query builder)
_QUERY_RANGE_URL: str = f"{_BASE_URL}/api/v5/query_range"

# SigNoz v1 alert-rules endpoint
_RULES_URL: str = f"{_BASE_URL}/api/v1/rules"


def _headers() -> dict[str, str]:
    """Return HTTP headers required by the SigNoz REST API."""
    h: dict[str, str] = {"Content-Type": "application/json", "Accept": "application/json"}
    if _API_KEY:
        h["SIGNOZ-API-KEY"] = _API_KEY
    return h


def _to_epoch_ms(dt: datetime | int | float) -> int:
    """
    Normalise *dt* to an integer Unix timestamp in milliseconds.

    Accepts:
        - a timezone-aware ``datetime`` object
        - a numeric Unix timestamp in seconds (int or float)
        - an integer already in milliseconds (detected when > 1e12)
    """
    if isinstance(dt, datetime):
        return int(dt.timestamp() * 1000)
    numeric = float(dt)
    # Heuristic: values larger than 1e12 are already in milliseconds
    return int(numeric) if numeric > 1e12 else int(numeric * 1000)


def _post_with_retry(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    """
    POST *payload* to *url*, retrying once after ``_RETRY_DELAY_SECONDS`` on
    any connection or HTTP error.

    Returns:
        Parsed JSON response as a Python dict.

    Raises:
        requests.HTTPError: if both attempts fail with a non-2xx status code.
        requests.ConnectionError / requests.Timeout: if both attempts raise a
            network-level error.
    """
    for attempt in (1, 2):
        try:
            response = requests.post(url, json=payload, headers=_headers(), timeout=30)
            response.raise_for_status()
            return response.json()
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
            if attempt == 1:
                logger.warning(
                    "SigNoz POST %s failed (attempt %d/2): %s — retrying in %.0fs",
                    url,
                    attempt,
                    exc,
                    _RETRY_DELAY_SECONDS,
                )
                time.sleep(_RETRY_DELAY_SECONDS)
            else:
                logger.error("SigNoz POST %s failed on both attempts: %s", url, exc)
                raise


def _get_with_retry(url: str) -> dict[str, Any]:
    """
    GET *url*, retrying once after ``_RETRY_DELAY_SECONDS`` on any error.

    Returns:
        Parsed JSON response as a Python dict.
    """
    for attempt in (1, 2):
        try:
            response = requests.get(url, headers=_headers(), timeout=30)
            response.raise_for_status()
            return response.json()
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
            if attempt == 1:
                logger.warning(
                    "SigNoz GET %s failed (attempt %d/2): %s — retrying in %.0fs",
                    url,
                    attempt,
                    exc,
                    _RETRY_DELAY_SECONDS,
                )
                time.sleep(_RETRY_DELAY_SECONDS)
            else:
                logger.error("SigNoz GET %s failed on both attempts: %s", url, exc)
                raise


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def query_traces(
    service_name: str,
    start_time: datetime | int | float,
    end_time: datetime | int | float,
    min_duration_ms: int | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch trace spans for *service_name* within the given time window.

    Args:
        service_name:    OTel service.name attribute value (e.g. "demo-service").
        start_time:      Window start — datetime or Unix timestamp (s or ms).
        end_time:        Window end   — datetime or Unix timestamp (s or ms).
        min_duration_ms: Optional lower bound on span duration in milliseconds.

    Returns:
        List of span dicts as returned by SigNoz, extracted from
        ``result[0].list`` in the API response.  Empty list if no data.
    """
    start_ms = _to_epoch_ms(start_time)
    end_ms = _to_epoch_ms(end_time)

    filters: list[dict[str, Any]] = [
        {
            "key": {"key": "serviceName", "type": "tag", "dataType": "string", "isColumn": True},
            "op": "=",
            "value": service_name,
        }
    ]
    if min_duration_ms is not None:
        filters.append(
            {
                "key": {
                    "key": "durationNano",
                    "type": "tag",
                    "dataType": "int64",
                    "isColumn": True,
                },
                "op": ">=",
                "value": min_duration_ms * 1_000_000,  # ms → ns
            }
        )

    payload: dict[str, Any] = {
        "start": start_ms,
        "end": end_ms,
        "step": 60,
        "variables": {},
        "compositeQuery": {
            "queryType": "builder",
            "panelType": "list",
            "builderQueries": {
                "A": {
                    "dataSource": "traces",
                    "queryName": "A",
                    "aggregateOperator": "noop",
                    "aggregateAttribute": {},
                    "filters": {"op": "AND", "items": filters},
                    "orderBy": [{"columnName": "timestamp", "order": "desc"}],
                    "limit": 100,
                    "offset": 0,
                    "pageSize": 100,
                }
            },
        },
    }

    logger.debug("query_traces: service=%s start=%d end=%d", service_name, start_ms, end_ms)
    data = _post_with_retry(_QUERY_RANGE_URL, payload)
    return _extract_list(data)


def query_logs(
    service_name: str,
    start_time: datetime | int | float,
    end_time: datetime | int | float,
    severity: str | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch log records for *service_name* within the given time window.

    Args:
        service_name: OTel service.name attribute value.
        start_time:   Window start — datetime or Unix timestamp (s or ms).
        end_time:     Window end   — datetime or Unix timestamp (s or ms).
        severity:     Optional severity level filter, e.g. "ERROR", "WARN".
                      Case-insensitive; mapped to SigNoz ``severityText``.

    Returns:
        List of log record dicts. Empty list if no data.
    """
    start_ms = _to_epoch_ms(start_time)
    end_ms = _to_epoch_ms(end_time)

    filters: list[dict[str, Any]] = [
        {
            "key": {
                "key": "serviceName",
                "type": "resource",
                "dataType": "string",
                "isColumn": False,
            },
            "op": "=",
            "value": service_name,
        }
    ]
    if severity is not None:
        filters.append(
            {
                "key": {
                    "key": "severityText",
                    "type": "tag",
                    "dataType": "string",
                    "isColumn": True,
                },
                "op": "=",
                "value": severity.upper(),
            }
        )

    payload: dict[str, Any] = {
        "start": start_ms,
        "end": end_ms,
        "step": 60,
        "variables": {},
        "compositeQuery": {
            "queryType": "builder",
            "panelType": "list",
            "builderQueries": {
                "A": {
                    "dataSource": "logs",
                    "queryName": "A",
                    "aggregateOperator": "noop",
                    "aggregateAttribute": {},
                    "filters": {"op": "AND", "items": filters},
                    "orderBy": [{"columnName": "timestamp", "order": "desc"}],
                    "limit": 100,
                    "offset": 0,
                    "pageSize": 100,
                }
            },
        },
    }

    logger.debug(
        "query_logs: service=%s severity=%s start=%d end=%d",
        service_name,
        severity,
        start_ms,
        end_ms,
    )
    data = _post_with_retry(_QUERY_RANGE_URL, payload)
    return _extract_list(data)


def query_metrics(
    service_name: str,
    metric_name: str,
    start_time: datetime | int | float,
    end_time: datetime | int | float,
) -> list[dict[str, Any]]:
    """
    Fetch time-series data for *metric_name* scoped to *service_name*.

    Args:
        service_name: OTel service.name label value used to filter the metric.
        metric_name:  Metric instrument name, e.g. "db.query.duration".
        start_time:   Window start — datetime or Unix timestamp (s or ms).
        end_time:     Window end   — datetime or Unix timestamp (s or ms).

    Returns:
        List of time-series result dicts, each containing ``metric`` labels
        and ``values`` (timestamp, value) pairs.  Empty list if no data.
    """
    start_ms = _to_epoch_ms(start_time)
    end_ms = _to_epoch_ms(end_time)
    step_s = max(60, (end_ms - start_ms) // (1000 * 100))  # ≤100 data points

    payload: dict[str, Any] = {
        "start": start_ms,
        "end": end_ms,
        "step": step_s,
        "variables": {},
        "compositeQuery": {
            "queryType": "builder",
            "panelType": "time_series",
            "builderQueries": {
                "A": {
                    "dataSource": "metrics",
                    "queryName": "A",
                    "aggregateOperator": "avg",
                    "aggregateAttribute": {
                        "key": metric_name,
                        "dataType": "float64",
                        "type": "gauge",
                        "isColumn": False,
                    },
                    "filters": {
                        "op": "AND",
                        "items": [
                            {
                                "key": {
                                    "key": "service_name",
                                    "type": "tag",
                                    "dataType": "string",
                                    "isColumn": False,
                                },
                                "op": "=",
                                "value": service_name,
                            }
                        ],
                    },
                    "groupBy": [],
                    "limit": 0,
                    "offset": 0,
                    "pageSize": 0,
                }
            },
        },
    }

    logger.debug(
        "query_metrics: service=%s metric=%s start=%d end=%d",
        service_name,
        metric_name,
        start_ms,
        end_ms,
    )
    data = _post_with_retry(_QUERY_RANGE_URL, payload)
    return _extract_series(data)


def get_alert_details(alert_id: int | str) -> dict[str, Any]:
    """
    Retrieve details for a single alert rule from SigNoz.

    Args:
        alert_id: Numeric rule ID as shown in the SigNoz Alerts UI or
                  included in a webhook payload.

    Returns:
        Parsed alert-rule dict as returned by SigNoz ``GET /api/v1/rules/{id}``.

    Raises:
        requests.HTTPError: if the alert is not found (404) or any HTTP error
            persists after the retry.
    """
    url = f"{_RULES_URL}/{alert_id}"
    logger.debug("get_alert_details: id=%s", alert_id)
    data = _get_with_retry(url)
    # SigNoz wraps the rule object in {"status":"success","data":{...}}
    return data.get("data", data)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_list(response: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Pull the flat list of records out of a SigNoz ``panelType=list`` response.

    SigNoz returns:
        {"status": "success", "data": {"result": [{"list": [...]}]}}
    """
    try:
        results: list[Any] = response["data"]["result"]
        if not results:
            return []
        # The first (and typically only) result bucket contains the rows
        return results[0].get("list", [])
    except (KeyError, IndexError, TypeError):
        logger.warning("Unexpected SigNoz list response shape: %s", list(response.keys()))
        return []


def _extract_series(response: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Pull the time-series data out of a SigNoz ``panelType=time_series`` response.

    SigNoz returns:
        {"status": "success", "data": {"result": [{"metric": {...}, "values": [...]}]}}
    """
    try:
        return response["data"]["result"]
    except (KeyError, TypeError):
        logger.warning("Unexpected SigNoz time_series response shape: %s", list(response.keys()))
        return []
