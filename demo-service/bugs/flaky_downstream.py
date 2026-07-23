"""
RootCauser Bug Module — Flaky Downstream API
=============================================
Simulates a downstream payment-service timeout.  The call always fails after
``timeout_seconds`` to mimic an unresponsive third-party API.

Telemetry produced:
    - A manual span ``downstream.payment_api.call`` marked as ERROR.
    - An ERROR-level log with the failure reason and timeout value.
    - A counter metric ``downstream.errors`` incremented on every failure.
"""

import logging
import time

from opentelemetry import trace, metrics
from opentelemetry.trace import StatusCode

logger = logging.getLogger(__name__)

# Obtain tracer and meter from the globally registered providers
# (set up by otel_config.init_telemetry at app startup).
tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)

# Counter for downstream call errors
downstream_errors = meter.create_counter(
    name="downstream.errors",
    description="Number of failed downstream API calls",
    unit="1",
)


class PaymentAPITimeoutError(Exception):
    """Raised when the simulated payment API does not respond in time."""


def call_payment_api(timeout_seconds: float = 1.5) -> dict:
    """
    Pretend to call an external payment service that always times out.

    Args:
        timeout_seconds: Simulated wait before the timeout is declared.

    Raises:
        PaymentAPITimeoutError: Always raised after ``timeout_seconds``.

    Returns:
        Never returns normally; always raises on timeout.
    """
    with tracer.start_as_current_span("downstream.payment_api.call") as span:
        span.set_attribute("simulated", True)
        span.set_attribute("peer.service", "payment-api")
        span.set_attribute("http.url", "https://payments.internal/v1/charge")
        span.set_attribute("http.method", "POST")
        span.set_attribute("timeout_seconds", timeout_seconds)

        try:
            # Simulate waiting for a response that never arrives
            time.sleep(timeout_seconds)
            raise PaymentAPITimeoutError(
                f"payment-api did not respond within {timeout_seconds}s (simulated)"
            )
        except PaymentAPITimeoutError as exc:
            # Mark the span as failed with a descriptive message
            span.set_status(StatusCode.ERROR, str(exc))
            span.record_exception(exc)

            # Increment the error counter
            downstream_errors.add(
                1,
                {
                    "peer.service": "payment-api",
                    "error.type": "TimeoutError",
                    "simulated": True,
                },
            )

            logger.error(
                "Downstream call failed: payment-api timed out after %.1fs (simulated)",
                timeout_seconds,
            )

            raise
