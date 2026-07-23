"""
RootCauser Bug Module — Slow Database Query
============================================
Simulates a slow database query by sleeping for a configurable duration.
Designed to be imported and called from an endpoint handler when the
"slow query" failure scenario is activated.

Telemetry produced:
    - A manual span ``db.orders.slow_query`` with ``simulated=true``.
    - A WARN-level log with the simulated query duration.
    - A histogram metric ``db.query.duration`` recording the latency in ms.
"""

import logging
import time

from opentelemetry import trace, metrics

logger = logging.getLogger(__name__)

# Obtain tracer and meter from the globally registered providers
# (set up by otel_config.init_telemetry at app startup).
tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)

# Histogram for DB call latency (milliseconds)
db_query_duration = meter.create_histogram(
    name="db.query.duration",
    description="Simulated database query latency",
    unit="ms",
)


def simulate_slow_query(delay_seconds: float = 2.0) -> list[dict]:
    """
    Pretend to run a slow SELECT against an orders table.

    Args:
        delay_seconds: How long the simulated query takes.

    Returns:
        A hard-coded list of "rows" (same shape as FAKE_ORDERS).
    """
    with tracer.start_as_current_span("db.orders.slow_query") as span:
        span.set_attribute("simulated", True)
        span.set_attribute("db.system", "postgresql")
        span.set_attribute("db.statement", "SELECT * FROM orders WHERE status = 'processing'")
        span.set_attribute("db.query.delay_seconds", delay_seconds)

        start = time.monotonic()
        time.sleep(delay_seconds)
        elapsed_ms = (time.monotonic() - start) * 1000

        # Record the latency in the histogram
        db_query_duration.record(elapsed_ms, {"db.operation": "SELECT", "simulated": True})

        logger.warning(
            "Slow query detected: db.orders.slow_query took %.0f ms (simulated)",
            elapsed_ms,
        )

    # Return fake "query results"
    return [
        {"order_id": "ord-1002", "customer_email": "bob@example.com", "status": "processing"},
    ]
