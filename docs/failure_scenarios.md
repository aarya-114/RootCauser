# Failure Scenarios

RootCauser's locked MVP implements exactly 2 seeded incidents. The remaining scenarios are documented roadmap items, not incomplete MVP work.

## Implemented

1. Slow database query  
   Trigger: `GET /orders?inject_bug=slow_query`  
   Signals: `db.orders.slow_query` span, warning log, `db.query.duration` metric.
   Incident behavior: repeated firings before `RESOLVED` update the same GitHub issue and increment Incident Version.

2. Downstream payment API timeout  
   Trigger: `GET /orders?inject_bug=flaky_downstream`  
   Signals: `downstream.payment_api.call` error span, error log, `downstream.errors` metric.
   Incident behavior: after a reliable `RESOLVED`, the next firing starts a new Version 1 incident issue.

## Roadmap Only

3. Elevated HTTP 5xx rate across one route.
4. Memory pressure or container restart loop.
5. Queue backlog causing delayed processing.
6. External dependency returning 429 rate limits.
7. Bad deploy causing a new exception class.
8. Database connection pool exhaustion.
9. Regional latency spike.
10. Missing telemetry or broken instrumentation.

These are intentionally excluded from the MVP to keep the demo focused and reliable.
