# Project_06 HTTP handoff v0.3

The canonical route is `POST /v1/agents/new-product-agent/runs`. It creates a product planning draft and requests the new product visual from three inputs only. Sales/market analysis is not a planning or image-generation input.

The envelope fields are exactly `contract_version`, `request_id`, and `input`. `input` contains exactly these JSON objects:

- `planning_request` (schema 1.0)
- `trend_result` (source schema 1.1; normalized internally to 1.0 while preserving the source payload)
- `inventory_product_result` (schema 1.0)

```json
{
  "contract_version": "vogue-handoff/0.3",
  "request_id": "planning-001",
  "input": {
    "planning_request": {"schema_version": "1.0", "request_id": "planning-001", "query": "27SS 아우터 기획"},
    "trend_result": {"schema_version": "1.1", "request_id": "planning-001", "status": "partial", "trends": [], "evidence": []},
    "inventory_product_result": {"schema_version": "1.0", "request_id": "planning-001", "agent_id": "stock-agent", "status": "ok", "products": [], "evidence": []}
  }
}
```

An extra `sales_market_result` input is rejected. P08 calls the separate `POST /v1/agents/new-product-agent/sales-market-reviews` route after draft generation; it is a post-draft review bridge and is not part of the planning or image-generation inputs.

Project_06 does not retrieve synthetic catalog, guideline, precedent, or taxonomy records from R2. H&M product photos may remain enabled as external visual references, clearly separated from company facts and from the new-product image prompt. The new-product image uses the planning request and eligible trend observations; stock products/images are reserved for the separate outfit image stage.

Successful domain responses use HTTP 200 for `ok`, `partial`, `no_results`, and `error` source statuses. The source Trend payload and version remain available in `input_evidence.trend_result`; the internal normalized view is not presented as the source contract.
