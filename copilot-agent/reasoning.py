"""LLM reasoning with strict citation validation."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import requests
from config import get_settings
from evidence_bundler import EvidenceBundle
from pydantic import BaseModel, Field

PROMPT_DIR = Path(__file__).parent / "prompts"
RETRY_DELAY_SECONDS = 2.0


class RootCauseHypothesis(BaseModel):
    summary: str
    cited_ids: list[str] = Field(default_factory=list)
    suggested_fix: str
    insufficient_evidence: bool = False
    confidence: str = "Insufficient Evidence"


def analyze_incident(bundle: EvidenceBundle) -> RootCauseHypothesis:
    """Call the configured LLM once and return a citation-checked hypothesis."""
    if bundle.is_empty():
        return _insufficient("No usable traces, logs, or metrics were retrieved.")

    response_text = _call_llm(bundle)
    return parse_and_validate_hypothesis(response_text, bundle)


def parse_and_validate_hypothesis(
    response_text: str, bundle: EvidenceBundle
) -> RootCauseHypothesis:
    """Parse strict JSON and reject any unverified citations."""
    try:
        payload = json.loads(_strip_json_fence(response_text))
        hypothesis = RootCauseHypothesis(**payload)
    except (json.JSONDecodeError, TypeError, ValueError):
        return _insufficient("LLM response was not valid RootCauser JSON.")

    if hypothesis.insufficient_evidence:
        return _insufficient(hypothesis.summary or "The model reported insufficient evidence.")

    searchable = bundle.searchable_text()
    if any(cited_id not in searchable for cited_id in hypothesis.cited_ids):
        return _insufficient("The model cited an ID that is not present in the evidence bundle.")

    hypothesis.confidence = _compute_confidence(hypothesis.cited_ids, bundle)
    return hypothesis


def _call_llm(bundle: EvidenceBundle) -> str:
    settings = get_settings()
    if not settings.llm_api_key:
        return json.dumps(
            {
                "summary": (
                    "LLM_API_KEY is not configured, so RootCauser cannot produce "
                    "a grounded hypothesis."
                ),
                "cited_ids": [],
                "suggested_fix": "Set LLM_API_KEY and rerun the investigation.",
                "insufficient_evidence": True,
            }
        )

    system_prompt = _read_prompt("system_prompt.md")
    investigation_prompt = _read_prompt("investigation_prompt.md").replace(
        "{{ evidence_bundle_json }}",
        bundle.model_dump_json(indent=2),
    )
    reasoning_prompt = _read_prompt("reasoning_prompt.md")

    payload = {
        "model": settings.llm_model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{investigation_prompt}\n\n{reasoning_prompt}"},
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }

    for attempt in (1, 2):
        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            return str(data["choices"][0]["message"]["content"])
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError, KeyError) as exc:
            if attempt == 1:
                time.sleep(RETRY_DELAY_SECONDS)
                continue
            return json.dumps(
                {
                    "summary": f"LLM request failed after retry: {exc}",
                    "cited_ids": [],
                    "suggested_fix": "Check LLM credentials, network access, and model name.",
                    "insufficient_evidence": True,
                }
            )

    return "{}"


def _compute_confidence(cited_ids: list[str], bundle: EvidenceBundle) -> str:
    cited_text = "\n".join(cited_ids)
    has_span = any(
        span.span_id in cited_text or span.trace_id in cited_text for span in bundle.spans
    )
    has_metric = any(metric.name in cited_text for metric in bundle.metrics)
    if has_span and has_metric:
        return "High"
    if has_span or has_metric:
        return "Medium"
    return "Low"


def _read_prompt(filename: str) -> str:
    return (PROMPT_DIR / filename).read_text(encoding="utf-8")


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL)
    return match.group(1).strip() if match else stripped


def _insufficient(summary: str) -> RootCauseHypothesis:
    return RootCauseHypothesis(
        summary=summary,
        cited_ids=[],
        suggested_fix="Collect more evidence or widen the incident time window.",
        insufficient_evidence=True,
        confidence="Insufficient Evidence",
    )
