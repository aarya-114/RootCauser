import os
from typing import Any

import requests


class SignozClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("SIGNOZ_BASE_URL", "http://localhost:8080").rstrip("/")
        self.api_key = os.environ["SIGNOZ_API_KEY"]

        self.session = requests.Session()
        self.session.headers.update({
            "SIGNOZ-API-KEY": self.api_key,
            "Content-Type": "application/json",
        })

    def request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> requests.Response:
        url = f"{self.base_url}{path}"

        response = self.session.request(
            method,
            url,
            timeout=30,
            **kwargs,
        )

        if not response.ok:
            raise RuntimeError(
                f"SigNoz API error: {response.status_code} "
                f"{response.text}"
            )

        return response

    def get(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> requests.Response:
        return self.request("PUT", path, **kwargs)