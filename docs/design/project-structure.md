# Project_06 structure

Project_06 owns new-product planning. The direction remains `domain` ← planning workflows ← local review UI; domain code does not import the web app, SQLite, or source-specific sales modules.

```text
src/vogue_npp/
├── domain/       planning inputs, evidence-aware evaluation, product concepts and candidates
├── workflows/    TrendBatch use case, planning brief and opt-in image generation
├── prototype/    local planning-only HTTP UI and review persistence
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

The local web UI only serves planning review and optional image generation. Image generation requires server enablement and explicit confirmation in the request form.
