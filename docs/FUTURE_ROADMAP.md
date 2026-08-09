# Future Roadmap

This roadmap separates the implemented MVP from future work. It reflects the current repository state and does not assume functionality that has not been built.

## Current MVP

Implemented features:

- FastAPI demo service with `/health`, `/orders`, and `/checkout`.
- OpenTelemetry traces, logs, and metrics routed through an OTel Collector to SigNoz.
- Two explicit seeded incidents:
  - `slow_query`
  - `flaky_downstream`
- SigNoz alert-rule documentation for both seeded incidents.
- SigNoz MCP investigation notes and a REST fallback client in `copilot-agent/mcp_client.py`.
- Evidence bundling in `copilot-agent/evidence_bundler.py`.
- LLM reasoning path in `copilot-agent/reasoning.py`.
- Hard citation validation before accepting LLM output.
- Webhook receiver in `copilot-agent/main.py`.
- GitHub Issue rendering and creation support.
- Optional Slack notification support.
- Unit tests for evidence bundling and reasoning validation.
- Ruff and pytest CI workflow.
- Setup, testing, architecture, demo, and failure-scenario documentation.

Current MVP limitation:

- The full live loop still depends on local SigNoz configuration, real telemetry, an LLM API key, and GitHub credentials.
- Alert rules are documented but not automatically provisioned by repository code.
- SigNoz querying uses the REST fallback because no usable local MCP endpoint was found.

## Technical Debt

### Monitor SigNoz REST Query Shape Changes

- Current implementation: `mcp_client.py` normalizes nested raw records and metric series from `POST /api/v5/query_range` and logs unsupported response shapes.
- Remaining limitation: future SigNoz versions may introduce new response variants that need explicit normalization coverage.
- Priority: Medium.

### Replace Import Path Workarounds

- Why it is needed: The `copilot-agent` directory name contains a hyphen, so tests add it to `sys.path`.
- Current limitation: This works locally but is less clean than a package-friendly module path.
- Estimated complexity: Low.
- Priority: Medium.

### Persist Agent Artifacts More Deliberately

- Why it is needed: Local Markdown artifacts are useful for demos and GitHub failure fallback.
- Current limitation: Artifacts are written inside the running agent container and are not mounted to the host by default.
- Estimated complexity: Low.
- Priority: Medium.

### Improve Error Handling Around Background Tasks

- Why it is needed: Webhook responses return immediately while investigation continues in the background.
- Current limitation: Failures are logged, but there is no durable job status or retry queue.
- Estimated complexity: Medium.
- Priority: Medium.

### Align Alert Documentation With Live SigNoz Rules

- Why it is needed: Demo reliability depends on thresholds matching real observed metric names and values.
- Current limitation: Alert rules are documented manually and must be recreated in the SigNoz UI/API.
- Estimated complexity: Medium.
- Priority: High.

## Immediate Improvements

### Add Alert Provisioning Script

- Why it is needed: Manual alert setup is easy to misconfigure during demo prep.
- Current limitation: `docs/alert_rules.md` documents rules, but code does not create them.
- Estimated complexity: Medium.
- Priority: High.

### Add Host-Mounted Agent Artifacts

- Why it is needed: Local issue Markdown should be visible outside the container.
- Current limitation: `copilot-agent/artifacts` is created inside the container unless a volume is added.
- Estimated complexity: Low.
- Priority: High.

### Improve Webhook Payload Parsing

- Why it is needed: SigNoz webhook payloads can differ across alert types and versions.
- Current limitation: `main.py` extracts service name, alert ID, and metric name with conservative heuristics.
- Estimated complexity: Medium.
- Priority: High.

### Add Manual End-to-End Smoke Script

- Why it is needed: The project needs one repeatable command for demo rehearsal.
- Current limitation: Manual scripts test MCP retrieval and reasoning separately.
- Estimated complexity: Medium.
- Priority: Medium.

### Add Sample `.env` Validation Command

