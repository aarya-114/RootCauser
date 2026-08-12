# RootCauser Technical Architecture

This document provides a comprehensive technical overview of RootCauser's architecture, data contracts, scoring algorithms, citation validation rules, incident state management, and external integration mechanisms.

---

## 1. High-Level System Architecture

```text
+-----------------------------------------------------------------------------------+
|                                  SigNoz Platform                                  |
|  +-----------------------+   +----------------------+   +----------------------+  |
|  | ClickHouse Telemetry  |   | PostgreSQL Metadata  |   | SigNoz Alertmanager  |  |
|  +-----------------------+   +----------------------+   +----------------------+  |
+--------------------------------------------------------------------|--------------+
                                                                     |
                                                                     | POST /webhook/alert
                                                                     v
+-----------------------------------------------------------------------------------+
|                            RootCauser Copilot Agent                               |
|                                                                                   |
|  +-----------------------+    +-----------------------+    +-------------------+  |
|  |     main.py           |    |     mcp_client.py       |    |evidence_bundler.py|  |
|  | (Webhook Receiver)    |--->| (SigNoz REST v5/v2)   |--->| (Scoring Engine)  |  |
|  +-----------------------+    +-----------------------+    +-------------------+  |
|                                                                      |            |
|  +-----------------------+    +-----------------------+              v            |
|  |   github_output.py    |<---|     reasoning.py      |<--------------------------+
|  | (Incident State / GFM)|    | (Citation Validation) |                           |
|  +-----------------------+    +-----------------------+                           |
+--------------|----------------------------|---------------------------------------+
               |                            |
               | POST / PATCH               | POST
               v                            v
   +-----------------------+    +-----------------------+
   |   GitHub Issues API   |    |     Slack Webhook     |
   +-----------------------+    +-----------------------+
```

---

## 2. Ingestion & Webhook Workflow

