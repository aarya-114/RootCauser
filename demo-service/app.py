"""
RootCauser Demo Service — Order/Checkout API
=============================================
A minimal FastAPI app simulating an e-commerce order backend.
Used as the "target application" that the RootCauser copilot-agent monitors.

Endpoints:
    GET  /health    → liveness probe (200 OK)
    GET  /orders    → returns a fake list of recent orders
    POST /checkout  → accepts a cart payload, returns a fake confirmation

OpenTelemetry auto-instrumentation is enabled at startup via otel_config.py.
Bug injection:
    Pass ``?inject_bug=slow_query`` to GET /orders or POST /checkout to
    trigger a simulated slow database query.
    Pass ``?inject_bug=flaky_downstream`` to GET /orders or POST /checkout
    to trigger a simulated downstream payment-API timeout.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI, Query, status
from pydantic import BaseModel
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from otel_config import init_telemetry
from bugs import slow_query, flaky_downstream

# =============================================================================
# App setup
# =============================================================================
@asynccontextmanager
async def lifespan(application: FastAPI):
    """Initialise OpenTelemetry providers before the first request."""
    init_telemetry()
    yield


app = FastAPI(
    title="RootCauser Demo Service",
    description="Fake order/checkout API used as an observability target.",
    version="0.1.0",
    lifespan=lifespan,
)

# Enable auto-instrumentation — every request automatically produces a span.
FastAPIInstrumentor.instrument_app(app)


# =============================================================================
# Models
# =============================================================================
class CartItem(BaseModel):
    """A single item in a checkout cart."""
    sku: str
    name: str
    quantity: int = 1
    price_cents: int  # price in cents to avoid float rounding


class CheckoutRequest(BaseModel):
    """Payload accepted by POST /checkout."""
    customer_email: str
    items: list[CartItem]


class CheckoutResponse(BaseModel):
    """Confirmation returned after a successful checkout."""
    order_id: str
    status: str
    total_cents: int
    estimated_delivery: str


# =============================================================================
# Fake in-memory data — no real database needed for the demo
# =============================================================================
FAKE_ORDERS = [
    {
        "order_id": "ord-1001",
        "customer_email": "alice@example.com",
        "status": "shipped",
        "items": [
            {"sku": "WIDGET-A", "name": "Widget Alpha", "quantity": 2, "price_cents": 1999},
        ],
        "total_cents": 3998,
        "created_at": "2026-07-20T09:15:00Z",
    },
    {
        "order_id": "ord-1002",
        "customer_email": "bob@example.com",
        "status": "processing",
        "items": [
            {"sku": "GADGET-B", "name": "Gadget Beta", "quantity": 1, "price_cents": 4999},
            {"sku": "CABLE-C", "name": "USB-C Cable", "quantity": 3, "price_cents": 799},
        ],
        "total_cents": 7396,
        "created_at": "2026-07-21T14:30:00Z",
    },
    {
        "order_id": "ord-1003",
        "customer_email": "carol@example.com",
        "status": "delivered",
        "items": [
            {"sku": "SENSOR-D", "name": "Temp Sensor", "quantity": 5, "price_cents": 1250},
        ],
        "total_cents": 6250,
        "created_at": "2026-07-19T08:00:00Z",
    },
]


# =============================================================================
# Endpoints
# =============================================================================
@app.get("/health", status_code=status.HTTP_200_OK)
def health_check():
    """Liveness / readiness probe for Docker and load-balancers."""
    return {"status": "ok", "service": "demo-service"}


@app.get("/orders")
def list_orders(
    inject_bug: str | None = Query(default=None, description="Inject a named failure scenario."),
):
    """Return the fake list of recent orders."""
    if inject_bug == "slow_query":
        slow_query.simulate_slow_query()
    elif inject_bug == "flaky_downstream":
        flaky_downstream.call_payment_api()
    return {"orders": FAKE_ORDERS, "count": len(FAKE_ORDERS)}


@app.post("/checkout", response_model=CheckoutResponse, status_code=status.HTTP_201_CREATED)
def checkout(
    cart: CheckoutRequest,
    inject_bug: str | None = Query(default=None, description="Inject a named failure scenario."),
):
    """
    Accept a cart and return a fake order confirmation.

    In a real system this would validate inventory, charge payment, etc.
    Here we just compute a total and return a generated order ID.
    """
    if inject_bug == "slow_query":
        slow_query.simulate_slow_query()
    elif inject_bug == "flaky_downstream":
        flaky_downstream.call_payment_api()
    total_cents = sum(item.price_cents * item.quantity for item in cart.items)
    order_id = f"ord-{uuid4().hex[:8]}"

    return CheckoutResponse(
        order_id=order_id,
        status="confirmed",
        total_cents=total_cents,
        estimated_delivery="3-5 business days",
    )
