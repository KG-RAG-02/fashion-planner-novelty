# Project structure

This repository is organized by responsibility. The dependency direction is
`domain` ← data adapters and workflows ← the local prototype interface.
Domain code does not depend on the web app or local persistence.

```text
project_06/
├── data/
│   ├── raw/                         Downloaded source files (ignored by Git)
│   ├── processed/                   Reproducible analysis outputs (ignored)
│   └── local/                       Prototype SQLite state (ignored)
├── docs/
│   ├── decisions/                   Architecture decision records
│   └── design/                      Requirements, data contracts, and runbooks
├── examples/
│   └── fixtures/                    Clearly labeled synthetic demo data
├── src/vogue_npp/
│   ├── domain/                      Planning contracts and pure business logic
│   ├── sources/hm/                  H&M ingestion, audit, analysis, and adapter
│   ├── workflows/                   Human review and brief assembly
│   ├── prototype/                   Local HTTP app and supporting components
│   ├── settings.py                  Shared runtime settings
│   └── __init__.py                  Public package API
├── tests/                            Automated behavior and boundary checks
└── web/prototype/                    Browser UI and static assets
```

## Package responsibilities

- `domain/` contains normalized planning inputs, evidence-aware analysis,
  concept models, and generation interfaces. It should remain independent of
  Kaggle file paths, SQLite, HTTP, and UI code.
- `sources/hm/` reads local H&M competition files and writes derived reports.
  It adapts source observations into domain contracts but does not manufacture
  inventory, returns, customer preference, currency, or future demand.
- `workflows/` composes evidence and human decisions into reviewable planning
  artifacts. It owns image prompt assembly and the optional image-provider
  boundary; provider calls require both runtime enablement and per-call
  confirmation. No request is sent by default.
- `prototype/` serves the local interface and owns fixture access, persistence,
  and evidence lookup. The synthetic demo and H&M analysis remain separate.
- `web/prototype/` is static browser code; it calls the local prototype API.
- `data/` is runtime state. Source downloads, generated reports, and SQLite
  files stay out of Git; `data/README.md` documents how to recreate them.

## Canonical commands

Run these from the repository root:

```bash
PYTHONPATH=src python3 -m vogue_npp.sources.hm.hm_data
PYTHONPATH=src python3 -m vogue_npp.sources.hm.hm_quality
PYTHONPATH=src python3 -m vogue_npp.sources.hm.hm_planning_analysis
PYTHONPATH=src python3 -m vogue_npp.prototype.server
```

Each module has one canonical location. Older flat module paths were removed
after all in-repository callers and run commands moved to the package paths
above; the package-level public API in `vogue_npp` remains available.
