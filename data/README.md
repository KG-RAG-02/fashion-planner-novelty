# Project_06 data directory

P06 analyzes the user's planning request together with Trend and Stock results supplied by P08. It does not connect to operational databases or keep a product catalog in this directory.

## Runtime data

Generated drafts, image artifacts, and local replay/ownership state belong under `data/local/` and are ignored by Git. The active `POST /v1/agents/novelty/runs` endpoint stores generated product and outfit images below `NOVELTY_DRAFT_ARTIFACT_DIR`. A local SQLite ledger binds request IDs to their artifacts and saved responses so duplicate requests do not repeat completed image work.

P08 reads the shared artifact volume and verifies each artifact's ownership, byte size, and SHA-256. P06 returns artifact metadata, not image bytes embedded in the Draft JSON. Do not commit generated artifacts, credentials, source databases, or customer records.

## Data ownership

P08 owns Trend and Stock retrieval and sends their results to P06 as `trend_result` and `inventory_product_result`. P06 validates and analyzes those inputs, preserving provenance and reporting missing or conflicting evidence. H&M/Kaggle historical sales analysis belongs to Project_07; P06 does not process those datasets.
