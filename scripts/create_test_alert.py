from scripts.signoz.alerts import AlertManager
from scripts.signoz.specs import (
    AlertSpec,
    FormulaQuery,
    MetricAggregation,
    MetricQuery,
)


def main():
    spec = AlertSpec(
        name="rootcauser-api-test",
        queries=[
            MetricQuery(
                name="A",
                aggregation=MetricAggregation(metric_name="db.query.duration.sum"),
            ),
            MetricQuery(
                name="B",
                aggregation=MetricAggregation(metric_name="db.query.duration.count"),
            ),
            FormulaQuery(
                name="F1",
                expression="A/B",
            ),
        ],
        threshold=1.5,
        notification_channels=["RootCauser Webhook"],
        description="RootCauser API-generated test alert.",
        summary="RootCauser API-generated test alert.",
    )

    payload = spec.to_payload()

    print("Creating:", spec.name)

    manager = AlertManager()
    result = manager.create_alert(payload)

    print("Created:")
    print("ID:", result["id"])
    print("Name:", result["alert"])


if __name__ == "__main__":
    main()
