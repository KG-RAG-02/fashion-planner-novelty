# Project_06 new-product planning agent

## Current runtime

P06 exposes `POST /v1/agents/novelty/runs` using `novelty-handoff`. P08 sends a PlanningRequest 1.0, Trend 1.1, and Stock 1.0 result. P06 validates and normalizes inputs, runs its evidence-aware planning analysis, and returns `draft.product_profile` with a narrative concept and two visual statuses at `draft.visuals.product` and `draft.visuals.outfit`.

P06 uses an explicitly configured real provider for actual concept images. Offline tests use a mock provider and do not create synthetic image artifacts. If no provider is configured, image statuses are `skipped`; an unsupported provider or generation/storage error is `failed` and makes the overall result partial.

P06 does not call Trend, Stock, or P07, and does not create the planning-board image. P08 owns upstream calls, P07 review, aggregation and board rendering. It receives the P06 draft, projects its product profile into P07's `/reviews` request, and returns the integrated result.

## Analysis boundary

P06 uses the request, eligible Trend evidence, and Stock product/inventory context. It does not query operational databases or consume P07 review results. Claim types and evidence IDs remain distinguishable through draft generation. See the [P06 structure](project-structure.md) and [service runbook](prototype-runbook.md).
