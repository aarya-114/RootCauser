# Setup and Testing

## Prerequisites

- Docker Compose v2 and Python 3.11+
- `.env` values for `LLM_API_KEY`, `LLM_MODEL_NAME`, `GITHUB_TOKEN`, `GITHUB_REPO`, and optionally `SLACK_WEBHOOK_URL`
- SigNoz API access through `SIGNOZ_BASE_URL` and `SIGNOZ_API_KEY` when required

## Start the stack

```powershell
docker compose up -d --build
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8001/health
```

The demo service runs on port 8000, the agent on 8001, and SigNoz on 8080.

## Generate telemetry

```powershell
Invoke-RestMethod "http://localhost:8000/orders?inject_bug=slow_query"
```

This emits a slow-query span, warning log, and query-duration metric. Confirm the service telemetry in SigNoz at `http://localhost:8080` before testing an alert.

## Manual webhook smoke test

This verifies that the FastAPI receiver accepts an alert-shaped payload. It does not prove that a SigNoz alert rule fired or that an incident issue was published.

```powershell
$now = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$body = @{ alertname = "manual slow query test"; labels = @{ serviceName = "demo-service" }; startsAt = $now } | ConvertTo-Json -Compress
Invoke-RestMethod -Uri "http://localhost:8001/webhook/alert" -Method POST -ContentType "application/json" -Body $body
docker compose logs copilot-agent --tail 100
```

Expected response: `{"status":"accepted"}`. If matching telemetry is absent, an insufficient-evidence result is expected.

## Real SigNoz alert end-to-end test

1. Start the stack and generate the slow-query workload repeatedly during the alert evaluation window.
2. In SigNoz, confirm traces, logs when available, and the configured metric telemetry are present. Agent logs should report non-zero `metric_series` and `metric_points` when the incident window contains metric data.
3. Confirm the configured SigNoz rule transitions to firing and sends its webhook.
4. Inspect `docker compose logs copilot-agent --tail 200` for the received payload, service, alert UUID, evidence counts, relevance scores, LLM status, and GitHub URL.
5. Confirm selected evidence is incident-relevant rather than dominated by routine health spans.
6. Confirm OpenRouter returns a citation-valid result, or an explicit insufficient-evidence result when evidence cannot support a cause.
7. Confirm the configured GitHub repository contains the incident issue and Slack receives the issue summary/link.

The live result depends on valid external credentials and a correctly configured SigNoz alert channel. A log-query failure is non-fatal; traces and metrics remain available to the investigation.

## Automated checks

```powershell
venv\Scripts\python.exe -m pytest -q
venv\Scripts\python.exe -m ruff check copilot-agent tests
```

The unit suite does not require live SigNoz, OpenRouter, GitHub, or Slack.

For a real alert with a stable rule ID, send repeated FIRING notifications before RESOLVED to verify that the same GitHub issue is updated with increasing Incident Version values. After a reliable RESOLVED notification, the next firing creates a new Version 1 issue. This lightweight state resets when the copilot-agent restarts.