- Why it is needed: Missing credentials are common setup failures.
- Current limitation: Settings load defaults where possible, but there is no explicit preflight command.
- Estimated complexity: Low.
- Priority: Medium.

## Short-term Roadmap

### Support GitHub Issue Deduplication

- Why it is needed: Repeated alerts for the same incident can create duplicate issues.
- Current limitation: Every successful GitHub output call creates a new issue.
- Estimated complexity: Medium.
- Priority: High.

### Add Issue Update Mode

- Why it is needed: Ongoing incidents should update an existing issue with new evidence.
- Current limitation: The GitHub integration only creates issues.
- Estimated complexity: Medium.
- Priority: Medium.

### Add More Unit Coverage for `mcp_client.py`

- Why it is needed: Query-building errors can silently produce empty evidence.
- Current limitation: Current tests cover deterministic bundling and reasoning parsing, not REST payload generation.
- Estimated complexity: Low.
- Priority: High.

### Add Agent Integration Tests With Mocked SigNoz

- Why it is needed: The webhook pipeline should be testable without live SigNoz.
- Current limitation: There are no tests for `POST /webhook/alert` background orchestration.
- Estimated complexity: Medium.
- Priority: High.

### Improve Confidence Scoring

- Why it is needed: Current confidence is intentionally simple for the MVP.
- Current limitation: Confidence only distinguishes span and metric citation coverage.
- Estimated complexity: Medium.
- Priority: Medium.

## Medium-term Roadmap

### Add Real MCP Support When Available

- Why it is needed: The project goal includes MCP-first observability access.
- Current limitation: Local SigNoz did not expose a usable MCP endpoint during investigation.
- Estimated complexity: High.
- Priority: Medium.

### Add Incident Deduplication State

- Why it is needed: Deduplication across restarts requires durable state.
- Current limitation: ADR-05 intentionally excludes a database from the MVP.
- Estimated complexity: High.
- Priority: Medium.

### Add Ownership Routing

- Why it is needed: Issues and Slack messages should go to the right service owners.
- Current limitation: All incidents use one configured `GITHUB_REPO` and optional Slack webhook.
- Estimated complexity: Medium.
- Priority: Medium.

### Add More Failure Scenarios

- Why it is needed: Real systems fail in more ways than latency and downstream timeouts.
- Current limitation: The MVP is intentionally locked to exactly two seeded failures.
- Estimated complexity: Medium.
- Priority: Low.

### Add Better Trace Deep Links

- Why it is needed: GitHub Issues are more useful when links open the exact trace view.
- Current limitation: `github_output.py` renders a basic trace URL from the top trace ID.
- Estimated complexity: Medium.
- Priority: Medium.

## Long-term Roadmap

### Production Authentication and Authorization

- Why it is needed: Real alert receivers need strong authentication, authorization, and auditability.
- Current limitation: The MVP supports only an optional shared-secret header.
- Estimated complexity: High.
- Priority: High for production, low for local demo.

### Human Approval Workflow

- Why it is needed: Production systems may require approval before creating or updating external tickets.
- Current limitation: The agent creates GitHub Issues automatically when credentials are configured.
- Estimated complexity: High.
- Priority: Medium.

### Multi-Service Incident Analysis

- Why it is needed: Real incidents often cross service boundaries.
- Current limitation: Evidence retrieval assumes one affected service name and a bounded time window.
- Estimated complexity: High.
- Priority: Medium.

### Persistent Investigation History

- Why it is needed: Teams need audit trails, comparisons across incidents, and incident lifecycle tracking.
- Current limitation: The MVP has no database and keeps only local Markdown fallback artifacts.
- Estimated complexity: High.
- Priority: Medium.

### Rich Remediation Automation

- Why it is needed: Mature copilots can propose or open code/config changes after root-cause analysis.
- Current limitation: RootCauser only writes a suggested fix into an issue or Slack message.
- Estimated complexity: Very high.
- Priority: Low until analysis reliability is proven.
