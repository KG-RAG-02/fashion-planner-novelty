# Project_06 repository layout and service boundary

## Folder layout

The shared repository layout is `src/`, `tests/`, `docs/`, `data/`, `examples/`, `prompts/`, `scripts/`, and `contracts/`. Project_06 has no separate `configs/` or `web/` tree because its current service has no standalone configuration bundle or browser UI. Developer generators live under `scripts/`; generated and local state stays under `data/`.

## Ownership and HTTP boundary

Project_06 owns planning-draft generation, its local persistence, and the `new-product-agent` producer result. Its canonical agent route is `POST /v1/agents/new-product-agent/runs` using `vogue-handoff/0.1`. The request ID is carried by the outer envelope; the `input` object contains `planning_request`, `trend_result`, `inventory_product_result`, and `sales_market_result`. The P06-specific accepted versions and result behavior are defined in [`contracts/http-handoff-v0.1.md`](../contracts/http-handoff-v0.1.md).

Project_06 consumes upstream results and does not call Project_07 or Project_08. Project_08 owns sequencing and makes the HTTP calls. Project_06 does not import sibling repositories.

## Independent local operation

Run the local service with `VOGUE_HTTP_MODE=local`. It binds to loopback on port `8767` by default; Project_07 uses `8766` and Project_08 uses `8765`. Override the database path with `VOGUE_DB_PATH` when isolating local or synthetic runs. `GET /api/health` checks the service; it does not validate caller compatibility.

Local mode is loopback-only and the canonical `/runs` route requires `VOGUE_AGENT_SERVICE_BEARER_TOKEN`. Service mode additionally requires TLS files and the same bearer token for all API routes. It must not be exposed as a production service without deployment-level review.
