from scripts.signoz.alerts import AlertManager
from scripts.signoz.specs import (
    AlertSpec,
    FormulaQuery,
    MetricAggregation,
    MetricQuery,
)
from dotenv import load_dotenv 

load_dotenv()    

def build_slow_query_alert() -> AlertSpec:
    return AlertSpec(
        name="slow-api-test-2",
        queries=[
            MetricQuery(
                "A",
                MetricAggregation("db.query.duration.sum"),
            ),
            MetricQuery(
                "B",
                MetricAggregation("db.query.duration.count"),
            ),
            FormulaQuery(
                "F1",
                "A/B",
            ),
        ],
        threshold=100,
        notification_channels=[
            "RootCauser Webhook",
        ],
        description="RootCauser test alert for slow database queries.",
        summary="RootCauser test alert for slow database queries.",
    )


def main() -> None:
    alert_manager = AlertManager()

    alert_spec = build_slow_query_alert()

    result = alert_manager.ensure_alert(
        alert_spec.to_payload()
    )

    print(
        f"RESULT: {result['id']} "
        f"{result['alert']} "
        f"{result['state']}"
    )


if __name__ == "__main__":
    main()