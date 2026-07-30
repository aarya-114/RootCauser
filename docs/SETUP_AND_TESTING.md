# Setup and Testing

This guide covers the setup and verification paths supported by the current RootCauser implementation.

## Prerequisites

- Docker Engine with Docker Compose v2.
- Python 3.11 or newer.
- Network access only when installing Python packages, pulling Docker images, calling the LLM API, or creating GitHub Issues.
- A local `.env` file for the full agent flow.

## Installation

Create the environment file:

```bash
cp .env.example .env
```

Install local test dependencies into an existing virtual environment:

```bash
venv/bin/python -m pip install -r copilot-agent/requirements.txt pytest ruff
```

What should happen:

- `copilot-agent` dependencies install.
- `pytest` and `ruff` become available in the local venv.
- No Docker containers are started by this command.

## Environment Variables

Required for the full autonomous flow:

- `LLM_API_KEY`: API key for the OpenAI-compatible chat completions call.
- `LLM_MODEL_NAME`: model name, for example `gpt-4o-mini`.
- `GITHUB_TOKEN`: GitHub personal access token for issue creation.
- `GITHUB_REPO`: target repo in `owner/repo` format.

Optional or locally defaulted:

- `OTEL_EXPORTER_OTLP_ENDPOINT`: defaults to the collector endpoint in Docker.
- `SIGNOZ_MCP_ENDPOINT`: documented MCP endpoint; current implementation uses REST fallback.
- `SIGNOZ_BASE_URL`: SigNoz API base URL.
- `SIGNOZ_API_KEY`: optional SigNoz API key if required.
- `SIGNOZ_PUBLIC_URL`: URL rendered into issue trace links.
- `SLACK_WEBHOOK_URL`: optional Slack Incoming Webhook.
- `WEBHOOK_SHARED_SECRET`: optional webhook shared secret.

What should happen:

- Missing LLM credentials do not crash import or health checks.
- Missing GitHub credentials cause the agent to write local Markdown artifacts but skip real GitHub issue creation.
- Missing Slack credentials make Slack notification a no-op.

## Docker Setup

Validate the Compose file:

```bash
docker compose config --quiet
```

What should happen:

- The command exits with status `0`.
- No output is printed.
- No containers are started.

Start the stack:

```bash
make up
```

What should happen:

- SigNoz, ClickHouse, the OTel collector, `demo-service`, and `copilot-agent` containers start.
- SigNoz UI/API is exposed on `http://localhost:8080`.
- Demo service is exposed on `http://localhost:8000`.
- Copilot agent is exposed on `http://localhost:8001`.

Stop the stack:

```bash
make down
```

What should happen:

- Containers are stopped and removed.
- Docker volumes are preserved.

## Build Commands

Build the demo service image:

```bash
docker build -t rootcauser-demo-service ./demo-service
```

What should happen:

- Docker builds the FastAPI demo-service image successfully.
- The image contains `app.py`, `otel_config.py`, and the two bug modules.

Build the copilot agent image:

```bash
docker build -t rootcauser-copilot-agent ./copilot-agent
```

What should happen:

- Docker builds the FastAPI copilot-agent image successfully.
- The image contains the webhook receiver, prompts, evidence bundler, reasoning code, and output modules.

## Run Commands

Run normal demo traffic:

```bash
curl http://localhost:8000/orders
```

What should happen:

- Response is HTTP `200`.
- JSON contains an `orders` array and `count`.
- No seeded bug is triggered.

Trigger slow query:

```bash
curl "http://localhost:8000/orders?inject_bug=slow_query"
```

What should happen:

- Response is HTTP `200`.
- Request takes about 2 seconds.
- A manual span named `db.orders.slow_query` is emitted.
- A warning log is emitted.
- Metric `db.query.duration` is recorded.

Trigger downstream timeout:

```bash
curl "http://localhost:8000/orders?inject_bug=flaky_downstream"
```

What should happen:

- Response is HTTP `500`.
- Request takes about 1.5 seconds.
- A manual span named `downstream.payment_api.call` is emitted and marked as error.
- An error log is emitted.
- Metric `downstream.errors` increments.

Send a sample alert webhook to the agent:

```bash
curl -X POST http://localhost:8001/webhook/alert \
  -H "Content-Type: application/json" \
  -d '{"alertname":"manual slow query test","labels":{"serviceName":"demo-service"},"startsAt":"2026-07-30T12:00:00Z"}'
```

What should happen:

- Response is HTTP `200`.
- JSON response is `{"status":"accepted"}`.
- Background processing starts in the agent.
- If SigNoz has no evidence for that exact time window, the agent should produce an insufficient-evidence result.

## Health Checks

Check demo-service health:

