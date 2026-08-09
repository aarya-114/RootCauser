from __future__ import annotations

import sys
from pathlib import Path

AGENT_PATH = Path(__file__).resolve().parents[1] / "copilot-agent"
sys.path.insert(0, str(AGENT_PATH))

import mcp_client  # noqa: E402


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


def test_alert_details_uses_uuid_v2_route(monkeypatch) -> None:
    received: list[str] = []
    monkeypatch.setattr(
        mcp_client, "_get_with_retry", lambda url: received.append(url) or {"data": {"id": "uuid"}}
    )
    assert mcp_client.get_alert_details("019fde7f-d754-717a-b9bc-5301d4d1a484")["id"] == "uuid"
    assert received[0].endswith("/api/v2/rules/019fde7f-d754-717a-b9bc-5301d4d1a484")
