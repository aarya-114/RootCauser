# SigNoz API Investigation Notes

These notes describe the SigNoz behavior used by RootCauser's current REST client.

## Endpoints in use

- `POST /api/v5/query_range` retrieves raw traces, raw logs, and metric time series.
- `GET /api/v2/rules/{uuid}` retrieves alert-rule details. Rule identifiers are UUIDs, not numeric v1 IDs.

`mcp_client.py` keeps the project-facing query interface but uses REST because the investigated local SigNoz deployment did not expose a usable MCP protocol endpoint.

## Response handling

SigNoz records can place the useful telemetry fields under `data`; the client normalizes that shape while preserving trace IDs, span IDs, timestamps, bodies, and metric points. Metric time-series are normalized from the v5 builder response shape that carries aggregations, series, and point values. Unsupported response shapes are logged rather than silently converted into fabricated evidence.

## Log query limitation

Some ClickHouse-backed SigNoz installations reject `JSON_EXISTS` and `JSON_VALUE` expressions with `Functions JSON* are not supported`. RootCauser therefore requests native raw-log columns without selecting or filtering `severityText`, which can trigger those expressions. Severity is retained when SigNoz returns it. If the log request still fails, `query_logs()` logs the failure and returns `[]`; traces and metrics continue through the investigation.
