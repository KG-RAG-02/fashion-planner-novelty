# Local H&M Kaggle Data

Download the H&M Personalized Fashion Recommendations competition files into:

```text
data/raw/hm-personalized-fashion-recommendations/
```

The contents of `data/raw/`, `data/interim/`, and `data/processed/` are ignored by Git. Do not force-add competition files or customer-level records. See [the ingestion and analysis plan](../docs/design/hm-kaggle-data-pipeline.md) for the intended processing boundary.

## Download

이 프로젝트 작업본에는 다운로드한 ZIP이 이미 `data/raw/hm-personalized-fashion-recommendations/`에 있습니다. 새 환경에서 다시 받는 경우 Kaggle 로그인 후 competition 규칙을 수락하고 브라우저 또는 Kaggle CLI를 사용하세요:

```bash
python3 -m pip install kaggle
kaggle competitions download -c h-and-m-personalized-fashion-recommendations \
  -p data/raw/hm-personalized-fashion-recommendations --unzip
```

Keep Kaggle credentials in Kaggle's local credential store. Do not copy the Kaggle token into `.env`, source files, logs, or Git.

The competition archive is large (Kaggle currently lists about 34.56 GB). The project workspace had sufficient free space when checked on 2026-11-05; recheck before downloading.

브라우저에서 받은 ZIP을 이 디렉터리에 둘 수 있습니다. 파이프라인은 이미지 압축 파일을 풀지 않고 필요한 CSV 두 개만 읽습니다. 압축 해제 CSV도 지원합니다. 데이터 갱신 시 저장소 루트에서 실행하세요:

```bash
PYTHONPATH=src python3 -m vogue_npp.sources.hm.hm_data
```

The pipeline produces `article_catalog.csv`, `weekly_sales_by_article_channel.csv`, Style/category/color/channel/monthly analysis CSVs, `hm_analysis.json`, and `manifest.json` under `data/processed/hm-personalized-fashion-recommendations/`. All remain local/ignored. The current dataset inspection and metrics are recorded in [the pipeline plan](../docs/design/hm-kaggle-data-pipeline.md).
