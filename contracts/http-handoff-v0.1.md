# VOGUE HTTP handoff v0.1 in Project_06

## Implemented contract

Project_06 exposes `POST /v1/agents/new-product-agent/runs`. The legacy `POST /api/planning-draft` remains available and keeps its existing request/response behavior. The new route is a thin adapter over the planning draft workflow.

Request top-level fields are exactly `contract_version`, `request_id`, and `input`. The contract version is `vogue-handoff/0.1`; `input` contains exactly `planning_request`, `trend_result`, `inventory_product_result`, and `sales_market_result`. The sales/market payload may be JSON `null` to represent no result, but the key must be present.

```json
{
  "contract_version": "vogue-handoff/0.1",
  "request_id": "synthetic-handoff-001",
  "input": {
    "planning_request": {"schema_version": "1.0", "request_id": "synthetic-handoff-001", "query": "합성 27SS 아우터 기획"},
    "trend_result": {"schema_version": "1.1", "request_id": "synthetic-handoff-001", "status": "partial", "trends": [], "evidence": [], "limitations": ["합성 자료"]},
    "inventory_product_result": {"schema_version": "1.0", "request_id": "synthetic-handoff-001", "agent_id": "stock-agent", "status": "no_results", "products": [], "evidence": [], "errors": []},
    "sales_market_result": {"schema_version": "1.0", "request_id": "synthetic-handoff-001", "agent_id": "sales-market-agent", "status": "no_results", "evidence": [], "limitations": [], "errors": []}
  }
}
```

Successful domain responses use HTTP 200, including `partial`, `no_results`, and `error` results. The response contains `contract_version`, `request_id`, `producer` (`new-product-agent`, schema `1.0`), `status`, and `result`. Envelope and result status are identical. `result` is the existing planning draft result, including draft, MD review state, input statuses, evidence, limitations, errors, and input payload trace.

## Version compatibility boundary

| Input producer payload | Supported source version | Internal handling |
| --- | --- | --- |
| PlanningRequest | 1.0 | Kept as supplied |
| Trend | 1.1 | A copied internal normalization view uses 1.0 for the existing domain context; source payload and source version 1.1 remain in `input_evidence.trend_result.payload` and compatibility trace |
| Stock | 1.0 | Kept as supplied |
| Project_07 | 1.0 | Opaque payload kept as supplied; producer ID must be `sales-market-agent` |

The normalizer is `project06-input-normalizer/1.0`. It does not rewrite the source Trend payload or its `schema_version`. Unsupported versions, missing producer metadata, request ID mismatches, unknown top-level envelope/input fields, or unsupported statuses return a compatibility/validation error. Producer-owned nested payloads are retained verbatim as JSON and are not projected into a new wire schema.

Project_06 only produces a review draft. `draft.review_status` remains `md_review_required`; the service does not automatically adopt products or decide price, cost, quantity, or purchase orders.

## HTTP errors

| HTTP | Error code | Condition |
| --- | --- | --- |
| 400 | `INVALID_JSON` / `INVALID_CONTENT_LENGTH` | Malformed JSON or missing/invalid content length |
| 401 | `UNAUTHORIZED` | Missing/invalid service bearer token, or non-loopback caller in local mode |
| 413 | `PAYLOAD_TOO_LARGE` | Request body exceeds 1 MB |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | Content-Type is not `application/json` |
| 422 | Specific validation code | Contract, request ID, producer ID/status, schema version, or envelope/input shape mismatch |
| 500 | `INTERNAL_ERROR` / `REQUEST_TIMEOUT` / `SERVICE_BUSY` | Internal exception, 60-second worker deadline, or all four execution slots occupied; response does not echo payload or exception text |

Unknown paths return 404. HTTP/domain errors use a small JSON object `{ "error": {"code": "...", "message": "..."} }`. Request bodies and exception details are not written to access logs.

## Local and service modes

The server must be started with an explicit `VOGUE_HTTP_MODE`:

- `local`: development mode; the process may bind only to `127.0.0.1`, `localhost`, or `::1`; the handoff accepts loopback callers without a token.
- `service`: TLS is enabled with `VOGUE_TLS_CERT_FILE` and `VOGUE_TLS_KEY_FILE`; `VOGUE_SERVICE_BEARER_TOKEN` is required for all HTTP API routes.

Example local run:

```bash
VOGUE_HTTP_MODE=local VOGUE_HOST=127.0.0.1 python -m vogue_npp.prototype.server
```

Service mode requires deployment-managed certificate and secret files. No credentials or service addresses are committed. v0.1 does not retry requests. The server enforces a 60-second worker deadline with at most four in-flight executions and returns HTTP 500 `REQUEST_TIMEOUT` if exceeded. Python cannot cancel an already running thread; timed-out work may finish in the background, so production needs process-level cancellation/isolation and load limits. A 3-second connection timeout is a caller-side connection setting and must be configured by Project_08/other clients. Project_06 performs no outbound HTTP call in this adapter. No automatic retry is made.

TLS termination may also be provided by an approved ingress, but then the service network must prevent direct plaintext access to the application and set the service mode behind a trusted TLS boundary. Bearer token rotation, issuer/audience, rate limits, persistence, idempotency, and deployment health checks remain operational work.

## Verification

`tests/test_http_handoff.py` uses synthetic inputs only and covers domain status passthrough, Trend 1.1 compatibility trace, malformed JSON, media type, request ID and schema failures, and unknown path behavior. It does not call Trend, Stock, Project_07, or external data sources.
