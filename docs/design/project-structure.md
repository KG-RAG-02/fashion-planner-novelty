# Project_06 structure

Project_06 owns new-product planning. The direction remains `domain` ← planning workflows ← HTTP adapter; domain code does not import a browser UI, SQLite, or source-specific sales modules.

```text
src/vogue_npp/
├── domain/       planning inputs, evidence-aware evaluation, product concepts and candidates
├── workflows/    TrendBatch use case, planning brief and opt-in image generation
├── prototype/    Project_08/API client HTTP adapter (planning draft endpoint)
└── settings.py   runtime image-generation settings
```

## Boundaries

- TrendBatch, Trend × Category fit, existing/new product concepts and MD review support belong here.
- Product and inventory data are consumed from the upstream agent; Project_06 does not connect to operational product/inventory databases.
- Sales and market results are received as a Project_07 handoff. Sales aggregation, market research, H&M historical processing, sales fixtures and their source adapters belong to Project_07.
- `data/` holds local planning drafts and generated review images only; sales data and source adapters remain in Project_07. Local data files are ignored and should not be committed.
- Planning-only retrieval scope and the Project_07 Evidence boundary are documented in [the KG/RAG design](planning-rag-design.md).

## Run

```bash
PYTHONPATH=src python3 -m vogue_npp.prototype.server
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

The server exposes planning API routes only; it does not serve browser pages or static web assets. Project_08 owns the local UI. Every planning-draft API request requests a product image and, after successful product image generation, a planning-board image. Actual provider calls still require server image-generation enablement and credentials.
