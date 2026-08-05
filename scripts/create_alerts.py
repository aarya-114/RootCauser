import json
import os
import requests

BASE_URL = os.environ["SIGNOZ_BASE_URL"]
API_KEY = os.environ["SIGNOZ_API_KEY"]

headers = {
    "SIGNOZ-API-KEY": API_KEY,
}

response = requests.get(
    f"{BASE_URL}/api/v1/rules",
    headers=headers,
)

print(response.status_code)
print(json.dumps(response.json(), indent=2))