```bash
curl http://localhost:8000/health
```

Expected JSON:

```json
{"status":"ok","service":"demo-service"}
```

Check copilot-agent health:

```bash
curl http://localhost:8001/health
```

Expected JSON:

```json
{"status":"ok","service":"copilot-agent"}
```

Check container status:

```bash
make status
```

What should happen:

- Containers show `running` or `healthy` once startup completes.
- Early SigNoz startup can take time because ClickHouse and migrations must initialize.

## Verification Commands

Run unit tests:

```bash
venv/bin/python -m pytest tests/
```

What should happen:

- Tests run without live SigNoz, LLM, GitHub, or Slack dependencies.
- Current expected result: `8 passed`.

Run lint:

```bash
venv/bin/python -m ruff check .
```

What should happen:

- Ruff reports `All checks passed!`.

Run format check:

```bash
venv/bin/python -m ruff format --check .
```

What should happen:

- Ruff reports all files already formatted.

Run manual SigNoz retrieval smoke test:

```bash
venv/bin/python copilot-agent/manual_test_mcp.py
```

What should happen:

- The script prints recent traces, logs, and metric responses for `demo-service`.
- If no recent telemetry exists, lists may be empty.
- Alert lookup may print a skipped/failed message if alert id `1` does not exist.

Run manual reasoning smoke test:

```bash
venv/bin/python copilot-agent/manual_test_reasoning.py
```

What should happen:

- The script prints an evidence bundle JSON.
- It then prints a `RootCauseHypothesis` JSON.
- Without `LLM_API_KEY`, the hypothesis should be `Insufficient Evidence`.

## Validation Checklist

1. `cp .env.example .env`
   - A local `.env` file appears.
   - Git does not show `.env` as tracked or untracked because `.gitignore` excludes it.

2. `docker compose config --quiet`
   - Exits successfully with no output.
   - Confirms Compose YAML is structurally valid.

3. `make up`
   - Starts SigNoz, OTel collector, demo service, and copilot agent.
   - First startup may take several minutes while images pull and SigNoz initializes.

4. `curl http://localhost:8000/health`
   - Returns `{"status":"ok","service":"demo-service"}`.
   - Confirms the demo API is reachable.

5. `curl http://localhost:8001/health`
   - Returns `{"status":"ok","service":"copilot-agent"}`.
   - Confirms the alert receiver process is reachable.

6. `curl http://localhost:8000/orders`
   - Returns normal order JSON quickly.
   - Confirms baseline traffic works without seeded bugs.

7. `curl "http://localhost:8000/orders?inject_bug=slow_query"`
   - Returns order JSON after an intentional delay.
   - Confirms the slow-query bug path is active only when requested.

8. `curl "http://localhost:8000/orders?inject_bug=flaky_downstream"`
   - Returns HTTP `500`.
   - Confirms the downstream timeout bug path is active only when requested.

9. `venv/bin/python -m pytest tests/`
   - Returns all tests passing.
   - Confirms deterministic bundling and reasoning validation logic works without live services.

10. `venv/bin/python -m ruff check .`
    - Returns `All checks passed!`.
    - Confirms lint rules pass.

11. `venv/bin/python -m ruff format --check .`
    - Returns all files already formatted.
    - Confirms formatting is stable.

## Extreme Edge Cases

### Edge Case 1: Empty Evidence Window

Purpose:

Verify that the reasoning layer does not invent a root cause when there is no usable evidence.

Steps:

- Do not trigger any bug.
- Run the reasoning script against the recent default time window.
- Use this especially after `make down` / `make up` before generating traffic.

Exact command:

```bash
venv/bin/python copilot-agent/manual_test_reasoning.py
```

Expected logs:

- The script may print empty `spans`, `logs`, or `metrics`.
- No Python traceback should appear.

Expected JSON:

```json
{
  "summary": "No usable traces, logs, or metrics were retrieved.",
  "cited_ids": [],
  "suggested_fix": "Collect more evidence or widen the incident time window.",
  "insufficient_evidence": true,
  "confidence": "Insufficient Evidence"
}
```

Success criteria:

- Output hypothesis has `confidence` set to `Insufficient Evidence`.
- `cited_ids` is empty.

Failure symptoms:

- The script crashes.
- A specific root cause is produced despite empty evidence.
- The output cites trace, span, or metric IDs that are not present.

Recovery:

- Confirm the agent dependencies are installed.
- Confirm `copilot-agent/reasoning.py` still validates citations through `parse_and_validate_hypothesis`.
- Widen the time window in the manual script only if you intended to include recent telemetry.

### Edge Case 2: Missing LLM API Key

Purpose:

Verify that missing LLM credentials fail safely instead of crashing the agent.

Steps:

