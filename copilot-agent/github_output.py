"""GitHub Issue output for RootCauser investigations."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import requests
from config import get_settings
from evidence_bundler import EvidenceBundle
from reasoning import RootCauseHypothesis

RETRY_DELAY_SECONDS = 2.0
ARTIFACT_DIR = Path(__file__).parent / "artifacts"


def create_github_issue(
    service_name: str,
    hypothesis: RootCauseHypothesis,
    bundle: EvidenceBundle,
    alert: dict[str, Any] | None = None,
) -> str | None:
    """Render and create a GitHub issue. Returns the issue URL when created."""
    settings = get_settings()
    title = f"[RootCauser] {service_name}: {hypothesis.confidence} root-cause hypothesis"
    body = render_issue_markdown(service_name, hypothesis, bundle, alert or {})
    _write_local_issue(title, body)

    if not settings.github_token or settings.github_repo == "your-org/your-repo":
        return None

    url = f"https://api.github.com/repos/{settings.github_repo}/issues"
    headers = {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {"title": title, "body": body, "labels": ["rootcauser", "incident"]}

    for attempt in (1, 2):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            return str(response.json().get("html_url"))
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError):
            if attempt == 1:
                time.sleep(RETRY_DELAY_SECONDS)
                continue
            raise
    return None


def render_issue_markdown(
    service_name: str,
    hypothesis: RootCauseHypothesis,
    bundle: EvidenceBundle,
    alert: dict[str, Any],
) -> str:
    template = (Path(__file__).parent / "prompts" / "issue_template.md").read_text(encoding="utf-8")
    top_trace = bundle.spans[0].trace_id if bundle.spans else ""
    settings = get_settings()
    trace_link = (
        f"{settings.signoz_public_url}/trace/{top_trace}"
        if top_trace
        else "No trace link available"
    )
    nested_alert = alert.get("alert")
    nested_name = nested_alert.get("name") if isinstance(nested_alert, dict) else nested_alert
    return template.format(
        service_name=service_name,
        confidence=hypothesis.confidence,
        summary=hypothesis.summary,
        suggested_fix=hypothesis.suggested_fix,
        cited_ids=", ".join(hypothesis.cited_ids) or "None",
        trace_link=trace_link,
        alert_name=alert.get("alertname")
        or alert.get("ruleName")
        or alert.get("name")
        or nested_name
        or "Unknown alert",
        incident_window=alert.get("incident_window")
        or alert.get("startsAt")
        or "See investigation log",
        evidence_json=bundle.model_dump_json(indent=2),
    )


def _write_local_issue(title: str, body: str) -> None:
    ARTIFACT_DIR.mkdir(exist_ok=True)
    safe_title = "".join(ch if ch.isalnum() else "-" for ch in title.lower()).strip("-")[:80]
    path = ARTIFACT_DIR / f"{int(time.time())}-{safe_title}.md"
    path.write_text(f"# {title}\n\n{body}\n", encoding="utf-8")
