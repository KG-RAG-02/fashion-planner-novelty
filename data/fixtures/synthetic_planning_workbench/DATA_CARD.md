# Synthetic planning workbench data card

- Dataset: `SYNTHETIC-PLANNING-WORKBENCH-SEED-20261110`
- Generator: `synthetic-planning-workbench-v2`
- Nature: fully fictional test and retrieval-evaluation material
- Intended use: local software development, deterministic retrieval tests, and draft-workflow evaluation only
- Prohibited interpretation: real company policy, actual assortment, product performance, customer preference, demand, sales, or market evidence
- Image content: none; the default synthetic planning RAG corpus is text and structured metadata only
- Storage: generated fixture in this repository; no external service or production index
- Reproduction: `python3 scripts/generate_synthetic_planning_workbench.py --seed 20261110`
- Validation: `PYTHONPATH=src python3 -m vogue_npp.synthetic_planning_workbench quality`
- IDs: all rows use `SYN-` or `SYNTHETIC-` namespaces and include dataset/generator/seed provenance
- Permission fields: `permission_status=synthetic_only`; this is an internal fixture classification, not company authorization
- Retention/deletion: normal repository fixture lifecycle; generated local caches remain under ignored `data/local/`

## H&M Kaggle data boundary

H&M product images are a separate external dataset and are not included in this synthetic dataset, its RAG index, generated attributes, or evaluation set. The outfit image flow forwards selected R2 H&M article photos to the image provider. This permission is independent of the generic R2 upload switch. See the [competition rules](https://www.kaggle.com/c/h-and-m-personalized-fashion-recommendations/rules) and [dataset page](https://www.kaggle.com/competitions/h-and-m-personalized-fashion-recommendations/data?select=transactions_train.csv).
