from typing import Any

from scripts.signoz.client import SignozClient


class ChannelManager:
    def __init__(self, client: SignozClient | None = None) -> None:
        self.client = client or SignozClient()

    def list_channels(self) -> list[dict[str, Any]]:
        response = self.client.get("/api/v2/notificationChannels")

        print("STATUS:", response.status_code)
        print("BODY:", response.text)

        response.raise_for_status()

        return response.json()["data"]

    def create_channel(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        response = self.client.post(
            "/api/v2/notificationChannels",
            json=payload,
        )

        response.raise_for_status()

        return response.json()["data"]

    def get_channel(
        self,
        channel_id: str,
    ) -> dict[str, Any]:
        response = self.client.get(f"/api/v2/notificationChannels/{channel_id}")

        response.raise_for_status()

        return response.json()["data"]
