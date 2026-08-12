from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

AGENT_PATH = Path(__file__).resolve().parents[1] / "copilot-agent"
sys.path.insert(0, str(AGENT_PATH))

import github_output  # noqa: E402
from evidence_bundler import EvidenceBundle  # noqa: E402
from reasoning import RootCauseHypothesis  # noqa: E402


class _Response:
    def __init__(self, number: int, url: str) -> None:
        self._payload = {"number": number, "html_url": url}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


def _hypothesis() -> RootCauseHypothesis:
    return RootCauseHypothesis(summary="Observed evidence.", suggested_fix="Investigate it.")


def test_first_firing_creates_version_one_issue(monkeypatch) -> None:
    github_output._ACTIVE_INCIDENTS.clear()
    calls: list[dict[str, object]] = []
    alert = {
        "alertname": "rootcauser-downstream-payment-timeout",
        "labels": {"serviceName": "demo-service", "severity": "critical"},
    }
    monkeypatch.setattr(github_output, "get_settings", lambda: _settings())
    monkeypatch.setattr(github_output, "_write_local_issue", lambda *_args: None)
    monkeypatch.setattr(
        github_output.requests,
        "post",
        lambda _url, **kwargs: calls.append(kwargs["json"]) or _Response(10, "https://issue/10"),
    )
    url = github_output.create_github_issue("svc", _hypothesis(), EvidenceBundle(), alert)
    assert url == "https://issue/10"
    assert "Incident Version:** 1" in str(calls[0]["body"])


def test_repeated_firing_updates_same_issue_and_increments_version(monkeypatch) -> None:
    github_output._ACTIVE_INCIDENTS.clear()
    updates: list[dict[str, object]] = []
    alert = {
        "alertname": "rootcauser-downstream-payment-timeout",
        "labels": {"serviceName": "demo-service", "severity": "critical"},
    }
    monkeypatch.setattr(github_output, "get_settings", lambda: _settings())
    monkeypatch.setattr(github_output, "_write_local_issue", lambda *_args: None)
    monkeypatch.setattr(
        github_output.requests,
        "post",
        lambda _url, **kwargs: updates.append(kwargs["json"]) or _Response(10, "https://issue/10"),
    )
    monkeypatch.setattr(
        github_output.requests,
        "patch",
        lambda _url, **kwargs: updates.append(kwargs["json"]) or _Response(10, "https://issue/10"),
    )
    github_output.create_github_issue("svc", _hypothesis(), EvidenceBundle(), alert)
    url = github_output.create_github_issue("svc", _hypothesis(), EvidenceBundle(), alert)
    assert url == "https://issue/10"
    assert "Incident Version:** 1" in str(updates[0]["body"])
    assert "Incident Version:** 2" in str(updates[1]["body"])


def test_resolved_then_firing_creates_new_issue_version_one(monkeypatch) -> None:
    github_output._ACTIVE_INCIDENTS.clear()
    created: list[dict[str, object]] = []
    alert = {
        "alertname": "rootcauser-downstream-payment-timeout",
        "labels": {"serviceName": "demo-service", "severity": "critical"},
    }
    monkeypatch.setattr(github_output, "get_settings", lambda: _settings())
    monkeypatch.setattr(github_output, "_write_local_issue", lambda *_args: None)
    monkeypatch.setattr(
        github_output.requests,
        "post",
        lambda _url, **kwargs: created.append(kwargs["json"]) or _Response(len(created), f"https://issue/{len(created)}"),
    )
    github_output.create_github_issue("svc", _hypothesis(), EvidenceBundle(), alert)
    github_output.resolve_incident("svc", alert)
    github_output.create_github_issue("svc", _hypothesis(), EvidenceBundle(), alert)
    assert len(created) == 2
    assert "Incident Version:** 1" in str(created[0]["body"])
    assert "Incident Version:** 1" in str(created[1]["body"])
    assert github_output._ACTIVE_INCIDENTS


def test_different_fingerprint_creates_different_incident(monkeypatch) -> None:
    github_output._ACTIVE_INCIDENTS.clear()
    created: list[str] = []
    monkeypatch.setattr(github_output, "get_settings", lambda: _settings())
    monkeypatch.setattr(github_output, "_write_local_issue", lambda *_args: None)
    monkeypatch.setattr(
        github_output.requests,
        "post",
        lambda _url, **_kwargs: created.append("post") or _Response(len(created), f"https://issue/{len(created)}"),
    )
    base = {
        "alertname": "rootcauser-downstream-payment-timeout",
        "labels": {"serviceName": "demo-service", "severity": "critical"},
    }
    variant = {
        "alertname": "rootcauser-downstream-payment-timeout",
        "labels": {"serviceName": "demo-service", "severity": "warning"},
    }
    github_output.create_github_issue("svc", _hypothesis(), EvidenceBundle(), base)
    github_output.create_github_issue("svc", _hypothesis(), EvidenceBundle(), variant)
    assert created == ["post", "post"]


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        github_token="token", github_repo="owner/repo", signoz_public_url="http://signoz"
    )
