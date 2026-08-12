# RootCauser Live Demonstration Script

Target Duration: 5-7 Minutes.

---

## 0:00-1:00 — Stack Verification & Overview

Open in browser:
* **SigNoz UI:** `http://localhost:8080`
* **Demo API Health:** `http://localhost:8000/health`
* **Copilot Agent Health:** `http://localhost:8001/health`

**Talking Point:**
> "RootCauser is an automated incident triage engine. It intercepts SigNoz alert webhooks, deterministically collects and ranks telemetry, runs citation-checked LLM root-cause synthesis, and manages versioned incident reports in GitHub and Slack."

---

## 1:00-2:30 — Scenario 1: Slow Database Query

Execute bug injection:
```powershell
Invoke-RestMethod "http://localhost:8000/orders?inject_bug=slow_query"
```

Point out in SigNoz & Agent logs:
* Span `db.orders.slow_query` (duration ~2000ms).
* WARN log message `"Slow query detected"`.
* Metric histogram `db.query.duration`.
* Agent logs: `Evidence bundle created: spans=... logs=... metrics=...`.

**Expected Result:** A GitHub issue created with `Incident Version: 1`, high confidence, citing span ID and metric `db.query.duration`.

---

## 2:30-4:00 — Scenario 2: Downstream Payment API Timeout

Execute bug injection:
```powershell
Invoke-RestMethod "http://localhost:8000/orders?inject_bug=flaky_downstream"
```

Point out:
* ERROR span `downstream.payment_api.call`.
* ERROR log message `"Downstream call failed: payment-api timed out"`.
* Metric counter `downstream.errors`.

**Expected Result:** A separate GitHub issue created detailing external dependency timeout in `flaky_downstream.py`.

---

## 4:00-5:30 — Citation Guardrails & Incident Versioning

1. Open the created GitHub Issue.
2. Show the **Evidence Summary Table**, **Evidence Chain**, **Confidence Breakdown**, and **Cited Telemetry IDs**.
3. Highlight that any hallucinated trace ID causes immediate rejection (`CITATION_VALIDATION_FAILED`).
4. Re-fire the alert and show that `github_output.py` updates the same issue body, incrementing `Incident Version: 2`.

---

## Pre-Demo Checklist

```powershell
# Verify environment and start stack
cp .env.example .env
docker compose up -d --build
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8001/health
```
