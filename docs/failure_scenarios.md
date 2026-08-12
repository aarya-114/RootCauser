# Failure Scenarios & Scope Boundaries

RootCauser currently implements two seeded failure scenarios inside `demo-service`. Additional failure modes are documented roadmap items.

---

## 1. Implemented Failure Scenarios

### Scenario 1: Slow Database Query (`slow_query`)
* **Trigger Endpoint:** `GET /orders?inject_bug=slow_query`
* **Telemetry Produced:**
  * Trace span `db.orders.slow_query` (duration ~2000ms).
  * WARN log `"Slow query detected: db.orders.slow_query took 2000 ms"`.
  * Metric histogram `db.query.duration`.
* **Triage Outcome:** RootCauser identifies database latency in `slow_query.py`, cites span and metric IDs, and creates/updates a GitHub issue.

### Scenario 2: Downstream Payment API Timeout (`flaky_downstream`)
* **Trigger Endpoint:** `GET /orders?inject_bug=flaky_downstream`
* **Telemetry Produced:**
  * ERROR trace span `downstream.payment_api.call` (status: `StatusCode.ERROR`).
  * ERROR log `"Downstream call failed: payment-api timed out"`.
  * Metric counter `downstream.errors`.
* **Triage Outcome:** RootCauser identifies downstream timeout, applies remediation grounding (suggesting latency investigation before timeout increases), and creates/updates a GitHub issue.

---

## 2. Future Roadmap Scenarios (Unimplemented)

The following failure modes are planned future extensions:
1. HTTP 5xx rate spikes across multiple microservices.
2. Memory pressure and container OOMKilled restart loops.
3. Message queue processing backlog delays.
4. Database connection pool exhaustion.
5. Regional network latency degradation.
