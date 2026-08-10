"""GitHub Issue output for RootCauser investigations."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any

import requests
from config import get_settings
from evidence_bundler import EvidenceBundle
from reasoning import RootCauseHypothesis

RETRY_DELAY_SECONDS = 2.0
ARTIFACT_DIR = Path(__file__).parent / "artifacts"
_ACTIVE_INCIDENTS: dict[str, dict[str, Any]] = {}
_INCIDENT_LOCK = Lock()


def create_github_issue(
    service_name: str,
    hypothesis: RootCauseHypothesis,
    bundle: EvidenceBundle,
    alert: dict[str, Any] | None = None,
) -> str | None:
    """Create Version 1 or update the active issue for the same rule identity."""
    settings = get_settings()
    alert = alert or {}
    identity = _incident_identity(alert)
    with _INCIDENT_LOCK:
        active = _ACTIVE_INCIDENTS.get(identity) if identity else None
        version = int(active["version"]) + 1 if active else 1
    title = f"[RootCauser] {service_name}: {hypothesis.confidence} root-cause hypothesis"
    body = render_issue_markdown(service_name, hypothesis, bundle, alert, version)
    _write_local_issue(title, body)

    if not settings.github_token or settings.github_repo == "your-org/your-repo":
        _remember_incident(identity, version, None, None)
        return None

    url = f"https://api.github.com/repos/{settings.github_repo}/issues"
    headers = {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {"title": title, "body": body, "labels": ["rootcauser", "incident"]}

    if active and active.get("issue_number") is not None:
        issue_number = active["issue_number"]
        issue_url = f"{url}/{issue_number}"
        for attempt in (1, 2):
            try:
                response = requests.patch(issue_url, headers=headers, json=payload, timeout=30)
                response.raise_for_status()
                updated = response.json()
                result_url = str(updated.get("html_url") or active.get("issue_url") or "")
                _remember_incident(identity, version, issue_number, result_url)
                return result_url or None
            except (requests.ConnectionError, requests.Timeout, requests.HTTPError):
                if attempt == 1:
                    time.sleep(RETRY_DELAY_SECONDS)
                    continue
                raise

    for attempt in (1, 2):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            created = response.json()
            result_url = str(created.get("html_url") or "")
            _remember_incident(identity, version, created.get("number"), result_url)
            return result_url or None
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
    incident_version: int = 1,
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
    report = build_report_facts(bundle)
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
        incident_version=incident_version,
        evidence_summary=report["evidence_summary"],
        evidence_chain=report["evidence_chain"],
        confidence_breakdown=report["confidence_breakdown"],
        timeline_section=(
            f"### Incident Timeline\n\n{report['timeline']}" if report["timeline"] else ""
        ),
        evidence_coverage=report["evidence_coverage"],
        evidence_json=bundle.model_dump_json(indent=2),
    )


def clear_active_incident(identity: str | None) -> None:
    """Forget the active issue when SigNoz reliably reports a resolved firing."""
    if not identity:
        return
    with _INCIDENT_LOCK:
        _ACTIVE_INCIDENTS.pop(identity, None)


def _remember_incident(
    identity: str | None, version: int, issue_number: Any, issue_url: str | None
) -> None:
    if not identity:
        return
    with _INCIDENT_LOCK:
        _ACTIVE_INCIDENTS[identity] = {
            "version": version,
            "issue_number": issue_number,
            "issue_url": issue_url,
        }


def _incident_identity(alert: dict[str, Any]) -> str | None:
    for key in ("_incident_identity", "ruleId", "rule_id", "alertId", "id"):
        value = alert.get(key)
        if value:
            return str(value)
    return None


def build_report_facts(bundle: EvidenceBundle) -> dict[str, str]:
    """Render deterministic incident facts from selected evidence only."""
    correlated_logs = [
        log for log in bundle.logs if "matches selected span" in " ".join(log.relevance_reasons)
    ]
    metric_series = [series for series in bundle.metrics if series.points]
    summary_rows = [
        ("Traces", _trace_observation(bundle), _relevance(bundle.spans)),
        ("Logs", _log_observation(bundle.logs), _relevance(bundle.logs)),
        ("Metrics", _metric_observation(metric_series), _relevance(metric_series)),
        (
            "Correlation",
            f"{len(correlated_logs)} logs matched selected trace/span IDs"
            if correlated_logs
            else "No selected trace/log ID matches",
            "High" if correlated_logs else "Unavailable",
        ),
    ]
    evidence_summary = "\n".join(
        ["| Evidence | Observation | Relevance |", "|---|---|---|"]
        + [f"| {kind} | {observation} | {relevance} |" for kind, observation, relevance in summary_rows]
    )

    chain: list[str] = []
    if bundle.spans:
        chain.append(_trace_observation(bundle))
    if bundle.logs:
        chain.append(_log_observation(bundle.logs))
    if metric_series:
        chain.append(_metric_observation(metric_series))
    if correlated_logs:
        chain.append(f"{len(correlated_logs)} selected logs share trace or span IDs with selected spans")
    if not chain:
        chain.append("No usable telemetry evidence was selected")
    evidence_chain = "\n".join(f"{index}. {fact}." for index, fact in enumerate(chain, 1))

    supporting = []
    missing = []
    if bundle.spans:
        supporting.append("Repeated relevant traces" if len(bundle.spans) > 1 else "Relevant trace")
    else:
        missing.append("No selected traces")
    if bundle.logs:
        supporting.append("Selected logs")
    else:
        missing.append("No selected logs")
    if metric_series:
        supporting.append("Relevant metric data")
    else:
        missing.append("No metric points")
    if correlated_logs:
        supporting.append("Trace/log correlation")
    else:
        missing.append("No selected trace/log ID correlation")
    confidence_breakdown = "\n".join(
        ["**Supporting signals**"]
        + [f"- ✓ {item}" for item in supporting]
        + ["", "**Missing evidence**"]
        + [f"- {item}" for item in missing]
    )

    coverage_rows = [
        ("Traces", bool(bundle.spans)),
        ("Logs", bool(bundle.logs)),
        ("Metrics", bool(metric_series)),
        ("Trace/log correlation", bool(correlated_logs)),
    ]
    evidence_coverage = "\n".join(
        ["| Signal | Available | Used |", "|---|---:|---:|"]
        + [f"| {name} | {'✓' if available else '—'} | {'✓' if available else '—'} |" for name, available in coverage_rows]
    )
    return {
        "evidence_summary": evidence_summary,
        "evidence_chain": evidence_chain,
        "confidence_breakdown": confidence_breakdown,
        "timeline": _timeline(bundle, metric_series),
        "evidence_coverage": evidence_coverage,
    }


def _trace_observation(bundle: EvidenceBundle) -> str:
    if not bundle.spans:
        return "No selected traces"
    names = ", ".join(f"`{name}`" for name in sorted({span.name for span in bundle.spans}))
    durations = [span.duration_ms for span in bundle.spans]
    return f"{len(bundle.spans)} selected spans ({names}); duration {min(durations):g}–{max(durations):g} ms"


def _log_observation(logs: list[Any]) -> str:
    if not logs:
        return "No selected logs"
    severities = ", ".join(sorted({log.severity for log in logs}))
    return f"{len(logs)} selected logs with severity {severities}"


def _metric_observation(series: list[Any]) -> str:
    if not series:
        return "No metric points"
    observations = []
    for item in series:
        first, last = item.points[0].value, item.points[-1].value
        observations.append(f"`{item.name}` {first:g} → {last:g}")
    return ", ".join(observations)


def _relevance(items: list[Any]) -> str:
    scores = [getattr(item, "relevance_score", 0) for item in items]
    if not items:
        return "Unavailable"
    return "High" if max(scores, default=0) >= 60 else "Available"


def _timeline(bundle: EvidenceBundle, metric_series: list[Any]) -> str:
    events: list[tuple[datetime, str]] = []
    for span in bundle.spans:
        timestamp = _parse_timestamp(span.timestamp)
        if timestamp:
            events.append((timestamp, f"Selected span `{span.name}` ({span.duration_ms:g} ms)"))
    for log in bundle.logs[:3]:
        timestamp = _parse_timestamp(log.timestamp)
        if timestamp:
            events.append((timestamp, f"{log.severity} log: {log.body}"))
    for series in metric_series:
        point = series.anomaly_point or series.points[-1]
        timestamp = _parse_timestamp(point.timestamp)
        if timestamp:
            events.append((timestamp, f"Metric `{series.name}` value {point.value:g}"))
    if not events:
        return ""
    rows = ["| Time | Evidence |", "|---|---|"]
    for timestamp, description in sorted(events)[:8]:
        rows.append(f"| {timestamp.isoformat().replace('+00:00', 'Z')} | {description} |")
    return "\n".join(rows)


def _parse_timestamp(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)) or str(value).isdigit():
            numeric = float(value)
            return datetime.fromtimestamp(numeric / 1000 if numeric > 1e12 else numeric, tz=UTC)
        timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=UTC)
    except (TypeError, ValueError, OSError):
        return None


def _write_local_issue(title: str, body: str) -> None:
    ARTIFACT_DIR.mkdir(exist_ok=True)
    safe_title = "".join(ch if ch.isalnum() else "-" for ch in title.lower()).strip("-")[:80]
    path = ARTIFACT_DIR / f"{int(time.time())}-{safe_title}.md"
    path.write_text(f"# {title}\n\n{body}\n", encoding="utf-8")
