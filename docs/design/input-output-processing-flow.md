# Project_06 input/output processing flow

Project_06 is the new-product planning step in the VOGUE sequence:

```text
user query → trend agent → product/inventory agent → Project_07 sales/market agent
→ Project_06 new-product planning agent → MD final decision
```

## Inputs

| Input | Owner | Project_06 handling |
|---|---|---|
| `PlanningRequest` | Query/request stage | Preserve user request, season/category, constraints and missing fields. Do not invent missing values. |
| `TrendResult` or internal `TrendBatch` | Trend agent | Validate names, descriptions and traceable evidence; evaluate Trend × Category fit. Never require upstream rank or similarity. |
| `InventoryProductResult` | Product/inventory agent | Consume product facts and stock values with unit, as-of, status and evidence. Do not query inventory systems or infer sales from stock. |
| Project_07 sales/market result | Project_07 | Preserve result status, findings, evidence and limitations as an upstream handoff. Do not aggregate sales or conduct market analysis in Project_06. |

## Processing and outputs

1. Validate request identity, required structure, evidence IDs and upstream status.
2. Normalize trend text and evaluate its applicability to each requested category. Keep unknowns and unverified material explicit.
3. Compare the evidence-supported trend attributes with upstream product attributes where supplied. Generate existing-product improvement and new-product concept drafts.
4. Preserve Project_07 findings without changing their measures, scope, evidence or certainty. Do not turn historical sales into future demand or customer preference.
5. Apply only an explicitly configured and reviewed product-planning score. If the basis is missing, leave the score unset and report a limitation.
6. Return an evidence-linked planning draft, assumptions, risks, open questions and optional review visual. MD decides adoption and commercial terms.

## Status and missing data

`not_provided`, `no_results`, `error`, missing values and an observed numeric zero are distinct. Project_06 does not replace missing data with zero. A failure or partial response from Project_07 is carried as a limitation; it does not invalidate unrelated trend and product facts.

## Implementation boundary

The current handoff model is internal and not an agreed cross-project wire schema. There is no operational source-system API or database connector. The older H&M sales adapter and sales-analysis UI were transferred to Project_07; see [the current responsibility record](agent-3-responsibility-map.md).

## Project_08-facing API adapter

Project_06 exposes `POST /api/planning-draft` for Project_08 and other API clients. This is an adapter, not an automated end-to-end pipeline or a shared wire contract. It returns the internal `ProductConceptDraft`, input statuses, evidence IDs, limitations, conflicts, questions, validation issues, and each received payload unchanged in the input-evidence section. The compatibility adapter records whether producer ID, source schema version, and status came from the payload or were assumed/defaulted; trend-analysis-agent output currently has no producer/schema fields, so these are explicitly marked as adapter assumptions/fallbacks. Stock-agent `products[]` are normalized while their original array indexes are retained. Each `trend_results[]` row is separately exposed with its explicit `product_index`, mapping status, upstream trend-style match, row status, Evidence references, limitations, errors, and missing-data notes. A null product slot remains in the index space; products are never compacted before resolving links. The adapter maps row Evidence IDs to the linked product only when `product_index` resolves, and can resolve root `evidence[]` by exact `style_id`; unresolved or missing Evidence remains a review limitation. Fields that do not fit internal models remain traceable in the untouched raw payload. Project_07 sales/market results remain an opaque handoff: the complete payload is preserved and is not recalculated, reaggregated, or parsed for detailed findings by Project_06; its detailed field contract and transport remain unagreed. The public draft APIs require a Project_07 result object; an internal component-level context may still represent an absent result as `not_provided`. Every planning-draft API request requests the new-product visual with `gpt-image-2.5-flare` and automatically builds the evidence-linked board if that image succeeds; incoming image flags do not disable the request. Project_06 deterministically renders board text, status and Evidence labels into SVG, embedding the product visual. Image generation is not asked to draw board text or Evidence IDs. The board exposes structured sections and Evidence IDs with its review-only image URL. Project_07 details remain “상세 해석 보류” pending its shared field contract. Project_06 does not serve browser pages or static UI assets; Project_08 owns the local UI.
