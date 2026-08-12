from __future__ import annotations

import sys
from pathlib import Path

AGENT_PATH = Path(__file__).resolve().parents[1] / "copilot-agent"
sys.path.insert(0, str(AGENT_PATH))

import mcp_client  # noqa: E402
import requests  # noqa: E402
from evidence_bundler import build_evidence_bundle  # noqa: E402


def test_extracts_nested_query_rows_and_normalizes_trace() -> None:
    response = {
        "data": {
            "data": {
                "results": [
                    {
                        "rows": [
                            {
                                "data": {
                                    "traceID": "trace-1",
                                    "spanID": "span-1",
                                    "name": "db.orders.slow_query",
                                    "durationNano": 2_000_000_000,
                                }
                            }
                        ]
                    }
                ]
            }
        }
    }
    rows = mcp_client._extract_list(response, "traces")
    trace = mcp_client._normalize_trace(rows[0])
    assert trace["traceID"] == "trace-1"
    assert trace["spanID"] == "span-1"
    assert trace["durationNano"] == 2_000_000_000


def test_extracts_metric_series_points_without_unknown_name() -> None:
    response = {
        "data": {
            "data": {
                "results": [
                    {
                        "series": [
                            {
                                "metric": {"__name__": "db.query.duration.sum"},
                                "values": [[1, "20"], [2, "30"]],
                            }
                        ]
                    }
                ]
            }
        }
    }
    series = mcp_client._extract_series(response)
    normalized = mcp_client._normalize_series(series[0], "requested.metric")
    assert normalized["name"] == "db.query.duration.sum"
    assert normalized["points"] == [[1, "20"], [2, "30"]]


def test_extracts_current_v5_aggregation_metric_shape() -> None:
    response = {
        "data": {
            "data": {
                "results": [
                    {
                        "queryName": "A",
                        "aggregations": [
                            {
                                "alias": "__result_0",
                                "meta": {"service.name": "demo-service"},
                                "series": [
                                    {
                                        "labels": {"route": "/orders"},
                                        "values": [{"timestamp": 1786378920000, "value": 2000.171}],
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        }
    }
    series = mcp_client._extract_series(response)
    normalized = mcp_client._normalize_series(series[0], "db.query.duration.sum")
    assert normalized["name"] == "db.query.duration.sum"
    assert normalized["labels"] == {"service.name": "demo-service", "route": "/orders"}
    assert normalized["points"] == [{"timestamp": 1786378920000, "value": 2000.171}]


def test_valid_downstream_metric_is_included_in_evidence_bundle(monkeypatch) -> None:
    response = {
        "data": {
            "data": {
                "results": [
                    {
                        "queryName": "A",
                        "aggregations": [
                            {
                                "series": [
                                    {
                                        "values": [
                                            {"timestamp": 1786381560000, "value": 4.5},
                                            {"timestamp": 1786381620000, "value": 5.75},
                                        ]
                                    }
                                ]
                            }
                        ],
                    }
                ]
            }
        }
    }
    monkeypatch.setattr(mcp_client, "_post_with_retry", lambda *_args: response)
    metrics = mcp_client.query_metrics("demo-service", "downstream.errors", 1, 2)
    bundle = build_evidence_bundle([], [], metrics)
    assert bundle.metrics[0].name == "downstream.errors"
    assert bundle.metrics[0].points[0].value == 4.5
    assert bundle.metrics[0].max_value == 5.75


def test_metric_series_and_points_are_bounded() -> None:
    raw = {"values": [[index, index] for index in range(mcp_client.MAX_METRIC_POINTS + 1)]}
    assert (
        len(mcp_client._normalize_series(raw, "metric")["points"]) == mcp_client.MAX_METRIC_POINTS
    )
    response = {
        "data": {
            "data": {
                "results": [
                    {"aggregations": [{"series": [{"values": [[1, 1]]}]}]}
                    for _ in range(mcp_client.MAX_METRIC_SERIES + 1)
                ]
            }
        }
    }
    assert len(mcp_client._extract_series(response)) == mcp_client.MAX_METRIC_SERIES + 1

    monkeypatch_response = response
    original = mcp_client._post_with_retry
    mcp_client._post_with_retry = lambda *_args: monkeypatch_response
    try:
        assert (
            len(mcp_client.query_metrics("demo-service", "metric", 1, 2))
            == mcp_client.MAX_METRIC_SERIES
        )
    finally:
        mcp_client._post_with_retry = original


def test_empty_metric_response_returns_no_series() -> None:
    assert mcp_client._extract_series({"data": {"data": {"results": []}}}) == []


def test_alert_details_uses_uuid_v2_route(monkeypatch) -> None:
    received: list[str] = []
    monkeypatch.setattr(
        mcp_client, "_get_with_retry", lambda url: received.append(url) or {"data": {"id": "uuid"}}
    )
    assert mcp_client.get_alert_details("019fde7f-d754-717a-b9bc-5301d4d1a484")["id"] == "uuid"
    assert received[0].endswith("/api/v2/rules/019fde7f-d754-717a-b9bc-5301d4d1a484")


def test_log_query_failure_returns_empty_list(monkeypatch) -> None:
    monkeypatch.setattr(
        mcp_client,
        "_post_with_retry",
        lambda *_args: (_ for _ in ()).throw(requests.HTTPError("JSON* unsupported")),
    )
    assert mcp_client.query_logs("demo-service", 1, 2) == []
