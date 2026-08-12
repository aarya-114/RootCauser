# RootCauser Architecture

```text
SigNoz Alert → FastAPI Webhook → Evidence Retrieval → Deterministic Ranking
→ LLM Reasoning → Citation Validation → GitHub Issue / Slack Notification
```

`demo-service` emits OpenTelemetry traces, logs, and metrics through the collector to SigNoz. SigNoz alerts call `copilot-agent/main.py` at `POST /webhook/alert`.

The webhook extracts the service and incident window. Real SigNoz payloads can provide the rule UUID at `alerts[0].labels.ruleId`; RootCauser uses that UUID to resolve the full rule with `GET /api/v2/rules/{uuid}` and then preserves the firing alert name for reporting. Evidence retrieval uses `POST /api/v5/query_range` for traces, logs, and metrics.

## Deterministic evidence before reasoning

The LLM is not responsible for telemetry retrieval or relevance selection. `evidence_bundler.py` ranks evidence first using service match, alert/rule/composite-query semantics, trace and log correlation, multiple spans in one trace, alert-time proximity, error/WARN status, secondary duration, health penalties, duplicate suppression, and per-trace diversity limits. Selected spans and logs include `relevance_score` and `relevance_reasons`.

This keeps the LLM input bounded and auditable. It also prevents an unrelated long-running health span from winning solely because of duration.

## Graceful evidence handling

Traces, logs, and metrics are independent sources. Metric queries use SigNoz v5 builder aggregations and normalize the returned `aggregations[].series[].values[]` timestamp/value records into bounded evidence series. SigNoz log querying can be unavailable on deployments that reject JSON* expressions; the log client returns an empty list after logging the failure so trace and metric investigation continues. No telemetry is fabricated.

## Reasoning and outputs

`reasoning.py` calls OpenRouter's OpenAI-compatible chat-completions endpoint with `LLM_MODEL_NAME`. Its JSON response is accepted only when every cited ID is present in the evidence bundle. Unsupported citations, malformed output, empty evidence, and legitimate uncertainty result in an insufficient-evidence outcome rather than an invented cause.

`github_output.py` creates the incident issue when configured. Its evidence summary, evidence chain, confidence breakdown, timeline, coverage table, and raw evidence bundle are generated deterministically from the selected evidence; only the hypothesis and suggested fix come from the LLM. `slack_output.py` sends a concise notification after the issue result is available.

## Active incident versioning

`github_output.py` keeps a process-local active-incident map keyed by a deterministic fingerprint derived from the service, alert name, and normalized labels supplied by `main.py`. The first firing creates Version 1; repeated active firings PATCH the same GitHub issue and increment the version. When a webhook explicitly reports `RESOLVED`, `main.py` marks that fingerprint as resolved so a later firing creates a new issue. This state is intentionally not persistent: an agent restart, missing stable fingerprint, or a webhook without a reliable resolved state can result in a new Version 1 issue.
