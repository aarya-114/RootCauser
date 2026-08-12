# Implementation Guide

RootCauser is an automated incident-investigation prototype built around deterministic evidence selection, grounded LLM reasoning, and stateful GitHub incident reporting.

---

## Runtime Workflow

1. **Webhook Ingestion:** [`copilot-agent/main.py`](file:///c:/Users/Om/Desktop/RootCauser/copilot-agent/main.py) receives `POST /webhook/alert`, checks the optional `X-Rootcauser-Secret` header, and schedules background triage via FastAPI `BackgroundTasks`.
2. **Context Extraction:** `process_alert()` extracts the target service name, time window, firing alert name, status (`FIRING`/`RESOLVED`), and alert rule UUID (`alerts[0].labels.ruleId`).
3. **Telemetry Retrieval:** [`copilot-agent/mcp_client.py`](file:///c:/Users/Om/Desktop/RootCauser/copilot-agent/mcp_client.py) queries traces, logs, metrics, and rule details from SigNoz REST endpoints (`POST /api/v5/query_range` and `GET /api/v2/rules/{uuid}`).
4. **Deterministic Bundling:** [`copilot-agent/evidence_bundler.py`](file:///c:/Users/Om/Desktop/RootCauser/copilot-agent/evidence_bundler.py) normalizes telemetry records, scores relevance, applies diversity limits, and builds an `EvidenceBundle`.
5. **LLM Reasoning & Validation:** [`copilot-agent/reasoning.py`](file:///c:/Users/Om/Desktop/RootCauser/copilot-agent/reasoning.py) sends the bundle to OpenRouter (`gpt-4o-mini`) and programmatically verifies that all returned citations exist in the bundle.
6. **Incident State & Output:** [`copilot-agent/github_output.py`](file:///c:/Users/Om/Desktop/RootCauser/copilot-agent/github_output.py) computes a SHA-256 fingerprint from service, alert name, and normalized labels to create or update the GitHub issue with `Incident Version` tracking. [`copilot-agent/slack_output.py`](file:///c:/Users/Om/Desktop/RootCauser/copilot-agent/slack_output.py) dispatches a Slack summary notification.

---

## Module Breakdown

### `copilot-agent/main.py`
* Serves `/webhook/alert` and `/health` endpoints.
* Extracts service name, incident time window (default: 10m), and rule UUID.
* Handles explicit `RESOLVED` status notifications by marking active incident fingerprints resolved.

### `copilot-agent/mcp_client.py`
* Interacts with SigNoz REST v5 `/api/v5/query_range` and v2 rules `/api/v2/rules/{uuid}` APIs.
* Normalizes raw trace, log, and metric JSON structures.
* Handles ClickHouse raw log query fallback: if log query fails, logs warning and returns `[]`, allowing trace/metric triage to continue.

### `copilot-agent/evidence_bundler.py`
* Encapsulates evidence data contracts (`SpanEvidence`, `LogEvidence`, `MetricSeries`, `EvidenceBundle`).
* Scores spans on semantic matches (+35), log correlation (+70-100), errors (+40), proximity (+15-30), while applying health penalties (-120).
* Enforces per-trace diversity limits (max 2 spans per trace, max 5 spans total).

### `copilot-agent/reasoning.py`
* Calls OpenRouter OpenAI-compatible chat completions API with `temperature=0.1` and `json_object` format.
* Validates literal evidence citations against `bundle.searchable_text()`. Returns `CITATION_VALIDATION_FAILED` status if unverified IDs exist.
* Applies `_ground_timeout_remediation()` to re-frame timeout increases as mitigations rather than confirmed root fixes.

### `copilot-agent/github_output.py` & `copilot-agent/slack_output.py`
* Generates GFM markdown report sections (Evidence Summary, Evidence Chain, Confidence Breakdown, Timeline, Coverage).
* Maintains in-memory `_ACTIVE_INCIDENTS` map to PATCH active issues and increment version numbers.
* Sends formatted Slack alerts when `SLACK_WEBHOOK_URL` is configured.

---

## Testing & Verification

Unit tests in `tests/` execute completely offline without live SigNoz or OpenRouter APIs:

```powershell
venv\Scripts\python.exe -m pytest -v
venv\Scripts\python.exe -m ruff check copilot-agent tests
```
