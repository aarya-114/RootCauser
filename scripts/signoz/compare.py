from typing import Any


def alert_payload_from_rule(rule: dict[str, Any]) -> dict[str, Any]:
    """
    Extract the parts of a SigNoz rule that define its behavior.

    Runtime-generated fields such as:
    - id
    - state
    - source
    - createdAt
    - updatedAt
    - createdBy
    - updatedBy

    are intentionally ignored.
    """

    return {
        "alert": rule["alert"],
        "alertType": rule["alertType"],
        "ruleType": rule["ruleType"],
        "condition": rule["condition"],
        "annotations": rule.get("annotations", {}),
        "disabled": rule.get("disabled", False),
        "version": rule.get("version"),
        "evaluation": rule.get("evaluation"),
        "schemaVersion": rule.get("schemaVersion"),
        "notificationSettings": rule.get(
            "notificationSettings",
            {},
        ),
    }


def alerts_differ(
    existing_rule: dict[str, Any],
    desired_payload: dict[str, Any],
) -> bool:
    """
    Return True when the existing SigNoz rule differs
    from the desired payload.
    """

    existing = alert_payload_from_rule(existing_rule)

    return existing != desired_payload