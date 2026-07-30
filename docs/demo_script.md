# RootCauser Demo Script

Target length: 5-7 minutes.

## 0:00-0:45 — Show the System

Open:

- SigNoz: `http://localhost:8080`
- Demo API: `http://localhost:8000/health`
- Copilot agent health: `http://localhost:8001/health`

Say: RootCauser turns SigNoz alerts into evidence-cited GitHub Issues.

## 0:45-1:30 — Baseline Traffic

```bash
curl http://localhost:8000/orders
```

Show that the service responds normally and produces regular traces.

## 1:30-3:15 — Slow Query Incident

```bash
curl "http://localhost:8000/orders?inject_bug=slow_query"
```

Point out:

- Manual span: `db.orders.slow_query`
- Warning log for the slow query
- Metric: `db.query.duration`
- SigNoz alert transitions to firing after the configured evaluation interval

Expected agent result: a GitHub Issue with a hypothesis about slow order lookup/database query latency.

## 3:15-5:00 — Downstream Timeout Incident

```bash
curl "http://localhost:8000/orders?inject_bug=flaky_downstream"
```

Point out:

- Manual span: `downstream.payment_api.call`
- Error status and recorded exception
- Error log for payment API timeout
- Metric: `downstream.errors`

Expected agent result: a separate GitHub Issue with a downstream timeout hypothesis.

## 5:00-6:30 — Evidence Guardrail

Open the created issue and highlight:

- Confidence label
- Literal cited IDs
- Evidence bundle
- Suggested fix

Say: If the LLM cites an ID that is not present in the bundle, RootCauser rejects the answer as `Insufficient Evidence`.

## Pre-Demo Checklist

```bash
cp .env.example .env
# Fill LLM_API_KEY, GITHUB_TOKEN, GITHUB_REPO
make down
make up
curl http://localhost:8000/health
curl http://localhost:8001/health
```

Confirm SigNoz alert rules point to:

```text
http://copilot-agent:8001/webhook/alert
```
