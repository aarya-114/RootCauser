"""FastAPI webhook receiver for the RootCauser copilot agent."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import mcp_client
from config import get_settings
from evidence_bundler import build_evidence_bundle
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from github_output import create_github_issue
from reasoning import analyze_incident
from slack_output import send_slack_notification

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rootcauser-agent")

app = FastAPI(title="RootCauser Copilot Agent", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "copilot-agent"}


@app.post("/webhook/alert")
async def receive_alert(
    request: Request,
    background_tasks: BackgroundTasks,
    x_rootcauser_secret: str | None = Header(default=None),
) -> dict[str, str]:
    settings = get_settings()
    if settings.webhook_shared_secret and x_rootcauser_secret != settings.webhook_shared_secret:
        raise HTTPException(status_code=401, detail="invalid webhook secret")

    payload = await request.json()
    logger.info("Received SigNoz alert payload: %s", payload)
    background_tasks.add_task(process_alert, payload)
    return {"status": "accepted"}


def process_alert(payload: dict[str, Any]) -> None:
    settings = get_settings()
    service_name = _extract_service_name(payload)
    end_time = _extract_alert_time(payload)
    start_time = end_time - timedelta(minutes=settings.incident_window_minutes)
    alert_id = _extract_alert_id(payload)

    logger.info("Investigating service=%s window=%s..%s", service_name, start_time, end_time)

    alert_details: dict[str, Any] = payload
    if alert_id:
        try:
            alert_details = mcp_client.get_alert_details(alert_id)
        except Exception:
            logger.exception(
                "Could not fetch alert details for id=%s; using webhook payload", alert_id
            )

    traces = mcp_client.query_traces(service_name, start_time, end_time)
    logs = mcp_client.query_logs(service_name, start_time, end_time)
    metric_name = _extract_metric_name(payload)
    metrics = mcp_client.query_metrics(service_name, metric_name, start_time, end_time)

    bundle = build_evidence_bundle(traces, logs, metrics)
    hypothesis = analyze_incident(bundle)
    issue_url = create_github_issue(service_name, hypothesis, bundle, alert_details)
    send_slack_notification(service_name, hypothesis, issue_url)

    logger.info(
        "Investigation complete: confidence=%s issue_url=%s", hypothesis.confidence, issue_url
    )


def _extract_service_name(payload: dict[str, Any]) -> str:
    text = str(payload)
    for candidate in ("demo-service", "rootcauser-demo-service"):
        if candidate in text:
            return "demo-service"
    labels = payload.get("labels") if isinstance(payload.get("labels"), dict) else {}
    return str(
        labels.get("serviceName")
        or labels.get("service_name")
        or payload.get("serviceName")
        or "demo-service"
    )


def _extract_metric_name(payload: dict[str, Any]) -> str:
    text = str(payload)
    if "downstream" in text.lower() or "error" in text.lower():
        return "downstream.errors"
    return "db.query.duration"


def _extract_alert_id(payload: dict[str, Any]) -> str | None:
    for key in ("ruleId", "rule_id", "alert_id", "alertId", "id"):
        if payload.get(key):
            return str(payload[key])
    return None


def _extract_alert_time(payload: dict[str, Any]) -> datetime:
    for key in ("startsAt", "timestamp", "time", "triggeredAt"):
        value = payload.get(key)
        if not value:
            continue
        try:
            if isinstance(value, (int, float)):
                return datetime.fromtimestamp(value / 1000 if value > 1e12 else value, tz=UTC)
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            continue
    return datetime.now(UTC)
