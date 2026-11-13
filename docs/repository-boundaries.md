# Project_06 repository layout and service boundary

## Folder layout

The shared repository layout is `src/`, `tests/`, `docs/`, `data/`, `examples/`, `prompts/`, `scripts/`, and `contracts/`. Project_06 has no separate `configs/` or `web/` tree because its current service has no standalone configuration bundle or browser UI. Developer generators live under `scripts/`; generated and local state stays under `data/`.

## Ownership and HTTP boundary

Project_06 owns planning-draft generation and the new-product image. It has no local brief/variant workbench or draft persistence. Its canonical agent route is `POST /v1/agents/new-product-agent/runs` using `vogue-handoff/0.3`. The input contains only `planning_request`, `trend_result`, and `inventory_product_result`; sales/market output is not part of planning or image generation. The P06-specific accepted versions and result behavior are defined in [`contracts/http-handoff-v0.3.md`](../contracts/http-handoff-v0.3.md).

Project_06 consumes upstream results and does not import sibling repositories. A separate `POST /v1/agents/new-product-agent/sales-market-reviews` adapter receives the full P06 PlanningDraft response, validates it, and returns only the projected Project_07 `/reviews` request payload. It never calls Project_07. Project_08 calls this adapter after P06 completes, sends the returned payload to Project_07, then combines the P06 and P07 results for the UI.

## Independent local operation

Run the local service with `VOGUE_HTTP_MODE=local`. It binds to loopback on port `8767` by default; Project_07 uses `8766` and Project_08 uses `8765`. `GET /api/health` checks the service; it does not validate caller compatibility.

Local mode is loopback-only and the canonical `/runs` route requires `VOGUE_AGENT_SERVICE_BEARER_TOKEN`. Service mode additionally requires TLS files and the same bearer token for all API routes. It must not be exposed as a production service without deployment-level review.
