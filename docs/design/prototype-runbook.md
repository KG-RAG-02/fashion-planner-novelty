# Project_06 planning prototype

## Run

From the repository root:

```bash
PYTHONPATH=src python3 -m vogue_npp.prototype.server
```

Open `http://127.0.0.1:8765`. The server binds to loopback by default. Stop it with `Ctrl+C`.

## What this UI does

The page shows a planning-only TrendBatch review example and an explicitly requested image-generation form. It does not query sales, market, product or inventory systems. Project_07 sales/market results and upstream product/inventory results are accepted at the domain handoff, not looked up by this prototype.

The SQLite file under `data/local/` stores planning briefs, image variants and MD evaluations. It is local state and is not part of the transfer. Existing `.env`, source datasets, generated files and local databases were not altered during the responsibility move.

## Image generation

Set `VOGUE_IMAGE_GENERATION_ENABLED=true` and `OPENAI_API_KEY` in the runtime environment. Image requests require the UI confirmation checkbox. The default page does not call the image provider. Generated images are exploratory design material and do not validate fit, materials, demand or production feasibility.

## Project_07 data products

The H&M historical analysis and synthetic sales/operations demos were removed from this UI and moved to the Project_07 repository. They are not loaded into the Project_06 planning fixture or brief.
