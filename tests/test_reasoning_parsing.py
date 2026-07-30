from __future__ import annotations

import json
import sys
from pathlib import Path

AGENT_PATH = Path(__file__).resolve().parents[1] / "copilot-agent"
sys.path.insert(0, str(AGENT_PATH))

from evidence_bundler import EvidenceBundle, MetricPoint, MetricSeries, SpanEvidence  # noqa: E402
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
