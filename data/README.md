# Project_06 local data boundary

Project_06 owns new-product planning and does not process sales datasets. H&M/Kaggle sales ingestion, analysis code, and the local historical dataset have been transferred to Project_07. In this workspace the raw archive is under `../../project_07/data/raw/hm-personalized-fashion-recommendations/` and processed outputs are under `../../project_07/data/processed/hm-personalized-fashion-recommendations/`.

These files are local and ignored by Git. Their presence does not establish Kaggle license permission for a particular use. Do not place sales datasets, source credentials, `.env`, or local databases back into Project_06. Project_06 may receive Project_07's evidence-backed result through its planning handoff.

`data/fixtures/planning_rag/synthetic_corpus.json` is a separate, fully synthetic corpus for exercising the local planning retriever. It is not company reference material and must not be treated as an operational source or approved business evidence.
