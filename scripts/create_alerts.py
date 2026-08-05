import os
import requests

BASE_URL = os.environ["SIGNOZ_BASE_URL"]
API_KEY = os.environ["SIGNOZ_API_KEY"]

headers = {
    "SIGNOZ-API-KEY": API_KEY,
    "Content-Type": "application/json",
}

payload = {
    "name": "RootCauser Webhook",
    "webhook_configs": [
        {
            "send_resolved": True,
            "url": "http://copilot-agent:8001/webhook/alert"
        }
    ]
}

response = requests.post(
    f"{BASE_URL}/api/v1/channels",
    headers=headers,
    json=payload,
)

print(response.status_code)
print(response.text)