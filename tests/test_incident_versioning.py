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
    monkeypatch.setattr(github_output, "get_settings", lambda: _settings())
    monkeypatch.setattr(github_output, "_write_local_issue", lambda *_args: None)
    monkeypatch.setattr(
        github_output.requests,
        "post",
        lambda _url, **kwargs: calls.append(kwargs["json"]) or _Response(10, "https://issue/10"),
    )
    url = github_output.create_github_issue("svc", _hypothesis(), EvidenceBundle(), {"id": "rule-a"})
    assert url == "https://issue/10"
    assert "Incident Version:** 1" in str(calls[0]["body"])


def test_repeated_firing_updates_same_issue_and_increments_version(monkeypatch) -> None:
    github_output._ACTIVE_INCIDENTS.clear()
    updates: list[dict[str, object]] = []
    monkeypatch.setattr(github_output, "get_settings", lambda: _settings())
    monkeypatch.setattr(github_output, "_write_local_issue", lambda *_args: None)
    monkeypatch.setattr(github_output.requests, "post", lambda *_args, **_kwargs: _Response(10, "https://issue/10"))
    monkeypatch.setattr(
        github_output.requests,
        "patch",
        lambda _url, **kwargs: updates.append(kwargs["json"]) or _Response(10, "https://issue/10"),
    )
    github_output.create_github_issue("svc", _hypothesis(), EvidenceBundle(), {"id": "rule-a"})
    url = github_output.create_github_issue("svc", _hypothesis(), EvidenceBundle(), {"id": "rule-a"})
    assert url == "https://issue/10"
    assert "Incident Version:** 2" in str(updates[0]["body"])


def test_new_alert_identity_creates_new_issue(monkeypatch) -> None:
    github_output._ACTIVE_INCIDENTS.clear()
    created: list[str] = []
    monkeypatch.setattr(github_output, "get_settings", lambda: _settings())
    monkeypatch.setattr(github_output, "_write_local_issue", lambda *_args: None)
    monkeypatch.setattr(
        github_output.requests,
        "post",
        lambda _url, **_kwargs: created.append("post") or _Response(len(created), f"https://issue/{len(created)}"),
    )
    github_output.create_github_issue("svc", _hypothesis(), EvidenceBundle(), {"id": "rule-a"})
    github_output.create_github_issue("svc", _hypothesis(), EvidenceBundle(), {"id": "rule-b"})
    assert created == ["post", "post"]


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        github_token="token", github_repo="owner/repo", signoz_public_url="http://signoz"
    )
