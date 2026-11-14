# Project_06 local data boundary

Runtime-generated drafts, image artifacts, and local caches belong under `data/local/` and are ignored by Git. The active `/runs` endpoint stores request-owned image artifacts and replay state under `VOGUE_DRAFT_ARTIFACT_DIR`. Do not commit credentials, source databases, or customer records.

The synthetic product catalog, internal-guideline planning datasets, H&M visual-reference path, and its R2 image/catalog adapters have been removed. Project_06 planning uses the user request, Trend result, and Stock result supplied by P08. P06 generates product and outfit images from the resulting product profile when a real image provider is configured.

H&M/Kaggle historical sales processing and analysis are owned by Project_07. This repository does not process those sales datasets.
