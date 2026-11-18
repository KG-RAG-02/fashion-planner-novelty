# Project_06 structure

Project_06 owns evidence-aware new-product planning and product/outfit visual artifacts requested through its P08 handoff API. Domain models do not depend on HTTP, browser UI, or artifact persistence.

```text
src/fashion_planner_novelty/
├── adapters/     upstream producer schema validation and normalization
├── domain/       planning context, evidence-aware concepts and candidates
├── workflows/    planning analysis, image providers and P06 artifact ownership
├── server/       stdlib HTTP service exposing P08 /runs
└── settings.py   runtime feature and credential settings
```

P08 owns Trend/Stock invocation, P07 review calls, workflow aggregation and planning-board images. P06 does not query operational databases or invoke sibling projects. Local images and SQLite ownership state stay under the ignored `data/local/` directory.

Run with `VOGUE_HTTP_MODE=local PYTHONPATH=src python3 -m fashion_planner_novelty.server`. The planning POST route is `POST /v1/agents/new-product-agent/runs`; see [repository boundaries](../repository-boundaries.md) and [service runbook](prototype-runbook.md).
