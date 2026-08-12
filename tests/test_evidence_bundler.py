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


def test_log_correlation_and_semantics_outrank_duration() -> None:
    bundle = build_evidence_bundle(
        [
            {"traceID": "health", "spanID": "health", "name": "GET /health", "durationMs": 800000},
            {"traceID": "db-trace", "spanID": "db-span", "name": "database operation", "durationMs": 10},
        ],
        [{"traceID": "db-trace", "spanID": "db-span", "severityText": "WARN", "body": "query"}],
        [],
        incident_context={"semantic_terms": ["database", "query"]},
    )
    assert bundle.spans[0].span_id == "db-span"
    assert "correlated log span_id" in bundle.spans[0].relevance_reasons
    # Health span is excluded from selected evidence (no semantic match, no error, no log correlation)
    assert len(bundle.spans) == 1
    assert all(span.span_id != "health" for span in bundle.spans)


def test_temporal_health_and_diversity_ranking() -> None:
    alert_time = "2026-08-10T10:00:00Z"
    traces = [
        {"traceID": "dup", "spanID": f"dup-{i}", "name": "database query", "durationMs": 100}
        for i in range(4)
    ]
    traces.extend(
        [
            {"traceID": "near", "spanID": "near", "name": "database query", "durationMs": 100, "timestamp": alert_time},
            {"traceID": "far", "spanID": "far", "name": "database query", "durationMs": 100, "timestamp": "2026-08-10T09:00:00Z"},
            {"traceID": "health", "spanID": "health", "name": "GET /health", "durationMs": 1},
        ]
    )
    bundle = build_evidence_bundle(traces, [], [], incident_context={"semantic_terms": ["database"], "alert_timestamp": alert_time})
    assert bundle.spans[0].span_id == "near"
    assert sum(span.trace_id == "dup" for span in bundle.spans) <= 2
    health_bundle = build_evidence_bundle([traces[-1]], [], [], incident_context={"semantic_terms": ["health"], "is_health_alert": True})
    assert "routine health span penalty" not in health_bundle.spans[0].relevance_reasons
    assert bundle.spans[0].trace_id == "near"


# ---------------------------------------------------------------------------
# New focused tests (Task 1 requirements)
# ---------------------------------------------------------------------------

def test_irrelevant_traces_not_counted_as_supporting() -> None:
    """Traces with no semantic match, no error, and no log correlation must not
    appear in bundle.spans even if trace telemetry was retrieved.
    They are still counted in traces_available so the report can distinguish
    'traces retrieved' from 'traces relevant'."""
    traces = [
        {"traceID": "health-1", "spanID": "span-h1", "name": "GET /health", "durationMs": 50},
        {"traceID": "health-2", "spanID": "span-h2", "name": "GET /readiness", "durationMs": 30},
    ]
    bundle = build_evidence_bundle(
        traces,
        [],
        [],
        incident_context={"semantic_terms": ["orders", "database"]},
    )
    # Traces were retrieved but none are relevant — spans must be empty
    assert bundle.spans == []
    # Telemetry was present — traces_available must reflect raw count
    assert bundle.traces_available == 2
    # Report can distinguish retrieved vs relevant
    assert bundle.traces_relevant == 0


def test_correlated_logs_usable_without_relevant_traces() -> None:
    """When no trace qualifies as supporting evidence, logs with their own
    severity signal should still be returned and usable for investigation.
    This verifies that logs are not dependent on trace evidence being present."""
    # Only a generic uncorrelated health span — no semantic match, no error
    traces = [
        {"traceID": "health-t", "spanID": "health-s", "name": "GET /health", "durationMs": 5},
    ]
    # Logs carry error evidence on their own (no trace_id correlation to selected spans)
    logs = [
        {"timestamp": "2026-08-10T10:00:01Z", "severityText": "ERROR", "body": "order service error"},
        {"timestamp": "2026-08-10T10:00:02Z", "severityText": "WARN", "body": "retry threshold reached"},
    ]
    bundle = build_evidence_bundle(
        traces,
        logs,
        [],
        incident_context={"semantic_terms": ["orders", "database"]},
    )
    # Health span is not relevant — no spans selected
    assert bundle.spans == []
    assert bundle.traces_available == 1
    # Logs are still available and selected without trace evidence
    assert len(bundle.logs) == 2
    assert any(log.severity == "ERROR" for log in bundle.logs)
    # Bundle is NOT empty — logs are usable evidence
    assert not bundle.is_empty()


def test_relevant_span_beats_health_span_traces_available_reflects_both() -> None:
    """The health span should appear in traces_available but not in spans (selected).
    The relevant span must appear in spans."""
    bundle = build_evidence_bundle(
        [
            {"traceID": "health-trace", "spanID": "health-span", "name": "GET /health", "durationMs": 99999},
            {"traceID": "order-trace", "spanID": "order-span", "name": "order processing", "durationMs": 200},
        ],
        [],
        [],
        incident_context={"semantic_terms": ["order", "processing"]},
    )
    # Both traces were retrieved
    assert bundle.traces_available == 2
    # Only the relevant span is selected
    selected_ids = {span.span_id for span in bundle.spans}
    assert "order-span" in selected_ids
    assert "health-span" not in selected_ids
    # traces_relevant matches spans count
    assert bundle.traces_relevant == len(bundle.spans)


def test_confidence_reflects_actual_selected_evidence() -> None:
    """If only irrelevant traces are retrieved (no relevant spans are selected),
    the evidence bundle must indicate this; the LLM cannot cite a span that was
    excluded, so confidence must stay Low for zero-evidence bundles."""
    import json
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "copilot-agent"))
    from reasoning import parse_and_validate_hypothesis  # noqa: E402

    # Bundle with NO selected spans (only irrelevant health traces)
    bundle = build_evidence_bundle(
        [{"traceID": "h", "spanID": "hs", "name": "GET /health", "durationMs": 1}],
        [],
        [],
    )
    assert bundle.spans == []
    # Even if the LLM tries to cite the health span's span_id,
    # it IS present in searchable_text() but the span was not a selected span.
    # Confidence should be Low because there are no selected spans or metrics.
    response = json.dumps({
        "summary": "No useful evidence found.",
        "cited_ids": [],
        "suggested_fix": "Collect more evidence.",
        "insufficient_evidence": False,
    })
    hyp = parse_and_validate_hypothesis(response, bundle)
    assert hyp.confidence == "Low"
