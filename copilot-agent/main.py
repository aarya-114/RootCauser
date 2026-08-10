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

app = FastAPI(
    title="RootCauser Copilot Agent",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "copilot-agent",
    }


@app.post("/webhook/alert")
async def receive_alert(
    request: Request,
    background_tasks: BackgroundTasks,
    x_rootcauser_secret: str | None = Header(default=None),
) -> dict[str, str]:
    settings = get_settings()

    if settings.webhook_shared_secret and x_rootcauser_secret != settings.webhook_shared_secret:
        raise HTTPException(
            status_code=401,
            detail="invalid webhook secret",
        )

    payload = await request.json()

    logger.info(
        "Received SigNoz alert payload: %s",
        payload,
    )

    background_tasks.add_task(
        process_alert,
        payload,
    )

    return {
        "status": "accepted",
    }


def process_alert(payload: dict[str, Any]) -> None:
    settings = get_settings()

    # ---------------------------------------------------------
    # 1. Extract incident context from the alert
    # ---------------------------------------------------------

    service_name = _extract_service_name(payload)

    end_time = _extract_alert_time(payload)

    start_time = end_time - timedelta(minutes=settings.incident_window_minutes)

    alert_id = _extract_alert_id(payload)

    logger.info(
        "Investigating service=%s window=%s..%s alert_id=%s",
        service_name,
        start_time,
        end_time,
        alert_id,
    )

    # ---------------------------------------------------------
    # 2. Retrieve the actual SigNoz alert definition
    # ---------------------------------------------------------

    alert_details: dict[str, Any] = payload

    if alert_id:
        try:
            alert_details = mcp_client.get_alert_details(alert_id)

            logger.info(
                "Retrieved alert details for alert_id=%s",
                alert_id,
            )

        except Exception:
            logger.exception(
                "Could not fetch alert details for id=%s; using webhook payload",
                alert_id,
            )

    # ---------------------------------------------------------
    # 3. Retrieve observability evidence
    # ---------------------------------------------------------

    logger.info(
        "Querying traces for service=%s",
        service_name,
    )

    traces = mcp_client.query_traces(
        service_name,
        start_time,
        end_time,
    )

    logger.info(
        "Retrieved %d traces",
        len(traces),
    )

    logger.info(
        "Querying logs for service=%s",
        service_name,
    )

    logs = mcp_client.query_logs(
        service_name,
        start_time,
        end_time,
    )

    logger.info(
        "Retrieved %d logs",
        len(logs),
    )

    metric_name = _extract_metric_name(
        payload,
        alert_details,
    )

    logger.info(
        "Querying metric=%s",
        metric_name,
    )

    metrics = mcp_client.query_metrics(
        service_name,
        metric_name,
        start_time,
        end_time,
    )

    logger.info(
        "Retrieved %d metric series",
        len(metrics),
    )

    # ---------------------------------------------------------
    # 4. Build deterministic evidence bundle
    # ---------------------------------------------------------

    bundle = build_evidence_bundle(
        traces,
        logs,
        metrics,
        incident_context=_incident_context(
            payload, alert_details, metric_name, service_name, end_time
        ),
    )

    metric_points = sum(len(series.points) for series in bundle.metrics)
    logger.info(
        "Evidence bundle created: spans=%d logs=%d metrics=%d points=%d",
        len(bundle.spans),
        len(bundle.logs),
        len(bundle.metrics),
        metric_points,
    )

    logger.info(
        "===== EVIDENCE BUNDLE =====\n%s\n===========================",
        bundle.model_dump_json(indent=2),
    )

    # ---------------------------------------------------------
    # 5. Ask LLM to reason over the evidence
    # ---------------------------------------------------------

    hypothesis = analyze_incident(bundle)

    logger.info(
        "===== ROOT CAUSE RESULT =====\n"
        "Summary: %s\n"
        "Confidence: %s\n"
        "Cited IDs: %s\n"
        "Suggested fix: %s\n"
        "Insufficient evidence: %s\n"
        "=============================",
        hypothesis.summary,
        hypothesis.confidence,
        hypothesis.cited_ids,
        hypothesis.suggested_fix,
        hypothesis.insufficient_evidence,
    )

    # ---------------------------------------------------------
    # 6. Create GitHub issue
    # ---------------------------------------------------------

    try:
        issue_url = create_github_issue(
            service_name,
            hypothesis,
            bundle,
            alert_details,
        )

        logger.info(
            "GitHub issue created: %s",
            issue_url,
        )

    except Exception:
        logger.exception("Failed to create GitHub issue")

        issue_url = ""

    # ---------------------------------------------------------
    # 7. Send Slack notification
    # ---------------------------------------------------------

    try:
        send_slack_notification(
            service_name,
            hypothesis,
            issue_url,
            _alert_name(alert_details, payload),
        )

        logger.info(
            "Slack notification sent",
        )

    except Exception:
        logger.exception("Failed to send Slack notification")

    # ---------------------------------------------------------
    # 8. Final investigation result
    # ---------------------------------------------------------

    logger.info(
        "Investigation: service=%s alert=%s metric=%s traces_raw=%d "
        "traces_relevant=%d logs=%d metric_series=%d metric_points=%d "
        "llm_status=%s confidence=%s issue_url=%s",
        service_name,
        _alert_name(alert_details, payload),
        metric_name,
        len(traces),
        len(bundle.spans),
        len(bundle.logs),
        len(bundle.metrics),
        metric_points,
        hypothesis.result_status,
        hypothesis.confidence,
        issue_url,
    )


