# SigNoz Alert Rules Reference

This reference details the two SigNoz alert rules used to trigger RootCauser triage investigations during demonstrations and testing.

---

## Webhook Channel Configuration

* **Channel Type:** Webhook
* **Webhook Endpoint:** `http://copilot-agent:8001/webhook/alert`
* **Custom Headers (Optional):** `X-Rootcauser-Secret: <WEBHOOK_SHARED_SECRET>`

---

## Alert Rule 1: Slow Database Query

* **Scenario:** Slow Database Query (`slow_query`)
* **Trigger Endpoint:** `GET /orders?inject_bug=slow_query`
* **Primary Span:** `db.orders.slow_query`
* **Primary Metric:** `db.query.duration`
* **Condition:** Average `db.query.duration` > `1500 ms` over 1 minute.
* **Evaluation Interval:** 1 minute.
* **Severity:** warning.
* **Expected Result:** SigNoz fires alert → `copilot-agent` queries telemetry → Creates or updates GitHub issue identifying database query latency in `slow_query.py`.

---

## Alert Rule 2: Downstream Payment Timeout

* **Scenario:** Downstream Payment API Timeout (`flaky_downstream`)
* **Trigger Endpoint:** `GET /orders?inject_bug=flaky_downstream`
* **Primary Span:** `downstream.payment_api.call`
* **Primary Metric:** `downstream.errors`
* **Condition:** `downstream.errors` > `0` over 1 minute.
* **Evaluation Interval:** 1 minute.
* **Severity:** critical.
* **Expected Result:** SigNoz fires alert → `copilot-agent` queries telemetry → Creates or updates GitHub issue identifying downstream payment API timeout in `flaky_downstream.py`.
