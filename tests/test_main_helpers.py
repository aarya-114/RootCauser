from __future__ import annotations

import sys
from pathlib import Path

AGENT_PATH = Path(__file__).resolve().parents[1] / "copilot-agent"
sys.path.insert(0, str(AGENT_PATH))

from main import _extract_alert_id, _extract_metric_name, _incident_context  # noqa: E402


def test_manual_webhook_has_no_alert_id_and_fallback_metric() -> None:
    payload = {"alertname": "manual slow query test", "labels": {"serviceName": "demo-service"}}
    assert _extract_alert_id(payload) is None
    assert _extract_metric_name(payload, payload) == "db.query.duration"


def test_nested_webhook_rule_id_takes_precedence() -> None:
    payload = {
        "ruleId": "top-level-id",
        "alerts": [{"labels": {"ruleId": "019fec4f-f69c-73d6-8d7c-f14477f11ded"}}],
    }
    assert _extract_alert_id(payload) == "019fec4f-f69c-73d6-8d7c-f14477f11ded"


def test_nested_webhook_rule_id_aliases_are_supported() -> None:
    for key in ("rule_id", "alertId"):
        assert _extract_alert_id({"alerts": [{"labels": {key: "real-uuid"}}]}) == "real-uuid"


def test_alert_rule_metric_takes_precedence() -> None:
    rule = {
        "id": "019fde7f-d754-717a-b9bc-5301d4d1a484",
        "compositeQuery": {
            "queries": [
                {
                    "spec": {
                        "aggregations": [
                            {"metricName": "db.query.duration.sum"},
                            {"metricName": "db.query.duration.count"},
                        ]
                    }
                }
            ]
        },
    }
    assert _extract_alert_id({"ruleId": rule["id"]}) == rule["id"]
    assert _extract_metric_name({"alertname": "anything"}, rule) == "db.query.duration.sum"


def test_incident_context_includes_composite_query_semantics() -> None:
    from datetime import UTC, datetime

    context = _incident_context({}, {"compositeQuery": {"filter": "database timeout"}}, "metric.name", "svc", datetime.now(UTC))
    assert "database timeout" in context["semantic_terms"]
