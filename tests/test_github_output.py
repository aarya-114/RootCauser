from __future__ import annotations

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
from github_output import build_report_facts, render_issue_markdown  # noqa: E402
from reasoning import RootCauseHypothesis  # noqa: E402


def _bundle() -> EvidenceBundle:
    return EvidenceBundle(
        spans=[
            SpanEvidence(
                trace_id="trace-1",
                span_id="span-1",
                name="dependency call",
                duration_ms=1500,
                timestamp="2026-08-10T22:35:17Z",
                relevance_score=100,
                relevance_reasons=["correlated log span_id"],
            )
        ],
        logs=[
            LogEvidence(
                timestamp="2026-08-10T22:35:10Z",
                severity="ERROR",
                body="dependency timeout",
                trace_id="trace-1",
                span_id="span-1",
                relevance_score=100,
                relevance_reasons=["span_id matches selected span"],
            )
        ],
        metrics=[
            MetricSeries(
                name="dependency.errors",
                points=[
                    MetricPoint(timestamp="2026-08-10T22:35:16Z", value=131),
                    MetricPoint(timestamp="2026-08-10T22:35:26Z", value=161),
                ],
                min_value=131,
                max_value=161,
                anomaly_point=MetricPoint(timestamp="2026-08-10T22:35:26Z", value=161),
            )
        ],
    )


def test_report_facts_summarize_actual_evidence_and_chain() -> None:
    facts = build_report_facts(_bundle())
    assert "1 selected spans (`dependency call`); duration 1500–1500 ms" in facts["evidence_summary"]
    assert "1 selected logs with severity ERROR" in facts["evidence_summary"]
    assert "`dependency.errors` 131 → 161" in facts["evidence_summary"]
    assert "logs matched selected trace/span IDs" in facts["evidence_summary"]
    assert "selected logs share trace or span IDs" in facts["evidence_chain"]


def test_confidence_breakdown_and_coverage_handle_missing_signals() -> None:
    facts = build_report_facts(EvidenceBundle(spans=[_bundle().spans[0]]))
    assert "Relevant trace" in facts["confidence_breakdown"]
    assert "No selected logs" in facts["confidence_breakdown"]
    assert "No metric points" in facts["confidence_breakdown"]
    assert "| Logs | — | — |" in facts["evidence_coverage"]
    assert "| Metrics | — | — |" in facts["evidence_coverage"]


def test_timeline_is_chronological_and_issue_keeps_raw_bundle() -> None:
    bundle = _bundle()
    facts = build_report_facts(bundle)
    assert facts["timeline"].index("22:35:10") < facts["timeline"].index("22:35:17")
    hypothesis = RootCauseHypothesis(
        summary="Observed dependency failures.",
        suggested_fix="Investigate the dependency.",
        confidence="High",
    )
    report = render_issue_markdown("demo-service", hypothesis, bundle, {"alertname": "test"})
    assert "### Evidence Summary" in report
    assert "### Evidence Chain" in report
    assert "### Confidence Breakdown" in report
    assert "### Incident Timeline" in report
    assert "### Evidence Coverage" in report
    assert "### Raw Evidence Bundle" in report
    assert '"trace_id": "trace-1"' in report
