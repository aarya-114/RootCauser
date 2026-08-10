# Implementation Guide

RootCauser is an automated incident-investigation prototype built around deterministic evidence selection and grounded LLM reasoning.

## Runtime flow

1. `copilot-agent/main.py` receives `POST /webhook/alert`, validates the optional shared secret, and starts background processing.
2. It extracts the service, time window, and rule UUID. A real SigNoz UUID may be at `payload["alerts"][0]["labels"]["ruleId"]`.
3. `copilot-agent/mcp_client.py` retrieves traces, logs, metrics, and rule details from SigNoz REST.
4. `copilot-agent/evidence_bundler.py` normalizes and ranks the available records into `EvidenceBundle`.
5. `copilot-agent/reasoning.py` sends the bundle to OpenRouter and validates the returned JSON citations.
6. `github_output.py` renders and creates the incident issue; `slack_output.py` sends its follow-up notification when configured.

## Module responsibilities

- `main.py`: webhook parsing, alert context, retrieval orchestration, and investigation logging.
- `mcp_client.py`: authenticated SigNoz v5 queries and UUID v2 rule lookup. Metrics are retrieved as builder aggregations and normalized from `aggregations[].series[].values[]` into bounded series/points. Log retrieval is optional and returns an empty list after a query failure.
- `evidence_bundler.py`: Pydantic evidence models, nested record normalization, deterministic relevance ranking, diversity limits, and `relevance_score` / `relevance_reasons` metadata.
- `reasoning.py`: OpenRouter request, structured response parsing, citation validation, confidence calculation, and insufficient-evidence handling.
- `github_output.py` and `slack_output.py`: external investigation reporting.

## Ranking and grounding

Ranking occurs before LLM reasoning. It uses service match, alert-rule/composite-query semantics, trace and log IDs, trace membership, alert-time proximity, error/WARN status, secondary duration, health penalties, duplicate suppression, and per-trace limits. This is deterministic so that evidence selection can be tested and reviewed separately from model behavior.

The LLM is asked to reason only from the selected bundle. A cited trace ID, span ID, or metric name must be literally present in that bundle. Invalid citations, malformed output, unavailable telemetry, and model-declared uncertainty produce an insufficient-evidence result rather than an unsupported root cause.

## External dependencies

SigNoz is the telemetry source. OpenRouter is used through `https://openrouter.ai/api/v1/chat/completions` with the configurable `LLM_MODEL_NAME`. GitHub issue creation and Slack notification require their respective configured credentials. These dependencies are intentionally optional for local unit testing.
