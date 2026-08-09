import json
import os
import requests


BASE_URL = os.getenv("SIGNOZ_BASE_URL", "http://localhost:8080")
API_KEY = os.environ["SIGNOZ_API_KEY"]

HEADERS = {
    "SIGNOZ-API-KEY": API_KEY,
    "Content-Type": "application/json",
}


payload = {
    "alert": "slow-api-test-2",
    "alertType": "METRIC_BASED_ALERT",
    "ruleType": "threshold_rule",

    "condition": {
        "compositeQuery": {
            "queries": [
                {
                    "type": "builder_query",
                    "spec": {
                        "name": "A",
                        "signal": "metrics",
                        "source": "",
                        "aggregations": [
                            {
                                "metricName": "db.query.duration.sum",
                                "temporality": "",
                                "timeAggregation": "rate",
                                "spaceAggregation": "sum",
                            }
                        ],
                        "disabled": False,
                        "filter": {
                            "expression": ""
                        },
                        "legend": "",
                    },
                },
                {
                    "type": "builder_query",
                    "spec": {
                        "name": "B",
                        "signal": "metrics",
                        "source": "",
                        "aggregations": [
                            {
                                "metricName": "db.query.duration.count",
                                "temporality": "",
                                "timeAggregation": "rate",
                                "spaceAggregation": "sum",
                            }
                        ],
                        "disabled": False,
                        "filter": {
                            "expression": ""
                        },
                        "legend": "",
                    },
                },
                {
                    "type": "builder_formula",
                    "spec": {
                        "name": "F1",
                        "expression": "A/B",
                        "disabled": False,
                        "legend": "",
                    },
                },
            ],
            "panelType": "graph",
            "queryType": "builder",
            "unit": "ms",
        },

        "selectedQueryName": "A",

        "thresholds": {
            "kind": "basic",
            "spec": [
                {
                    "name": "critical",
                    "target": 1.5,
                    "targetUnit": "",
                    "recoveryTarget": None,
                    "matchType": "at_least_once",
                    "op": "above",
                    "channels": [
                        "RootCauser Webhook"
                    ],
                }
            ],
        },
    },

    "annotations": {
        "description": (
            "RootCauser test alert for slow database queries."
        ),
        "summary": (
            "RootCauser test alert for slow database queries."
        ),
    },

    "disabled": False,

    "version": "v5",

    "evaluation": {
        "kind": "rolling",
        "spec": {
            "evalWindow": "1m",
            "frequency": "1m",
        },
    },

    "schemaVersion": "v2alpha1",

    "notificationSettings": {
        "groupBy": [],
        "renotify": {
            "enabled": False,
            "interval": "30m",
            "alertStates": [],
        },
        "usePolicy": False,
    },
}


response = requests.post(
    f"{BASE_URL}/api/v1/rules",
    headers=HEADERS,
    json=payload,
    timeout=15,
)

print("STATUS:", response.status_code)

try:
    print(json.dumps(response.json(), indent=2))
except ValueError:
    print(response.text)