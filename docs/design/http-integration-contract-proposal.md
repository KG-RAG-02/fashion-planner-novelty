# Project_06 HTTP integration contract proposal

> **Historical proposal:** this document predates the current P06 HTTP adapter. Use [HTTP handoff v0.3](../../contracts/http-handoff-v0.3.md) and [repository boundaries](../repository-boundaries.md) for the active planning input contract and service ports.

**Status: historical proposal, superseded for the Project_06 handoff boundary.** The current planning input adapter is documented in [`http-handoff-v0.3.md`](../../contracts/http-handoff-v0.3.md). Production addresses, credentials, deployment, and caller-side timeout configuration remain environment-specific and are not committed.

## Current Project_06 behavior (observed locally)

`POST /api/planning-draft` is a Project_06 internal compatibility adapter, not a shared or production HTTP contract.

- Required body slots are `planning_request`, `trend_result`, and `inventory_product_result`, each a JSON object. `sales_market_result` is optional and treated as a Project_07 handoff.
- The request ID is taken from `planning_request.request_id` (or a legacy top-level fallback). Trend and stock `request_id` values must match it.
- The planning request schema version is taken from its payload (or a top-level fallback/default). Trend and stock schema versions, when present, must equal that version. Missing producer versions fall back to the planning request version and are marked as adapter fallbacks.
- Therefore a synthetic PlanningRequest `1.0`, Trend `1.1`, Stock `1.0` request is currently rejected before draft generation. A supplied Trend `1.1` is not rewritten to `1.0`.
- Allowed upstream statuses are `ok`, `partial`, `no_results`, and `error`. An upstream `error` or `no_results` with valid IDs and versions is accepted; the draft path returns a limited draft and preserves the input status. An invalid request ID or schema version raises a validation error; the current HTTP handler returns HTTP 400 with an unversioned `{ "error": ... }` body.
- The response contains top-level `request_id`, `status`, `input_statuses`, `draft`, `input_evidence`, Evidence IDs, limitations, conflicts, questions, validation issues, and optional planning/image fields. `input_evidence.<slot>.payload` preserves the parsed input JSON mapping. This is semantic JSON preservation, not byte-for-byte preservation of the original HTTP body.
- The normalized input metadata records producer ID and source schema/status origins. `internal_schema_version` currently reflects the normalized internal metadata value, which is often the producer value or a fallback; it is not a separately versioned adapter transformation identifier.
- Compatibility is checked at more than one layer: after the HTTP adapter's equality check, `build_planning_context` also requires the normalized `AgentResult.schema_version` values to match. A future producer-specific compatibility adapter therefore needs an explicitly approved internal normalization target (and traceable source/adapter versions), or a reviewed change to that domain invariant; removing only the HTTP-layer check would still fail downstream.
- Top-level response status is currently `partial` if context limitations/conflicts exist or `sales_market_result` is not `ok`; otherwise it is `ok`. In particular, omitting optional Project_07 input currently produces `sales_market_result=not_provided` and a top-level `partial` result, even when request, trend, and stock are `ok`.
- Project_06 does not own the browser review UI. Project_08 owns the UI; Project_06 can return the structured review data and statuses.

The behavior above was exercised with synthetic in-memory payloads on 2026-11-10. The fixture cases are in [`examples/fixtures/http-integration-proposal/cases.json`](../../examples/fixtures/http-integration-proposal/cases.json).

## Candidate common envelope (not a final wire schema)

Candidate endpoint comparison:

| Candidate | What it represents | Discussion point |
| --- | --- | --- |
| `POST /api/planning-draft` | Existing single-purpose Project_06 adapter | Small migration step; path and body are Project_06-specific and do not provide a common envelope/version boundary. Keep only as a compatibility adapter if a shared path is adopted. |
| `POST /v1/agents/{agent_id}/runs` | API Design candidate for a common agent run boundary | Consistent stage invocation shape and HTTP API version; service ownership/base URL, input nesting, output schema, authentication, and lifecycle remain unapproved. |