def _extract_service_name(
    payload: dict[str, Any],
) -> str:
    text = str(payload)

    for candidate in (
        "demo-service",
        "rootcauser-demo-service",
    ):
        if candidate in text:
            return "demo-service"

    labels = payload.get("labels") if isinstance(payload.get("labels"), dict) else {}

    return str(
        labels.get("serviceName")
        or labels.get("service_name")
        or payload.get("serviceName")
        or "demo-service"
    )


def _extract_metric_name(
    payload: dict[str, Any],
    alert_details: dict[str, Any] | None = None,
) -> str:
    """Use alert-rule metric names before webhook text or safe fallback."""
    candidates = _find_metric_names(alert_details or {}) + _find_metric_names(payload)
    if candidates:
        # A/B composite alerts commonly expose sum and count. Query the base metric
        # only when it is explicitly present; otherwise retain the exact rule metric.
        return candidates[0]
    text = str(payload).lower()
    if "downstream" in text or "error" in text:
        return "downstream.errors"
    return "db.query.duration"


def _find_metric_names(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if (
                key in {"metricName", "metric_name", "metric"}
                and isinstance(child, str)
                and "." in child
            ):
                found.append(child)
            found.extend(_find_metric_names(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_find_metric_names(child))
    # preserve query order while removing duplicates
    return list(dict.fromkeys(found))


def _incident_keywords(
    payload: dict[str, Any], alert: dict[str, Any], metric_name: str
) -> list[str]:
    values = [_alert_name(alert, payload), metric_name]
    values.extend(_find_metric_names(alert))
    return values


def _incident_context(
    payload: dict[str, Any],
    alert: dict[str, Any],
    metric_name: str,
    service_name: str,
    alert_time: datetime,
) -> dict[str, Any]:
    """Pass only real webhook/rule semantics into deterministic ranking."""
    terms = _incident_keywords(payload, alert, metric_name)
    terms.extend(_all_strings(alert.get("compositeQuery", {})))
    terms.extend(_all_strings(payload.get("labels", {})))
    normalized = " ".join(terms).lower()
    return {
        "service_name": service_name,
        "alert_timestamp": alert_time.isoformat(),
        "semantic_terms": list(dict.fromkeys(terms)),
        "is_health_alert": any(word in normalized for word in ("health", "readiness", "liveness")),
    }


def _all_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for child in value.values() for text in _all_strings(child)]
    if isinstance(value, list):
        return [text for child in value for text in _all_strings(child)]
    return []


def _alert_name(alert: dict[str, Any], payload: dict[str, Any]) -> str:
    for source in (alert, payload):
        for key in ("alert", "alertname", "ruleName", "name"):
            value = source.get(key)
            if isinstance(value, str) and value:
                return value
            if isinstance(value, dict):
                nested = value.get("name")
                if nested:
                    return str(nested)
    return "unknown-alert"


def _extract_alert_id(
    payload: dict[str, Any],
) -> str | None:
    alerts = payload.get("alerts")
    if isinstance(alerts, list):
        for alert in alerts:
            if not isinstance(alert, dict):
                continue
            labels = alert.get("labels")
            if not isinstance(labels, dict):
                continue
            for key in ("ruleId", "rule_id", "alertId"):
                if labels.get(key):
                    return str(labels[key])

    for key in (
        "ruleId",
        "rule_id",
        "alert_id",
        "alertId",
        "id",
    ):
        if payload.get(key):
            return str(payload[key])

    return None


def _extract_alert_time(
    payload: dict[str, Any],
) -> datetime:
    for key in (
        "startsAt",
        "timestamp",
        "time",
        "triggeredAt",
    ):
        value = payload.get(key)

        if not value:
            continue

        try:
            if isinstance(value, (int, float)):
                return datetime.fromtimestamp(
                    value / 1000 if value > 1e12 else value,
                    tz=UTC,
                )

            return datetime.fromisoformat(
                str(value).replace(
                    "Z",
                    "+00:00",
                )
            )

        except ValueError:
            continue

    return datetime.now(UTC)
