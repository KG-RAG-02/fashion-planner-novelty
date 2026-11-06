# Project_06 implementation status

Updated 2026-11-06 after aligning code ownership with the sequential VOGUE workflow.

## Current Project_06 scope

Project_06 implements new-product planning only. It consumes request, trend, product/inventory and Project_07 sales/market results; it does not own their source queries or perform sales/market calculations.

## Current code

- Request/trend/inventory normalization and Project_07 handoff boundary: `src/vogue_npp/domain/context.py`
- TrendBatch validation and Trend × Category evaluation: `src/vogue_npp/domain/trend_batch.py`, `trend_evaluator.py`
- Evidence-aware product candidate and concept generation: `src/vogue_npp/domain/analysis.py`, `candidates.py`, `generator.py`, `concept.py`
- Knowledge retrieval interface: `src/vogue_npp/domain/retrieval.py`
- Planning use case and optional image generation: `src/vogue_npp/workflows/`
- Local planning-only review UI: `src/vogue_npp/prototype/`, `web/prototype/`

## Project_07 ownership

Sales domain records, historical H&M ingestion/quality/aggregation/adapter, synthetic sales/operations analysis and related tests/documentation were transferred to the Project_07 repository. No operational source connector was established by this move. No `data/` content, local database or `.env` was moved or edited.

## Remaining work

1. Agree on the cross-project request/result envelope and version.
2. Connect authorized upstream trend, product/inventory and Project_07 outputs through adapters.
3. Connect approved KG/RAG retrieval where available.
4. Agree on MD-reviewed product-planning scoring criteria and evaluation set.
5. Run MD review against fixed, evidence-backed test cases before making quality claims.

The transferred sales implementation is tested in Project_07. Project_06 tests cover planning behavior and handoff preservation, not sales computations or live data connections.
