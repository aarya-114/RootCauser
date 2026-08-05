import os
import requests


class SignozClient:
    def __init__(self):
        self.base_url = os.environ["SIGNOZ_BASE_URL"].rstrip("/")
        self.session = requests.Session()

        self.session.headers.update(
            {
                "SIGNOZ-API-KEY": os.environ["SIGNOZ_API_KEY"],
                "Content-Type": "application/json",
            }
        )

    def get(self, path):
        response = self.session.get(f"{self.base_url}{path}")
        response.raise_for_status()
        return response.json()

    def post(self, path, payload):
        response = self.session.post(
            f"{self.base_url}{path}",
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    def delete(self, path):
        response = self.session.delete(f"{self.base_url}{path}")
        response.raise_for_status()
        return response.json()