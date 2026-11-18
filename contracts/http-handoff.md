# P06 ↔ P08 handoff compatibility: `novelty-handoff`

P06 implements this request on `POST /v1/agents/novelty/runs`, aligned against the local P08 `orchestrator-integration-branch` contract snapshot. P08 remains the owner of orchestration and P07 review calls. This file is a compatibility note, not a separately frozen cross-repository schema.

## Request

```json
{
  "contract_version": "novelty-handoff",
  "request_id": "planning-001",
  "input": {
    "planning_request": {"schema_version": "1.0", "request_id": "planning-001"},
    "trend_result": {"schema_version": "1.1", "request_id": "planning-001", "status": "ok"},
    "inventory_product_result": {"schema_version": "1.0", "request_id": "planning-001", "agent_id": "inventory", "status": "ok"}
  }
}
```

The input object has exactly the three shown keys. Every input `request_id` must match the envelope. Unsupported producer schemas and malformed identities are rejected with HTTP 4xx. Reusing a committed request ID with a different payload returns HTTP 409 (`REQUEST_ID_REUSED`); simultaneous identical requests converge on the first committed response.

## Response

```json
{
  "contract_version": "novelty-handoff",
  "request_id": "planning-001",
  "producer": {"agent_id": "novelty", "schema_version": "1.0"},
  "status": "partial",
  "result": {
    "schema_version": "1.0",
    "request_id": "planning-001",
    "status": "partial",
    "draft": {"title": "...", "review_status": "md_review_required", "product_profile": {}, "visuals": {}},
    "input_evidence": {},
    "compatibility": {},
    "image": {},
    "outfit_image": {},
    "planning_board": null
  }
}
```

The result also preserves input statuses, planning analysis, Trend/Stock evidence, validation issues, limitations, conflicts, and open questions. `draft.visuals.product` and `draft.visuals.outfit` carry explicit status and, when generated, immutable artifact metadata (URI, media type, size, SHA-256). P08 reads those artifacts from the shared P06 artifact volume and performs its own P07 call and board composition. P06 does not provide a synthetic image mode; offline tests use a mock provider and do not emit generated image artifacts. P06 never calls P07 and never generates `planning_board`.

The authoritative request/result snapshots referenced by P08 live in Project_08. Confirm its current branch and artifact volume configuration before deployment.
