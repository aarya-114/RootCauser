"""Manual SigNoz evidence retrieval smoke test."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from mcp_client import get_alert_details, query_logs, query_metrics, query_traces


def main() -> None:
    end = datetime.now(UTC)
    start = end - timedelta(minutes=15)
    service = "demo-service"

    print("traces:", query_traces(service, start, end, min_duration_ms=500)[:3])
    print("logs:", query_logs(service, start, end)[:3])
    print("db metric:", query_metrics(service, "db.query.duration", start, end)[:3])
    print("downstream metric:", query_metrics(service, "downstream.errors", start, end)[:3])
    try:
        print("alert 1:", get_alert_details("1"))
    except Exception as exc:
        print(f"alert lookup skipped/failed: {exc}")


if __name__ == "__main__":
    main()