- Leave `LLM_API_KEY` blank for the command.
- Run a pure local Python snippet with an in-memory evidence bundle.

Exact command:

```bash
LLM_API_KEY= venv/bin/python - <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, str(Path("copilot-agent").resolve()))

from evidence_bundler import EvidenceBundle, MetricPoint, MetricSeries, SpanEvidence
from reasoning import analyze_incident

bundle = EvidenceBundle(
    spans=[
        SpanEvidence(
            trace_id="trace-slow-1",
            span_id="span-db-1",
            name="db.orders.slow_query",
            duration_ms=2200,
        )
    ],
    metrics=[
        MetricSeries(
            name="db.query.duration",
            points=[MetricPoint(timestamp=1, value=2200)],
            min_value=2200,
            max_value=2200,
            anomaly_point=MetricPoint(timestamp=1, value=2200),
        )
    ],
)

print(analyze_incident(bundle).model_dump_json(indent=2))
PY
```

Expected logs:

- No traceback should appear.
- The script should complete normally.

Expected JSON:

```json
{
  "summary": "LLM_API_KEY is not configured, so RootCauser cannot produce a grounded hypothesis.",
  "cited_ids": [],
  "suggested_fix": "Collect more evidence or widen the incident time window.",
  "insufficient_evidence": true,
  "confidence": "Insufficient Evidence"
}
```

Success criteria:

- The script exits successfully.
- The hypothesis is explicitly insufficient evidence.

Failure symptoms:

- Import-time settings failure.
- Unhandled authentication exception.
- A fabricated hypothesis despite no LLM call.

Recovery:

- Set `LLM_API_KEY` in `.env` for real reasoning.
- Keep the fallback path intact for local and CI-safe operation.

### Edge Case 3: Invalid LLM Citation

Purpose:

Verify that citation validation rejects an LLM response that cites an ID absent from the evidence bundle.

Steps:

- Run the unit test that exercises invalid citation handling.

Exact command:

```bash
venv/bin/python -m pytest tests/test_reasoning_parsing.py::test_rejects_unverified_citation
```

Expected logs:

- Pytest prints one passing test.
- No network calls are made.

Expected JSON:

The test asserts the parsed hypothesis behaves like:

```json
{
  "cited_ids": [],
  "insufficient_evidence": true,
  "confidence": "Insufficient Evidence"
}
```

Success criteria:

- Test passes.
- Invalid cited ID `span-not-real` is rejected.

Failure symptoms:

- Test fails.
- The invalid citation is accepted.
- Confidence is anything other than `Insufficient Evidence`.

Recovery:

- Inspect `parse_and_validate_hypothesis` in `copilot-agent/reasoning.py`.
- Ensure every cited ID is checked as a literal substring of the evidence bundle.

### Edge Case 4: Malformed LLM JSON

Purpose:

Verify that non-JSON LLM output does not crash parsing or produce an unsafe hypothesis.

Steps:

- Run the unit test for malformed LLM output.

Exact command:

```bash
venv/bin/python -m pytest tests/test_reasoning_parsing.py::test_rejects_malformed_json
```

Expected logs:

- Pytest prints one passing test.
- No network calls are made.

Expected JSON:

The test asserts an insufficient-evidence result equivalent to:

```json
{
  "cited_ids": [],
  "insufficient_evidence": true,
  "confidence": "Insufficient Evidence"
}
```

Success criteria:

- Test passes.
- Malformed text is rejected without an exception escaping.

Failure symptoms:

- JSON parsing exception escapes.
- The malformed text is treated as valid evidence.

Recovery:

- Restore `_strip_json_fence` and JSON parsing safeguards in `copilot-agent/reasoning.py`.
- Re-run the targeted test.

### Edge Case 5: GitHub Credentials Missing

Purpose:

Verify that issue rendering still produces a local artifact when GitHub is not configured.

Steps:

- Leave `GITHUB_TOKEN` blank or `GITHUB_REPO` as `your-org/your-repo`.
- Send a manual alert webhook.
- Inspect the agent artifact directory inside the running container.

Exact command:

```bash
curl -X POST http://localhost:8001/webhook/alert \
  -H "Content-Type: application/json" \
  -d '{"alertname":"manual missing github test","labels":{"serviceName":"demo-service"},"startsAt":"2026-07-30T12:00:00Z"}'

docker exec rootcauser-copilot-agent sh -c 'ls -1 /app/artifacts | tail'
```

Expected logs:

- Agent logs should show the webhook payload was received.
- Agent logs should show investigation completion.
- No GitHub API success log is expected because credentials are absent.

Expected JSON:

Webhook response:

```json
{"status":"accepted"}
```

Success criteria:

