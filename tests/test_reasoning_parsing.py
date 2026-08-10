from __future__ import annotations

import json
import sys
from pathlib import Path

AGENT_PATH = Path(__file__).resolve().parents[1] / "copilot-agent"
sys.path.insert(0, str(AGENT_PATH))

from evidence_bundler import (  # noqa: E402
    EvidenceBundle,
    LogEvidence,
    MetricPoint,
    MetricSeries,
    SpanEvidence,
)
from reasoning import parse_and_validate_hypothesis  # noqa: E402


def _bundle() -> EvidenceBundle:
    return EvidenceBundle(
        spans=[
            SpanEvidence(
                trace_id="trace-slow-1",
                span_id="span-db-1",
                name="db.orders.slow_query",
                duration_ms=2200,
            )
        ],
        metrics=[
            MetricSeries(
                name="db.query.duration",
                points=[MetricPoint(timestamp=1, value=2200)],
                min_value=2200,
                max_value=2200,
                anomaly_point=MetricPoint(timestamp=1, value=2200),
            )
        ],
    )


def test_valid_response_with_span_and_metric_is_high_confidence() -> None:
    response = json.dumps(
        {
            "summary": "Slow order lookup is driving latency.",
            "cited_ids": ["span-db-1", "db.query.duration"],
            "suggested_fix": "Inspect the orders query and add an index if needed.",
            "insufficient_evidence": False,
        }
    )

    hypothesis = parse_and_validate_hypothesis(response, _bundle())

    assert hypothesis.confidence == "High"
    assert hypothesis.insufficient_evidence is False


def test_rejects_unverified_citation() -> None:
    response = json.dumps(
        {
            "summary": "Invented span caused the incident.",
            "cited_ids": ["span-not-real"],
            "suggested_fix": "Do something vague.",
            "insufficient_evidence": False,
        }
    )

    hypothesis = parse_and_validate_hypothesis(response, _bundle())

    assert hypothesis.confidence == "Insufficient Evidence"
    assert hypothesis.insufficient_evidence is True


def test_rejects_malformed_json() -> None:
    hypothesis = parse_and_validate_hypothesis("not-json", _bundle())

    assert hypothesis.confidence == "Insufficient Evidence"


def test_span_only_citation_is_medium_confidence() -> None:
    response = json.dumps(
        {
            "summary": "Slow span explains request latency.",
            "cited_ids": ["span-db-1"],
            "suggested_fix": "Inspect the slow query.",
            "insufficient_evidence": False,
        }
    )

    hypothesis = parse_and_validate_hypothesis(response, _bundle())

    assert hypothesis.confidence == "Medium"


def test_insufficient_evidence_keeps_valid_citations() -> None:
    response = json.dumps(
        {
            "summary": "Metric is missing context.",
            "cited_ids": ["span-db-1"],
            "suggested_fix": "Collect logs.",
            "insufficient_evidence": True,
        }
    )
    hypothesis = parse_and_validate_hypothesis(response, _bundle())
    assert hypothesis.result_status == "INSUFFICIENT_EVIDENCE"
    assert hypothesis.cited_ids == ["span-db-1"]


def test_invalid_citation_has_distinct_status() -> None:
    response = json.dumps(
        {
            "summary": "Bad reference.",
            "cited_ids": ["not-present"],
            "suggested_fix": "None.",
            "insufficient_evidence": False,
        }
    )
    assert (
        parse_and_validate_hypothesis(response, _bundle()).result_status
        == "CITATION_VALIDATION_FAILED"
    )


def test_unqualified_timeout_increase_is_not_presented_as_root_fix() -> None:
    bundle = EvidenceBundle(
        spans=[
            SpanEvidence(
                trace_id="trace", span_id="span", name="payment call", duration_ms=1500
            )
        ],
        logs=[
            LogEvidence(
                timestamp="1",
                severity="ERROR",
                body="payment API timeout",
                trace_id="trace",
                span_id="span",
            )
        ],
    )
    response = json.dumps(
        {
            "summary": "Payment API calls repeatedly timed out after 1.5 seconds.",
            "cited_ids": ["span"],
            "suggested_fix": "Increase the timeout threshold.",
            "insufficient_evidence": False,
        }
    )
    hypothesis = parse_and_validate_hypothesis(response, bundle)
    assert "Investigate the downstream dependency latency/root cause first" in hypothesis.suggested_fix
    assert "only as a mitigation" in hypothesis.suggested_fix
