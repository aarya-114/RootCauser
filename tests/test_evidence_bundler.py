from __future__ import annotations

import sys
from pathlib import Path

AGENT_PATH = Path(__file__).resolve().parents[1] / "copilot-agent"
sys.path.insert(0, str(AGENT_PATH))

from evidence_bundler import build_evidence_bundle  # noqa: E402


def test_ranks_and_truncates_spans_and_logs() -> None:
    traces = [
        {
            "traceID": f"trace-{idx}",
            "spanID": f"span-{idx}",
            "name": "op",
            "durationNano": idx * 1_000_000,
        }
        for idx in range(1, 8)
    ]
    traces[0]["statusCode"] = "ERROR"
    logs = [
        {
            "timestamp": str(idx),
            "severityText": "INFO",
            "body": f"log {idx}",
            "traceID": f"trace-{idx}",
        }
        for idx in range(1, 8)
    ]
    logs[3]["severityText"] = "ERROR"

    bundle = build_evidence_bundle(traces, logs, [])

    assert len(bundle.spans) == 5
    assert len(bundle.logs) == 5
    assert bundle.spans[0].is_error is True
    assert any(log.severity == "ERROR" for log in bundle.logs)


def test_empty_input_reports_empty() -> None:
    bundle = build_evidence_bundle([], [], [])

    assert bundle.is_empty()


def test_partial_input_still_builds_usable_bundle() -> None:
    bundle = build_evidence_bundle(
        [
            {
                "traceID": "trace-a",
                "spanID": "span-a",
                "durationMs": 2300,
                "name": "db.orders.slow_query",
            }
        ],
        [],
        None,
    )

    assert not bundle.is_empty()
    assert bundle.spans[0].duration_ms == 2300


def test_metric_anomaly_point_uses_max_value() -> None:
    bundle = build_evidence_bundle(
        [],
        [],
        [
            {
                "metric": {"__name__": "db.query.duration"},
                "values": [[1, "10"], [2, "2500"], [3, "20"]],
            }
        ],
    )

    metric = bundle.metrics[0]
    assert metric.name == "db.query.duration"
    assert metric.max_value == 2500
    assert metric.anomaly_point is not None
    assert metric.anomaly_point.timestamp == 2


def test_nested_records_preserve_ids_and_duration() -> None:
    bundle = build_evidence_bundle(
        [
            {
                "timestamp": "2026-08-09T00:00:00Z",
                "data": {
                    "traceID": "trace-real",
                    "spanID": "span-real",
                    "name": "db.orders.slow_query",
                    "durationNano": 2_000_000_000,
                },
            }
        ],
        [
            {
                "timestamp": "2026-08-09T00:00:01Z",
                "data": {
                    "body": "Slow query detected",
                    "severityText": "WARN",
                    "traceID": "trace-real",
                    "spanID": "span-real",
                },
            }
        ],
        [],
    )
    assert bundle.spans[0].trace_id == "trace-real"
    assert bundle.spans[0].span_id == "span-real"
    assert bundle.spans[0].duration_ms == 2000
    assert bundle.logs[0].trace_id == "trace-real"


def test_incident_span_outranks_unrelated_long_health_check() -> None:
    bundle = build_evidence_bundle(
        [
            {
                "traceID": "health-trace",
                "spanID": "health-span",
                "name": "GET /health",
                "durationNano": 800_000_000_000,
            },
            {
                "traceID": "order-trace",
                "spanID": "order-span",
                "name": "db.orders.slow_query",
                "durationNano": 2_000_000_000,
            },
        ],
        [],
        [],
        incident_keywords=["db.query.duration", "slow query"],
        service_name="demo-service",
    )
    assert bundle.spans[0].span_id == "order-span"