- The webhook returns immediately with HTTP `200`.
- A Markdown file is written under `/app/artifacts` in the running agent container.
- The agent does not crash.

Failure symptoms:

- Webhook returns `500`.
- No local artifact is written.
- A GitHub authentication error terminates the background task before local rendering.

Recovery:

- Confirm `copilot-agent/github_output.py` calls local artifact writing before the GitHub API request.
- Set `GITHUB_TOKEN` and `GITHUB_REPO` for real issue creation.

### Edge Case 6: Webhook Secret Mismatch

Purpose:

Verify that optional webhook shared-secret validation blocks unauthorized requests when enabled.

Steps:

- Set `WEBHOOK_SHARED_SECRET` for `copilot-agent`.
- Restart the stack.
- Send a webhook request without `X-Rootcauser-Secret`.

Exact command:

```bash
curl -i -X POST http://localhost:8001/webhook/alert \
  -H "Content-Type: application/json" \
  -d '{"alertname":"secret mismatch","labels":{"serviceName":"demo-service"}}'
```

Expected logs:

- No background investigation should start for the unauthorized request.

Expected JSON:

```json
{"detail":"invalid webhook secret"}
```

Success criteria:

- Response status is HTTP `401`.
- No issue artifact is created for the rejected request.

Failure symptoms:

- Response is HTTP `200` without the secret.
- Background investigation starts.

Recovery:

- Confirm `WEBHOOK_SHARED_SECRET` is present in the running container environment.
- Send the correct header:

```bash
curl -X POST http://localhost:8001/webhook/alert \
  -H "Content-Type: application/json" \
  -H "X-Rootcauser-Secret: <WEBHOOK_SHARED_SECRET>" \
  -d '{"alertname":"secret match","labels":{"serviceName":"demo-service"}}'
```

### Edge Case 7: SigNoz REST API Unavailable During Manual Retrieval

Purpose:

Verify that the MCP fallback client fails visibly when SigNoz is unreachable.

Steps:

- Stop the Docker stack.
- Run the manual MCP script.

Exact command:

```bash
make down
venv/bin/python copilot-agent/manual_test_mcp.py
```

Expected logs:

- The client should retry once after a short fixed delay.
- The final error should be a connection failure to SigNoz.

Expected JSON:

- No successful JSON response is expected because SigNoz is unavailable.

Success criteria:

- Failure is explicit.
- Retry behavior occurs once.

Failure symptoms:

- Script hangs indefinitely.
- Failure is swallowed and reported as successful data.

Recovery:

```bash
make up
curl http://localhost:8080/api/v1/health
venv/bin/python copilot-agent/manual_test_mcp.py
```

### Edge Case 8: Unknown Bug Injection Value

Purpose:

Verify that unsupported bug names do not accidentally trigger a seeded failure.

Steps:

- Call `/orders` with an unknown `inject_bug` value.

Exact command:

```bash
curl "http://localhost:8000/orders?inject_bug=unknown"
```

Expected logs:

- No slow-query warning log.
- No downstream timeout error log.

Expected JSON:

```json
{
  "orders": [
    {
      "order_id": "ord-1001",
      "customer_email": "alice@example.com",
      "status": "shipped",
      "items": [
        {
          "sku": "WIDGET-A",
          "name": "Widget Alpha",
          "quantity": 2,
          "price_cents": 1999
        }
      ],
      "total_cents": 3998,
      "created_at": "2026-07-20T09:15:00Z"
    },
    {
      "order_id": "ord-1002",
      "customer_email": "bob@example.com",
      "status": "processing",
      "items": [
        {
          "sku": "GADGET-B",
          "name": "Gadget Beta",
          "quantity": 1,
          "price_cents": 4999
        },
        {
          "sku": "CABLE-C",
          "name": "USB-C Cable",
          "quantity": 3,
          "price_cents": 799
        }
      ],
      "total_cents": 7396,
      "created_at": "2026-07-21T14:30:00Z"
    },
    {
      "order_id": "ord-1003",
      "customer_email": "carol@example.com",
      "status": "delivered",
      "items": [
        {
          "sku": "SENSOR-D",
          "name": "Temp Sensor",
          "quantity": 5,
          "price_cents": 1250
        }
      ],
      "total_cents": 6250,
      "created_at": "2026-07-19T08:00:00Z"
    }
  ],
  "count": 3
}
```

Success criteria:

- Response status is HTTP `200`.
- Response is fast.
- No seeded bug telemetry is emitted.

Failure symptoms:

- Request delays by about 2 seconds.
- Request returns HTTP `500`.
- Slow-query or downstream-error logs appear.

Recovery:

- Inspect the conditional bug dispatch in `demo-service/app.py`.
- Ensure only `slow_query` and `flaky_downstream` are handled.
