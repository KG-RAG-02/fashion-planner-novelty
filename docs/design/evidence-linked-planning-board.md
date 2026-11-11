# Evidence-linked planning board

## Purpose

The planning board is a review artifact, not an approval or production specification. It keeps producer observations, Project_06 interpretation, proposals, and validation questions distinct. Text and Evidence labels must be rendered deterministically so image generation cannot alter identifiers or numeric values.

## Current contract and code gaps

| Input | Source payload retained | Evidence ID handling | Evidence detail / current use |
|---|---|---|---|
| Planning request | Yes, under `input_evidence.planning_request.payload` | Recursively collected; request-level and requested-attribute IDs enter context | The query and supplied fields inform scope. A request ID alone does not retrieve the source document. |
| Trend | Yes; handoff preserves source schema and payload | Candidate, attribute, description and root IDs collected. Trend row IDs attach to normalized observations where supplied. | Compatible, evidenced observations can inform the draft and product image. Unlinked root IDs remain traceable in raw payload/input metadata. |
| Stock | Yes, under `input_evidence.inventory_product_result.payload` | Product IDs retained; per-trend IDs attach by `product_index`. Root evidence can remain result-level if no explicit relation is supplied. | Quantity and attributes inform own-product context; role-compatible items feed outfit prompts and optional image references. Category is not compared as a mismatch with the requested new-product category. |
| Sales/market (Project_07) | Yes, copied as an opaque payload | Recursive Evidence IDs retained in input metadata and context | Detailed values are not normalized as a shared contract. The board therefore labels the section `blocked` / “상세 해석 보류” and may show IDs as unverified references only. Project_07 owner must agree on the finding schema before semantic use. |

Evidence ID preservation is not source verification. For inputs without quotes, source name, locator, permission and a supported resolver, the board marks the claim unverified or retains it in the source payload. Product-level facts are not attributed to unrelated root Evidence.

## Internal board model

`src/vogue_npp/workflows/planning_board.py` defines `PlanningBoard`, `BoardSection`, and `BoardClaim`.

- `BoardSection` records section ID/title, producer, input status, schema version, display state, claims and limitations.
- `BoardClaim` records display text, kind (`observation`, `interpretation`, `proposal`, `user_requested`, `to_validate`), Evidence IDs, producer and source reference, and verification state.
- `PlanningBoard` records the title, season/category, review label, ISSUE → INSIGHT → PROPOSAL flow, sections, displayed Evidence IDs and limitations.

The initial state mapping is `available`, `partial`, `no_results`, `not_provided`, `unverified`, `blocked`, or `failed`. Finance is `not_provided` until supported inputs/formulas exist. Sales/market details remain `blocked` pending the Project_07 agreement.

For product-image generation, `ImageGenerationRequest.evidence_uses` records each allowed ID with producer, source reference and the claim it supports. `excluded_evidence` records IDs deliberately omitted and why. Request-level IDs without field linkage, incompatible trend candidates, inventory evidence and all Project_07 IDs are excluded from the new-product prompt. Product-specific stock attributes/images belong only to outfit generation. Only `planning_reference`/`taxonomy` retrieval results with a quote, verified source, authorized permission and `product_planning` permitted use are accepted as visual references.

## Rendering and image boundaries

`render_planning_board_svg()` deterministically draws headings, cards, claims, status labels and Evidence IDs. The generated new-product image is embedded as the visual. The renderer does not call an image model to draw text. The board endpoint returns an SVG URL plus structured sections and Evidence IDs. Outfit generation remains a separate stage.

Only permitted retrieval results are included in the reference section. The current Project_06 stock schema accepts an optional `products[].image.url` extension, but stock schema 1.0 does not guarantee it. See `contracts/http-handoff-v0.1.md` for the allowlisted HTTPS image-fetch boundary.

## Project_07 agreement required

Before displaying sales/market findings as facts, the Project_07 owner must confirm schema version and fields for period/as-of, analysis scope/population, measure/value/unit, observation-versus-forecast, finding-level Evidence IDs, source/quote/locator, status, limitations, errors, and missing data. Until then, preserve the raw payload and status without interpreting findings.

## Validation

Automated checks cover source-linked trend/request claims, opaque sales status, exact Evidence labels, product-image embedding, and the review-only label. Manual visual review is still needed for typography and long-content fit in the target browser/viewer. More producer fixtures are required for missing and disconnected root Evidence, sales statuses, and licensed reference materials.
