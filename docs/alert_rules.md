# RootCauser SigNoz Alert Rules

This file records the two MVP alert rules that should be recreated in SigNoz if the local stack is rebuilt.

## Notification Channel

- Type: Webhook
- URL: `http://copilot-agent:8001/webhook/alert`
- Optional header: `X-Rootcauser-Secret: <WEBHOOK_SHARED_SECRET>` if configured

## Alert 1: Slow Database Query

- Purpose: detect the `slow_query` seeded incident.
- Trigger command: `curl "http://localhost:8000/orders?inject_bug=slow_query"`
- Primary span: `db.orders.slow_query`
- Primary metric: `db.query.duration`
- Suggested condition: average `db.query.duration` greater than `1500 ms` over the last minute.
- Evaluation interval: 1 minute.
- Severity: warning.

Expected result: the alert transitions to firing after repeated slow-query requests and returns to normal after traffic stops.

## Alert 2: Downstream Payment Timeout

- Purpose: detect the `flaky_downstream` seeded incident.
- Trigger command: `curl "http://localhost:8000/orders?inject_bug=flaky_downstream"`
- Primary span: `downstream.payment_api.call`
- Primary metric: `downstream.errors`
- Suggested condition: `downstream.errors` greater than `0` over the last minute.
- Evaluation interval: 1 minute.
- Severity: critical.

Expected result: the alert transitions to firing after repeated downstream-timeout requests and returns to normal after traffic stops.

## Notes

SigNoz alert setup is partly UI/API dependent and may vary by installed SigNoz version. Confirm the exact stored metric names in the SigNoz metrics explorer before final demo rehearsal, then update thresholds here if needed.
