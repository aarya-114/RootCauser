from dataclasses import dataclass, field
from typing import Any


@dataclass
class MetricAggregation:
    metric_name: str
    time_aggregation: str = "rate"
    space_aggregation: str = "sum"
    temporality: str = ""


@dataclass
class MetricQuery:
    name: str
    aggregation: MetricAggregation
    filter_expression: str = ""


@dataclass
class FormulaQuery:
    name: str
    expression: str


@dataclass
class AlertSpec:
    name: str
    queries: list[MetricQuery | FormulaQuery]
    threshold: float
    notification_channels: list[str]
    description: str
    summary: str
    eval_window: str = "1m"
    frequency: str = "1m"
    unit: str = "ms"

    def _selected_query_name(self) -> str:
        return self.queries[-1].name


    def to_payload(self) -> dict[str, Any]:
        queries = []

        for query in self.queries:
            if isinstance(query, MetricQuery):
                queries.append({
                    "type": "builder_query",
                    "spec": {
                        "name": query.name,
                        "signal": "metrics",
                        "source": "",
                        "aggregations": [
                            {
                                "metricName": query.aggregation.metric_name,
                                "temporality": query.aggregation.temporality,
                                "timeAggregation": query.aggregation.time_aggregation,
                                "spaceAggregation": query.aggregation.space_aggregation,
                            }
                        ],
                        "disabled": False,
                        "filter": {
                            "expression": query.filter_expression,
                        },
                        "legend": "",
                    },
                })

            elif isinstance(query, FormulaQuery):
                queries.append({
                    "type": "builder_formula",
                    "spec": {
                        "name": query.name,
                        "expression": query.expression,
                        "disabled": False,
                        "legend": "",
                    },
                })

        return {
            "alert": self.name,
            "alertType": "METRIC_BASED_ALERT",
            "ruleType": "threshold_rule",
            "condition": {
                "compositeQuery": {
                    "queries": queries,
                    "panelType": "graph",
                    "queryType": "builder",
                    "unit": self.unit,
                },
                "selectedQueryName": self._selected_query_name(),
                "thresholds": {
                    "kind": "basic",
                    "spec": [
                        {
                            "name": "critical",
                            "target": self.threshold,
                            "targetUnit": "",
                            "recoveryTarget": None,
                            "matchType": "at_least_once",
                            "op": "above",
                            "channels": self.notification_channels,
                        }
                    ],
                },
            },
            "annotations": {
                "description": self.description,
                "summary": self.summary,
            },
            "disabled": False,
            "version": "v5",
            "evaluation": {
                "kind": "rolling",
                "spec": {
                    "evalWindow": self.eval_window,
                    "frequency": self.frequency,
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