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

The draft includes a sourced `product_profile`. The prose draft and product-image prompt consume that same profile in one generation flow; the image response exposes the profile and prompt hash used. The optional P07 review adapter projects only supported fields from that profile. See [P06 structured planning draft](p06-structured-planning-draft.md). This remains an internal P06 model and does not establish a shared wire contract.

## Status and missing data

`not_provided`, `no_results`, `error`, missing values and an observed numeric zero are distinct. Project_06 does not replace missing data with zero. A failure or partial response from Project_07 is carried as a limitation; it does not invalidate unrelated trend and product facts.

## Implementation boundary

The current handoff model is internal and not an agreed cross-project wire schema. There is no operational source-system API or database connector. The older H&M sales adapter and sales-analysis UI were transferred to Project_07; see [the current responsibility record](agent-3-responsibility-map.md).

## Project_08-facing API adapter

Project_06 exposes `POST /api/planning-draft` and the versioned `/v1/agents/new-product-agent/runs` route. These return the structured product profile and a new-product image generated from that same profile. Project_06 does not create planning-board images; P08 owns the board assembled from the P06 image and review material. P06's `POST /v1/agents/new-product-agent/sales-market-reviews` accepts the full P06 planning response and returns only the validated P07 0.2 request payload. P06 does not call P07; P08 sends that payload to P07 and combines the responses. The adapter is project-specific and does not establish a shared cross-project contract.
