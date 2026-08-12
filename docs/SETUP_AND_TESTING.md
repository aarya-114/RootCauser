# Setup and Testing Guide

This guide details environment setup, local execution, bug injection procedures, manual webhook testing, and automated quality checks for RootCauser.

---

## Prerequisites

* Docker Engine 20.10+ and Docker Compose v2.
* Python 3.11+ (for local test execution and linting).
* `.env` credentials for `LLM_API_KEY`, `LLM_MODEL_NAME`, `GITHUB_TOKEN`, and `GITHUB_REPO`.

---

## 1. Environment Configuration

Copy `.env.example` to `.env` and fill in credentials:

```bash
cp .env.example .env
```

Example `.env` configuration:
```env
SIGNOZ_BASE_URL=http://localhost:8080
SIGNOZ_PUBLIC_URL=http://localhost:8080
LLM_API_KEY=your_openrouter_api_key
LLM_MODEL_NAME=gpt-4o-mini
GITHUB_TOKEN=your_github_token
GITHUB_REPO=your-org/your-repo
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
WEBHOOK_SHARED_SECRET=secret123
```

---

## 2. Start Services

Bring up SigNoz, OpenTelemetry Collector, Demo Service, and Copilot Agent:

```powershell
docker compose up -d --build
```

Verify service health endpoints:

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8001/health
```

Expected health response:
```json
{"status": "ok", "service": "demo-service"}
{"status": "ok", "service": "copilot-agent"}
```

---

## 3. Generate Telemetry (Bug Injection)

### Scenario 1: Slow Database Query
```powershell
Invoke-RestMethod "http://localhost:8000/orders?inject_bug=slow_query"
```
Emits a `db.orders.slow_query` span (2s sleep), a WARN log, and latency datapoints in `db.query.duration`.

### Scenario 2: Downstream Payment Timeout
```powershell
Invoke-RestMethod "http://localhost:8000/orders?inject_bug=flaky_downstream"
```
Emits an ERROR span `downstream.payment_api.call`, an ERROR log, and increments the `downstream.errors` metric.

---

## 4. Manual Webhook Testing

Test the agent webhook receiver using PowerShell or curl:

```powershell
$now = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
$body = @{
    alertname = "High DB Query Latency"
    labels = @{ serviceName = "demo-service" }
    startsAt = $now
} | ConvertTo-Json -Compress

Invoke-RestMethod -Uri "http://localhost:8001/webhook/alert" -Method POST -ContentType "application/json" -Body $body
```

Inspect agent logs:
```powershell
docker compose logs copilot-agent --tail 100
```

---

## 5. Automated Quality Checks

Run local unit tests and lint checks inside your virtual environment:

```powershell
# Execute pytest suite (43 offline tests)
venv\Scripts\python.exe -m pytest -v

# Execute Ruff linting
venv\Scripts\python.exe -m ruff check copilot-agent tests
```

---

## 6. Real SigNoz Webhook Integration Test

1. Configure a Webhook Notification Channel in SigNoz (`http://localhost:8080`):
   * URL: `http://copilot-agent:8001/webhook/alert`
   * Header: `X-Rootcauser-Secret: secret123` (if configured).
2. Trigger telemetry generation repeatedly during the alert evaluation window.
3. Confirm the alert transitions to FIRING in SigNoz.
4. Verify that `copilot-agent` logs report `Investigation: service=demo-service ...` and outputs a valid GitHub issue URL.
5. Send repeated firings to verify that `github_output.py` updates the existing GitHub issue with incremented `Incident Version` badges.
6. Verify that an explicit `RESOLVED` alert payload marks the incident fingerprint resolved.
