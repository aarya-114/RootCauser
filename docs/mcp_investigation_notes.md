# SigNoz API & Protocol Notes

This document records technical details regarding SigNoz API endpoints and integration design decisions.

---

## REST Endpoint Specifications

RootCauser interacts directly with SigNoz REST endpoints:
* **Query Range API (`POST /api/v5/query_range`):** Used for retrieving raw trace spans, raw log records, and metric time series aggregations.
* **Rules API (`GET /api/v2/rules/{uuid}`):** Used for resolving alert rule definitions. Rule identifiers are UUIDs.

---

## Historical MCP Protocol Naming Context

The module retains the filename [`copilot-agent/mcp_client.py`](file:///c:/Users/Om/Desktop/RootCauser/copilot-agent/mcp_client.py) from earlier protocol research. However, because local SigNoz Docker deployments expose stable v5/v2 HTTP REST endpoints rather than a live Model Context Protocol (MCP) server, the client executes direct REST calls via Python `requests`.

---

## SigNoz Response Parsing & Fallback Behavior

### 1. Nested Record Unwrapping
SigNoz query responses wrap telemetry fields under a inner `data` dictionary. `_unwrap_data()` normalizes this shape while preserving `traceID`, `spanID`, `timestamp`, and duration fields.

### 2. Log Query SQL Compatibility Fallback
Certain ClickHouse-backed SigNoz installations reject queries selecting or filtering `severityText` with `Functions JSON* are not supported`. `mcp_client.py` strips `selectFields` for log queries. If log querying still fails due to database errors, `query_logs()` logs a warning and returns an empty list `[]`. Telemetry triage proceeds using available trace and metric data.
