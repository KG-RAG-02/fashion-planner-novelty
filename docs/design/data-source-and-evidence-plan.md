# Project_06 data and Evidence boundary

Updated 2026-11-06. This replaces the earlier source plan that assigned H&M sales collection and analysis to Project_06.

## Sources and owners

| Information | Owner | How Project_06 uses it |
|---|---|---|
| User request | upstream request/query stage | Preserve requested category, season, constraints and missing values. |
| Trend names, descriptions and evidence | trend agent | Validate traceability; evaluate Trend × Category fit without rank/similarity input. |
| Product and inventory facts | upstream product/inventory agent | Preserve IDs, units, status, as-of and Evidence. Do not query the operational source. |
| Sales and market observations | Project_07 | Receive findings and source scope as a handoff; cite and carry limitations without recalculating. |
| KG/RAG context | approved retrieval adapter when configured | Use retrieved relationships/documents to support product-concept claims. No production KG/vector connector is configured by default. |

## Evidence handling

Each factual claim should retain its Evidence IDs and upstream status. Distinguish observation, interpretation, proposal, hypothesis and unknown. Missing, not provided, no results, query failure and numeric zero remain separate states. A supplied sales observation is not automatically future demand, customer preference or market growth.

## Current data connection status

There is no operational PostgreSQL, product/inventory API, sales source, external market provider, KG database or vector store connection in Project_06. The internal handoff is not an approved cross-project API contract. The local planning fixture is a review example, not a claim about live operations.

## Project_07 transfer

H&M historical processing/analysis adapters, synthetic sales and operations fixtures, and their tests/docs now live in Project_07. Project_06 data directories were left untouched. See [the responsibility and transfer record](agent-3-responsibility-map.md).

For planning-only retrieval of approved design guidance, taxonomy, prior briefs, and supplied Evidence references, see the [Project_06 KG/RAG design](planning-rag-design.md). That design does not assign sales or market research retrieval to Project_06.
