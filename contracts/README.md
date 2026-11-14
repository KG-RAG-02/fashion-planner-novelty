# Project_06 HTTP contract notes

P06 receives one `vogue-handoff/0.3` request from P08 at `POST /v1/agents/new-product-agent/runs`. The request contains a `planning_request` (schema 1.0), `trend_result` (schema 1.1), and `inventory_product_result` (schema 1.0). P06 validates the envelope, producer identities, statuses, schemas, and matching request IDs before analysis.

The response producer is `new-product-agent`, schema version `1.0`. Its result contains the Draft and sourced `product_profile`, input evidence/provenance, validation issues and limitations, and product/outfit visual statuses. Generated visuals are request-owned artifact references with media type, byte size, and SHA-256; image bytes are not embedded in the response. If images are skipped or fail, the visual status and overall result communicate that outcome.

P06 does not call P07 and does not create a planning board. P08 projects eligible product-profile fields into its P07 review request, calls P07, and composes the final response and board.

[`http-handoff-v0.3.md`](http-handoff-v0.3.md) records the current P08-facing compatibility shape. It is a compatibility note, not a frozen cross-repository schema: the source contract is owned by P08, and both repositories must be reviewed together before changing the handoff. PlanningRequest, Trend, and Stock schemas remain owned by their respective producers.
