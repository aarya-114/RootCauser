"""Optional Slack notification output."""

from __future__ import annotations

import time

import requests
from config import get_settings
from reasoning import RootCauseHypothesis

RETRY_DELAY_SECONDS = 2.0


def send_slack_notification(
    service_name: str,
    hypothesis: RootCauseHypothesis,
    issue_url: str | None,
    alert_name: str = "Unknown alert",
) -> None:
    settings = get_settings()
    if not settings.slack_webhook_url or not issue_url:
        return

    text = (
        f"*RootCauser incident:* `{service_name}`\n"
        f"*Alert:* {alert_name}\n"
        f"*Confidence:* {hypothesis.confidence}\n"
        f"*Summary:* {hypothesis.summary}\n"
        f"*Suggested fix:* {hypothesis.suggested_fix}\n"
        f"*Issue:* <{issue_url}|Open GitHub issue>"
    )

    for attempt in (1, 2):
        try:
            response = requests.post(settings.slack_webhook_url, json={"text": text}, timeout=15)
            response.raise_for_status()
            return
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError):
            if attempt == 1:
                time.sleep(RETRY_DELAY_SECONDS)
                continue
            return