### 1. Endpoint & Authentication
SigNoz alerts are delivered to `POST /webhook/alert` handled by `receive_alert()` in [`copilot-agent/main.py`](file:///c:/Users/Om/Desktop/RootCauser/copilot-agent/main.py).
* **Secret Verification:** If `WEBHOOK_SHARED_SECRET` is configured, the request must supply a matching `X-Rootcauser-Secret` header. Otherwise, HTTP 401 Unauthorized is returned immediately.
* **Asynchronous Acknowledgment:** To prevent alertmanager HTTP timeouts, `receive_alert()` parses the JSON payload, dispatches `process_alert()` as a FastAPI `BackgroundTask`, and immediately returns `{"status": "accepted"}` with HTTP 202 status.

### 2. Context Extraction
`process_alert()` extracts core incident metadata:
* **Service Name:** Extracted via `_extract_service_name()` from payload labels (`serviceName`, `service_name`). Defaults to `"demo-service"`.
* **Incident Time Window:** `_extract_alert_time()` parses ISO timestamp or epoch integer (`startsAt`, `timestamp`). `start_time` is calculated as `end_time - incident_window_minutes` (default: 10 minutes).
* **Alert Rule Identity:** `_extract_alert_id()` checks `alerts[0].labels.ruleId`. If present, `mcp_client.get_alert_details(alert_id)` queries rule definitions via `GET /api/v2/rules/{uuid}`.
* **Alert Status:** Evaluated via `_extract_alert_status()`. Recognizes explicit `"FIRING"` and `"RESOLVED"` states.

---

## 3. Telemetry Retrieval (`mcp_client.py`)

RootCauser interfaces directly with SigNoz REST endpoints:

### 1. Traces (`query_traces`)
Queries `POST /api/v5/query_range` with signal `"traces"`, filter `service.name = '{service_name}'`, and orders by timestamp descending (limit 100).
* Selects: `service.name`, `name`, `durationNano`, `statusCode`, `traceID`, `spanID`, `timestamp`.
* Converts duration from nanoseconds to milliseconds (`durationNano / 1,000,000`).

### 2. Logs (`query_logs`)
Queries `POST /api/v5/query_range` with signal `"logs"` and filter `service.name = '{service_name}'`.
* **ClickHouse Compatibility Fallback:** To avoid SQL syntax errors on ClickHouse deployments that reject `JSON_VALUE`/`JSON_EXISTS` expressions, `query_logs()` strips `selectFields` and refrains from filtering by `severityText`.
* **Failure Resilience:** If log querying fails due to network error or SQL incompatibility, `query_logs()` catches the exception, logs a warning, and returns `[]`. Triage proceeds using trace and metric telemetry.

### 3. Metrics (`query_metrics`)
Queries `POST /api/v5/query_range` using a `builder_query` with:
* `timeAggregation: "avg"`, `spaceAggregation: "sum"`.
* Normalizes time series from nested SigNoz v5 response shapes: `results[].aggregations[].series[].values[]`.
* Bounds outputs to a maximum of 20 series and 200 points per series.

---

## 4. Deterministic Evidence Bundling & Scoring (`evidence_bundler.py`)

Raw telemetry is normalized into Pydantic models (`SpanEvidence`, `LogEvidence`, `MetricSeries`, `EvidenceBundle`).

```
                    +-----------------------------------+
                    |          SpanEvidence             |
                    +-----------------------------------+
                    | trace_id        : str             |
                    | span_id         : str             |
                    | name            : str             |
                    | duration_ms     : float           |
                    | is_error        : bool            |
                    | relevance_score : int             |
                    | relevance_reasons: list[str]      |
                    +-----------------------------------+
```

### Deterministic Span Scoring Formula

Each candidate trace span is assigned a relevance score:

$$\text{Relevance Score} = S_{\text{semantic}} + S_{\text{correlation}} + S_{\text{error}} + S_{\text{proximity}} + S_{\text{service}} - P_{\text{health}}$$

#### Scoring Breakdown:
1. **Semantic Match ($S_{\text{semantic}}$):** $+35 \times (\text{matching alert keywords in span name})$.
2. **Log Correlation ($S_{\text{correlation}}$):**
   * $+100$ if `span.span_id` exists in `log_span_ids`.
   * $+70$ if `span.trace_id` exists in `log_trace_ids`.
   * $+20$ if `trace_id` contains multiple correlated spans.
3. **Error Status ($S_{\text{error}}$):** $+40$ if `span.is_error` is `True` or status contains `"error"`.
4. **Temporal Proximity ($S_{\text{proximity}}$):**
   * $+30$ if $|\text{span.timestamp} - \text{alert.timestamp}| \le 60\text{ seconds}$.
   * $+15$ if $|\text{span.timestamp} - \text{alert.timestamp}| \le 300\text{ seconds}$.
5. **Service Match ($S_{\text{service}}$):** $+25$ if `span.service.name == target_service`.
6. **Health Check Penalty ($P_{\text{health}}$):** $-120$ if span name contains `health`, `readiness`, or `liveness` AND the alert is not a health alert.

### Supporting Filter & Diversity Controls
* **Supporting Span Threshold (`_is_supporting_span`):** A span is retained ONLY if `relevance_score > 0`, `is_error == True`, or its IDs match a log record. Routine uncorrelated spans are excluded.
* **Per-Trace Diversity Limit (`_select_diverse_spans`):** Sorts candidate spans by relevance score and duration. Limits selection to at most **2 spans per `trace_id`** and caps the total bundle at **5 spans**.

---

## 5. Grounded LLM Reasoning & Citation Validation (`reasoning.py`)

`analyze_incident()` passes the formatted JSON bundle to OpenRouter (`gpt-4o-mini`, `temperature=0.1`, `response_format={"type": "json_object"}`).

```
                                +-----------------------+
                                |  EvidenceBundle JSON  |
                                +-----------------------+
                                            |
                                            v
                                +-----------------------+
                                |   OpenRouter API      |
                                +-----------------------+
                                            |
                                            v
                                +-----------------------+
                                | RootCauseHypothesis   |
                                | JSON Payload          |
                                +-----------------------+
                                            |
                                            v
                                +-----------------------+
                                | Citation Validator    |
                                +-----------------------+
                                  /                   \
                        All Cited IDs                Unverified
                          Present                    Citation
                             |                          |
                             v                          v
                      SUCCESS Status         CITATION_VALIDATION_FAILED
                                             (Insufficient Evidence)
```

### Citation Checking Rule
The LLM response must include a `cited_ids` array. `parse_and_validate_hypothesis()` checks every cited string against `bundle.searchable_text()`:

```python
searchable = bundle.searchable_text()

if any(cited_id not in searchable for cited_id in hypothesis.cited_ids):
    return _result(
        "CITATION_VALIDATION_FAILED",
        "The model cited an ID that is not present in the evidence bundle.",
    )
```

### Remediation Grounding Guardrail
`_ground_timeout_remediation()` checks if the LLM suggests "increasing the timeout" when timeout evidence exists. If ungrounded, it re-frames the remediation to emphasize investigating downstream latency first, treating timeout increases only as temporary mitigations.

### Confidence Classification Matrix
* **High Confidence:** LLM cited at least one valid span ID AND at least one valid metric name.
* **Medium Confidence:** LLM cited spans OR metrics (but not both).
* **Low / Insufficient Evidence:** Neither spans nor metrics cited, or `insufficient_evidence == True`.

---

## 6. Active Incident State & Versioning (`github_output.py`)

RootCauser tracks active incidents in-memory to prevent duplicate GitHub issues during sustained outages.

```text
[Incoming Alert Webhook]
           |
           v
Compute SHA-256 Fingerprint (service, alert_name, labels)
           |
           +----------------------------------+
           |                                  |
           v                                  v
Fingerprint EXISTS in _ACTIVE_INCIDENTS?   Fingerprint NEW or RESOLVED?
           |                                  |
    [Status == OPEN]                           |
           |                                  |
           v                                  v
PATCH Existing GitHub Issue             POST New GitHub Issue
Increment Incident Version (v2, v3...)  Create Incident Version 1
```

### Fingerprint Calculation
```python
payload = {
    "service": service_name or "",
    "alert_name": alert_name or "",
    "labels": labels,
}
normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
fingerprint = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
```

### Lifecycle Rules:
1. **Initial Firing:** POSTs a new issue to GitHub with `Incident Version: 1`. Saves fingerprint to `_ACTIVE_INCIDENTS` map with `status: "OPEN"`.
2. **Repeated Firings (Same Fingerprint):** PATCHes the existing issue body with updated telemetry facts and increments `version` (v2, v3...).
3. **Explicit RESOLVED Webhook:** `resolve_incident()` updates fingerprint status to `"RESOLVED"`.
4. **Subsequent Firing:** A new alert for that fingerprint creates a fresh `Incident Version 1` issue.

---

## 7. Output Channels & Markdown Reports

### GitHub Issue Generation
`render_issue_markdown()` compiles deterministic facts from `build_report_facts()`:
* **Evidence Summary Table:** Summarizes traces, logs, metrics, and correlation scores.
* **Evidence Chain:** Step-by-step facts derived purely from telemetry records.
* **Confidence Breakdown:** Lists supporting signals and missing evidence.
* **Incident Timeline:** Chronological table of span timestamps, log events, and metric anomalies.
* **Evidence Coverage Table:** Displays available vs. used telemetry signals.
* **Raw Evidence Bundle:** Collapsible JSON block for full engineering auditability.

### Slack Notifications (`slack_output.py`)
If `SLACK_WEBHOOK_URL` and `issue_url` are configured, posts a summary payload:

```json
{
  "text": "*RootCauser incident:* `demo-service`\n*Alert:* High DB Query Latency\n*Confidence:* High\n*Summary:* ...\n*Issue:* <https://github.com/org/repo/issues/42|Open GitHub issue>"
}
```

---

## 8. Summary of Architectural Trade-Offs

| Architectural Decision | Trade-Off Rationale |
|---|---|
| **Deterministic Ranking before LLM** | **Benefit:** Zero hallucinated data ingestion, 100% testable, low token costs.<br>**Cost:** Requires manual heuristic tuning of scoring weights. |
| **SigNoz REST APIs over MCP** | **Benefit:** Direct access to stable v5 query builder aggregations.<br>**Cost:** Tied to SigNoz REST endpoint schemas. |
| **In-Memory Incident State** | **Benefit:** Simple local execution without external DB dependencies.<br>**Cost:** Container restarts reset active incident state map. |
| **Strict Citation Enforcement** | **Benefit:** Prevents bogus trace/metric IDs in published incident reports.<br>**Cost:** Rejects hypothesis if LLM fails to cite exact ID strings. |
