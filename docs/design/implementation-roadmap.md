# Project_06 implementation status

Updated 2026-11-14 against the P08 local `orchestrator-integration-branch` working tree.

## Current Project_06 scope

P06 consumes the user PlanningRequest and Trend/Stock results supplied by P08. It validates and analyzes these inputs, creates the sourced new-product draft and may generate product/outfit images through an explicitly configured real provider. It does not call Trend, Stock, or P07 and does not render a planning board.

## Current code

- Producer input validation and schema normalization: `src/vogue_npp/adapters/draft_inputs.py`
- Planning context, Evidence-aware concepts and profile: `src/vogue_npp/domain/`
- P06 HTTP `/v1/agents/new-product-agent/runs`, response assembly and native `vogue-handoff/0.3`: `src/vogue_npp/prototype/server.py`
- Image generation and request-owned content-addressed artifacts: `src/vogue_npp/workflows/draft_artifacts.py`, `image_generation.py`
- P08 owns the P07 `/reviews` call, integrated response and planning-board rendering.

## Remaining work

1. Confirm and freeze the cross-project request/result contract with P08 owners; current compatibility is based on their local modified checkout.
2. Verify shared artifact volume mounts and image-provider environment settings in the integrated deployment.
3. Connect approved KG/RAG retrieval where available.
4. Evaluate drafts with fixed evidence-backed cases and MD review before making quality claims.

Project_06 tests cover planning behavior, input provenance, artifact ownership and the native P08 handoff. They do not make paid image calls or assert business outcomes.
