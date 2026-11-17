# Project_06 workflow service

## Run locally

```bash
VOGUE_HTTP_MODE=local \
VOGUE_DRAFT_ARTIFACT_DIR=data/local/p06-artifacts \
PYTHONPATH=src python3 -m vogue_npp.prototype.server
```

The server binds to `127.0.0.1:8767`. `GET /api/health` returns service health. Local mode is loopback-only. For container-to-container plain HTTP, use `VOGUE_HTTP_MODE=private` with bearer authentication on an isolated network. `service` mode requires TLS and bearer authentication.

## Active API

`POST /v1/agents/new-product-agent/runs` accepts `vogue-handoff/0.3`: an envelope with `contract_version`, `request_id`, and `input`. The input contains only `planning_request`, `trend_result`, and `inventory_product_result`. P06 validates the request ID, producer/schema versions and statuses, normalizes Trend 1.1 on an internal copy, and preserves source payloads and adapter provenance in the response.

The response uses the P08 native envelope and result schema 1.0. P06 produces `draft.product_profile`, concept, limitations, conflicts and questions; P08 uses the profile for its own P07 `/reviews` call. P06 does not call P07 or create the planning board. Reusing a committed `request_id` with different input returns `409 REQUEST_ID_REUSED`; simultaneous identical requests return the first committed response.

## Product and outfit visuals

P06 returns both `draft.visuals.product` and `draft.visuals.outfit` with an explicit `generated`, `failed`, or `skipped` status. Each visual includes the same `product_specification_sha256` and `specification_alignment: same_product_profile`; this confirms the prompts used the same product profile, not that rendered pixels match. Real generation is enabled only with `VOGUE_DRAFT_IMAGE_PROVIDER=openai` and image credentials. No configured provider is marked skipped; an unsupported provider name or provider/artifact failure is marked failed and makes the overall result `partial`. Synthetic fixture image generation is not part of the runtime. The two OpenAI image calls run sequentially, one active image pair at a time: the product image is generated from the product profile (details included), then the outfit is an Images Edit API call (`/v1/images/edits`) that receives the stored product image as its reference input, so both visuals show the same garment. The outfit visual records that input as `reference_image_sha256`. If the product image is not produced, the outfit is not generated from text alone; it is `skipped` with `OUTFIT_REFERENCE_UNAVAILABLE`. Visual identity is still not verified automatically. Stock photos are not forwarded as image-generation references. `VOGUE_DRAFT_IMAGE_TIMEOUT_SECONDS` controls each call (default 180 seconds, clamped to 5–300), so the image stage can take up to about twice that. P06 does not automatically retry model calls because a timed-out client cannot know whether the provider already processed and billed the request. A durable request claim and saved response prevent replay of completed work and refuse to repeat a paid image attempt whose outcome is unknown; use a new request ID for an intentional new attempt.

`generation_metadata.timings_ms` reports input validation/normalization, planning analysis, each image call, combined image wall time, per-artifact persistence, response serialization, and total processing before response-cache persistence. The `p06_draft_completed` Docker log adds response-cache persistence and total processing including that write. The correlated `p06_http_response_serialized` log reports the HTTP status and response JSON serialization time. Join both log events by `request_id`; neither log contains prompts, image bytes, raw upstream payloads, or credentials. The response's `validation_issues` and completion log `partial_issue_codes` identify causes such as `UPSTREAM_PARTIAL`, `UPSTREAM_NO_RESULTS`, `PLANNING_ANALYSIS_PARTIAL`, `IMAGE_API_TIMEOUT`, or `ARTIFACT_PERSISTENCE_FAILED`.

Artifacts are stored under `VOGUE_DRAFT_ARTIFACT_DIR` (default `/app/data/local/p06-artifacts`) at `images/<sha256>.<ext>`. References include URI, media type, size and digest; a SQLite ledger binds request ID + visual kind to the artifact. P08 mounts the volume read-only and verifies bytes before use. P06 exposes no public image URL route.

## Contract source

The implementation was compared against P08's local `orchestrator-integration-branch` working tree, including its `/runs` request/response schema and `planning_sheet.py` visual reader. That P08 tree is local and uncommitted; this is compatibility with that snapshot, not proof of a frozen cross-project contract. Keep both repos' schemas and artifact mount in sync before deployment.
