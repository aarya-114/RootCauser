from typing import Any

from scripts.signoz.client import SignozClient
from scripts.signoz.compare import alerts_differ


class AlertManager:
    def __init__(self, client: SignozClient | None = None) -> None:
        self.client = client or SignozClient()

    def list_alerts(self) -> list[dict[str, Any]]:
        response = self.client.get("/api/v2/rules")
        response.raise_for_status()

        return response.json()["data"]

    def get_alert(self, alert_id: str) -> dict[str, Any]:
        response = self.client.get(f"/api/v2/rules/{alert_id}")
        response.raise_for_status()

        return response.json()["data"]

    def create_alert(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        response = self.client.post(
            "/api/v2/rules",
            json=payload,
        )
        response.raise_for_status()

        return response.json()["data"]

    def update_alert(
        self,
        alert_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        response = self.client.put(
            f"/api/v2/rules/{alert_id}",
            json=payload,
        )
        response.raise_for_status()

        # SigNoz may return an empty response for PUT.
        if not response.text.strip():
            return self.get_alert(alert_id)

        try:
            return response.json()["data"]
        except ValueError:
            return self.get_alert(alert_id)

    def ensure_alert(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        alert_name = payload["alert"]

        existing_alert = next(
            (alert for alert in self.list_alerts() if alert.get("alert") == alert_name),
            None,
        )

        if existing_alert is None:
            print(f"[CREATE] Alert does not exist: {alert_name}")
            return self.create_alert(payload)

        if not alerts_differ(existing_alert, payload):
            print(f"[NOOP] Alert already matches: {alert_name}")
            return existing_alert

        print(f"[UPDATE] Alert configuration changed: {alert_name}")

        return self.update_alert(
            existing_alert["id"],
            payload,
        )
