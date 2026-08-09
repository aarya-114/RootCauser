from __future__ import annotations

import sys
from pathlib import Path

AGENT_PATH = Path(__file__).resolve().parents[1] / "copilot-agent"
sys.path.insert(0, str(AGENT_PATH))

from main import _extract_alert_id, _extract_metric_name  # noqa: E402


def test_manual_webhook_has_no_alert_id_and_fallback_metric() -> None:
    payload = {"alertname": "manual slow query test", "labels": {"serviceName": "demo-service"}}
    assert _extract_alert_id(payload) is None
    assert _extract_metric_name(payload, payload) == "db.query.duration"


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
