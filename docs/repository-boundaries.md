# Project_06 repository boundary

## Current ownership

P06 owns analysis of the PlanningRequest, Trend and Stock results, the sourced new-product draft, and `draft.visuals.product` / `draft.visuals.outfit` creation. P08 owns the Trend and Stock calls, the P06 call, the P07 review call, response aggregation and planning-board rendering. P06 never calls P07 and never creates a planning board.

The active endpoint is `POST /v1/agents/new-product-agent/runs`, using the P08 local branch's `vogue-handoff/0.3` request and response envelope. P06 accepts exactly `planning_request`, `trend_result`, and `inventory_product_result`; supported schemas are 1.0, 1.1, and 1.0 respectively. The input adapter retains original payloads and schema/provenance information while preparing the Trend copy for internal analysis.

## Service and data boundary

P06 consumes producer responses supplied by P08 and does not import sibling repositories or query operational Trend/Stock databases. Generated images are stored as content-addressed artifacts below `VOGUE_DRAFT_ARTIFACT_DIR`; a local SQLite ledger records request ownership and response replay. P08 reads the shared image volume read-only and verifies artifact byte size and SHA-256.

`local` mode binds to loopback. `private` mode supports bearer-authenticated HTTP inside an isolated service network. `service` mode requires bearer authentication and TLS.

## Removed from the active flow

`/v1/agents/new-product-agent/drafts`, P06 review bridge routes, planning-board generation and old workflow/0.1 request adapters are not active runtime paths. Offline tests use mock image providers; P06 does not generate fixture images. The runbook and README describe the current `/runs` flow; retired proposal and provisional-decision documents have been removed.