**Candidate recommendation for discussion:** use the shared agent-run shape for cross-agent invocation, with `agent_id=new-product-agent`, and have it call the existing Project_06 planning use case through an adapter. Keep `/api/planning-draft` as a local/legacy adapter during migration if owners want it. This is a recommendation only; the path and envelope require approval.

The candidate body fields below describe semantics, not a ratified schema:

- Common envelope version identifies the shared transport envelope. It is distinct from each producer payload's `schema_version`.
- One top-level `request_id` identifies the run. Every producer result must carry the same request ID; the orchestrator validates this and never substitutes a different value.
- Each named input slot carries the unchanged producer result, including producer ID, producer `schema_version`, status, Evidence, limitations, errors, and missing-data notes. The slot name identifies the role of the input; it does not change ownership of the payload schema.
- Project_06 response carries its own producer identity/version and result. The result includes the draft and per-input provenance; each original input remains available unchanged under its input evidence record.
- If normalization is needed, the response records source schema version, adapter/transform version, and normalized internal representation separately. The source version and raw payload are never rewritten.
- Unknown envelope versions or producer versions fail explicitly. Optional unknown payload fields remain in the raw payload even if the current internal model does not interpret them.

Illustrative shape only (field names and exact nesting require review):

```json
{
  "contract_version": "<TBD: team-approved envelope version>",
  "request_id": "SYN-REQ-001",
  "input": {
    "planning_request": {
      "producer": {"agent_id": "query-trend-agent", "schema_version": "1.0"},
      "status": "ok",
      "payload": {"request_id": "SYN-REQ-001", "schema_version": "1.0", "query": "synthetic request"}
    },
    "trend_result": {
      "producer": {"agent_id": "trend-analysis-agent", "schema_version": "1.1"},
      "status": "partial",
      "payload": {"request_id": "SYN-REQ-001", "schema_version": "1.1", "trends": []}
    },
    "inventory_product_result": {
      "producer": {"agent_id": "stock-agent", "schema_version": "1.0"},
      "status": "ok",
      "payload": {"request_id": "SYN-REQ-001", "schema_version": "1.0", "products": []}
    }
  }
}
```

The `contract_version` placeholder is intentionally not a valid agreed version. `vogue-handoff/0.1-proposal` remains one unapproved candidate and is not applied by this proposal.

## Producer version compatibility proposal

Producer versions are independent. Project_06 should maintain a reviewed support matrix instead of requiring all producer `schema_version` values to be equal.

| Producer input | Version in the reported pipeline | Proposed Project_06 handling | Decision owner |
| --- | --- | --- | --- |
| PlanningRequest | `1.0` | Candidate supported version; validate against its owner’s schema/fixture | Query/request owner + Project_06 |
| TrendResult | `1.1` | **Pending review.** Trend owner supplies schema definition and synthetic fixture; Project_06 confirms field semantics and writes an explicit adapter only if compatible | Trend owner + Project_06 |
| InventoryProductResult | `1.0` | Candidate supported version; validate against stock owner’s schema/fixture | Stock owner + Project_06 |

For each supported producer version, record the source schema version, adapter version, normalization outcome, and preserved raw payload. Do not infer that `1.1` is backward compatible merely from the number. No support date is proposed until the Trend owner provides the actual `1.1` contract and the owners agree on acceptance criteria.

## Status and MD review semantics proposal

| Upstream status | Project_06 may use as evidence? | Candidate behavior |
| --- | --- | --- |
| `ok` | Yes, subject to normal validation and Evidence limits | Use valid fields; preserve source payload. |
| `partial` | Only available, valid fields | Continue with explicit limitations and questions; mark draft for MD review. |
| `no_results` | No result facts from that input | Treat as successful lookup with no matching result, never as numeric zero. Continue with other valid inputs and ask for review/next step. |
| `error` | No result facts from that input | Preserve error details; continue only if request and remaining inputs are valid. Mark limited draft for MD review. |

