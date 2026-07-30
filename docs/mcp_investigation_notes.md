# MCP Investigation Notes

## Date
2026-07-24

## Objective

Determine whether the local self-hosted SigNoz instance exposes a usable MCP (Model Context Protocol) server.

## Investigation

### Tested endpoint

```bash
curl http://localhost:8080/mcp
```

**Result**

- HTTP Status: `200 OK`
- Content-Type: `text/html`
- Response body: SigNoz frontend HTML (`index.html`)

This indicates that `/mcp` is routed to the frontend application rather than exposing an MCP protocol endpoint.

### REST API verification

```bash
curl http://localhost:8080/api/v1/version
```

Response:

```json
{
  "version": "v0.134.0",
  "ee": "Y",
  "setupCompleted": true
}
```

The REST API is available and functioning correctly.

## Conclusion

No usable MCP endpoint or documented MCP tool schema was found in the local SigNoz deployment.

Following ADR-04, RootCauser will use SigNoz's HTTP REST API for evidence retrieval while preserving an MCP-compatible interface inside `mcp_client.py` for future replacement.