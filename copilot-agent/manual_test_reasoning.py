"""Manual end-to-end reasoning smoke test over a recent incident window."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from evidence_bundler import build_evidence_bundle
from mcp_client import query_logs, query_metrics, query_traces
from reasoning import analyze_incident


def main() -> None:
    end = datetime.now(UTC)
    start = end - timedelta(minutes=15)
    service = "demo-service"

    traces = query_traces(service, start, end)
    logs = query_logs(service, start, end)
    metrics = query_metrics(service, "db.query.duration", start, end)
    bundle = build_evidence_bundle(traces, logs, metrics)
    hypothesis = analyze_incident(bundle)

    print(bundle.model_dump_json(indent=2))
    print(hypothesis.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