Candidate Project_06 response rule: return `partial` when a usable draft is produced with any non-`ok` input, conflict, missing evidence, or material limitation; reserve `error` for Project_06 request validation or execution failure. Whether Project_06 needs an overall `no_results` status, and exactly when it applies, remains open. A draft is always `md_review_required`; upstream error/no-results does not authorize adoption, pricing, purchasing, or production.

An invalid JSON body, missing required input, mismatched `request_id`, or unsupported schema version does not produce a planning draft. HTTP status mapping and standardized error body remain TBD. Upstream status `error` is data about a source call and must not be confused with a Project_06 HTTP or execution error.

## Security and operations: unresolved

- Endpoint ownership, path, base URL, synchronous/asynchronous behavior: TBD.
- Service-to-service TLS and Bearer token are candidates; issuer, audience/scope, rotation, and secret handling: TBD.
- API Design's 3-second connect timeout and 60-second per-agent request timeout are proposal values only.
- API Design's one additional attempt for connection failures and HTTP 429/502/503/504 (respecting `Retry-After` for 429) is a proposal only. Automatic retries remain disabled until idempotency behavior is agreed and implemented.
- `Idempotency-Key: {request_id}:{agent_id}` is a candidate format; persistence, retention, and same-key/different-body rules are TBD.
- No service address, credentials, deployment, or production retry behavior is defined here.

## Synthetic fixture and verification plan

The fixture file contains synthetic inputs and expected behaviors for current versus proposed handling. It uses invented IDs and values only. Before enabling a producer version, run the relevant case against its explicitly versioned adapter and assert raw-payload, status, Evidence, limitations, and errors preservation.

| Case | Current adapter observation | Candidate agreed-contract expectation |
| --- | --- | --- |
| All sources `ok`, versions request `1.0`/trend `1.0`/stock `1.0` | Accepted; top-level response may still be `partial` because Project_07 is absent | Accept; preserve source statuses and show Project_07 as `not_provided`; overall status policy to approve |
| Trend or stock `partial` | Accepted; status and limitations are carried | Continue with usable fields and explicit limitations; MD review required |
| `no_results` vs inventory quantity `0` | Both are accepted but remain distinguishable by status vs product record | Preserve distinction; zero requires an actual stock record and unit/as-of/evidence as available |
| Upstream `error`, other inputs valid | Accepted; input status/error is retained and response is limited | Continue without using failed result as evidence; MD review required |
| Request ID mismatch | Rejected before draft generation; current handler responds 400 | Explicit validation error; no merged draft |
| Trend `1.1`, request `1.0` | Rejected before draft generation by equality check | Accept only if the reviewed support matrix includes Trend `1.1`; otherwise explicit compatibility error |
| Unknown producer schema | Rejected only when a supplied schema differs from PlanningRequest; missing versions currently use fallback | Explicit unsupported-version error; no implicit fallback in the approved contract |
| Payload/provenance round trip | Accepted inputs are returned under `input_evidence.*.payload`; source metadata origins are included | Preserve raw payload and source metadata separately from any normalized representation |

## Approval and ownership needed

1. Orchestrator, Project_06, producer owners, and contract steward agree on envelope fields/version and request/response semantics.
2. Trend owner supplies the exact `1.1` schema and fixture; Project_06 and orchestrator agree on the adapter/support matrix.
3. Stock and request owners confirm their `1.0` fixtures and status/Evidence/error semantics.
4. Project_08 confirms which provenance/status fields the review UI needs.
5. Owners decide endpoint, authentication, HTTP error mapping, timeout, retry, and idempotency policy.
6. Only after these approvals, implement the agreed changes and run the accepted synthetic fixture suite.

No Project_06 code, endpoint, configuration, or operational setting was changed for this proposal.
