# H&M Kaggle 수집·정제·집계 파이프라인

- 상태: 로컬 수집·정제·집계 및 UI 표시 완료
- 담당: New Product Planning Agent 저장소
- 입력: H&M Personalized Fashion Recommendations Kaggle competition 파일
- 처리 버전: `0.1.0`

## 목적과 범위

다운로드한 competition 파일에서 H&M 상품 카탈로그와 과거 구매 행을 검증·정리하고, **주차 × 상품(article) × 판매 채널** 단위의 관측 집계를 생성한다. 이 산출물은 New Product Planning Agent가 자사 상품 관계와 과거 실적을 검토할 Evidence 후보이다. 미래 수요 예측이나 실시간 운영 데이터로 사용하지 않는다.

경쟁상품 조사는 하지 않는다. 현재 재고 조회는 Agent 2의 책임이며, 원가·마진·생산·조달·고객 피드백 분석은 추후 별도 Agent 4 저장소의 책임이다. 이 데이터에는 현재고, 반품, 품절, 매장 ID, 기준 할인 가격, 상품 출시일, 리뷰·문의가 있다고 가정하지 않는다.

## 입력 파일과 선택 이유

필수 파일은 `articles.csv`와 `transactions_train.csv`이다. `customers.csv`의 고객 속성이나 고객별 기록은 이 MVP에 필요하지 않아 읽거나 출력하지 않는다. 이미지 폴더와 `sample_submission.csv`도 이 배치 분석에 사용하지 않는다.

필수 컬럼은 실행 시 실제 헤더에 대해 검사한다.

| 원천 | 필수 필드 | 처리 |
| --- | --- | --- |
| `articles.csv` | `article_id` | 원본 상품 메타데이터 행을 유지해 로컬 정제 카탈로그에 기록한다. 스타일·분류·색상·부서·설명 등 세부 열은 실제 CSV 헤더를 manifest에 기록하며 임의 변환하지 않는다. |
| `transactions_train.csv` | `t_dat`, `customer_id`, `article_id`, `price`, `sales_channel_id` | 고객 식별자는 출력하지 않는다. 날짜·상품·채널·가격을 검증하고 고객별로 분리되지 않는 기간별 집계만 만든다. |

Kaggle source의 중복 거래 행은 여러 번의 구매일 수 있으므로 중복 제거하지 않는다. 각 유효 행을 1 purchase row로 세며, 원천 스키마 확인 전 이를 고유 주문 수라고 부르지 않는다.

## 실행

원본 CSV를 풀어 두거나 Kaggle ZIP 파일을 `data/raw/hm-personalized-fashion-recommendations/` 바로 아래에 놓는다. ZIP은 이미지 전체를 별도 압축 해제하지 않고 필요한 CSV만 순차적으로 읽는다.

```bash
PYTHONPATH=src python3 -m vogue_npp.hm_data
```

다른 원본 또는 출력 위치를 지정할 수 있다.

```bash
PYTHONPATH=src python3 -m vogue_npp.hm_data \
  --source data/raw/hm-personalized-fashion-recommendations/h-and-m-data.zip \
  --output data/processed/hm-personalized-fashion-recommendations
```

필수 파일 누락, 중복 파일, 필수 컬럼 누락은 오류로 끝낸다. 거래 행에서 날짜·식별자·채널·가격이 유효하지 않으면 행을 제외하고 건수를 manifest에 남긴다. 상품 ID가 카탈로그에서 발견되지 않은 행은 집계에서 제거하지 않고 `matched_article=false`와 건수로 표시한다.

## 산출물

기본 출력 경로는 `data/processed/hm-personalized-fashion-recommendations/`이며 Git에서 제외된다. 기본 ingest 명령은 원천 CSV 확인, 주간 집계, 그 집계 기반의 카테고리/Style 분석까지 이어서 수행한다. `hm_analysis.json`은 로컬 프로토타입의 별도 H&M 데이터 화면에서 읽으며, 합성 fixture와 브리프/LLM 흐름에 자동 병합하지 않는다.

| 파일 | 내용 |
| --- | --- |
| `article_catalog.csv` | `articles.csv`의 비어 있지 않은 `article_id` 상품 행. 실제 원천 헤더와 열을 보존한다. |
| `weekly_sales_by_article_channel.csv` | 월요일 시작 주, 상품, 판매 채널별 구매 행 수와 원천 price의 합계·평균·최솟값·최댓값. 고객 식별자는 포함하지 않는다. |
| `style_sales_summary.csv` | `product_code`(Style) 단위 기간 전체 구매 행과 평균 원천 price, 대표 상품 속성, 우세 채널 코드, 판매·카탈로그 Evidence ID |
| `top_article_sales.csv` | 구매 행 상위 article ID 100개와 상품 속성 |
| `category_sales_summary.csv` | 상품군 × 상품 유형 × 채널 코드별 구매 행, 평균 원천 price, 고유 article·product_code 수 |
| `color_sales_summary.csv` | 색상군 × 상품군 × 채널 코드별 집계 |
| `monthly_product_group_sales.csv` | Monday 주차 집계를 주 시작일의 월에 귀속해 만든 상품군별 월간 관측 추이 |
| `channel_sales_summary.csv` | 채널 코드별 구매 행·평균 원천 price·고유 article/Style 수 |
| `hm_analysis.json` | 데이터 범위, 집계 수치, 상위 상품군·Style·색상, source ID와 사용 한계 요약 |
| `hm_quality_report.json` | 처리 데이터의 스키마·결측·중복 키·카탈로그 매칭·상품 분류 충돌·Article/Style 유형별 집계 차이 진단. `python -m vogue_npp.hm_quality`로 생성 |
| `manifest.json` | 파이프라인 버전, 원천 위치·SHA-256, 컬럼, 행 검증 건수, 관측 시작/종료일, 출력 행 수·SHA-256, 알려진 한계를 기록한다. |

SQLite 임시 집계 DB는 `data/interim/` 아래 생성 후 성공·실패와 관계없이 제거한다. 원천 파일은 수정하지 않는다. 원본 및 파생 파일은 Git에 커밋하거나 승인 없이 외부 모델/API로 전송하지 않는다.

## 필드와 지표 해석

- `purchase_rows`는 입력 transaction 행 수이다. 원천의 중복 행을 보존한 구매 기록 수이며 고객 수·고유 주문 수와 같다고 보장하지 않는다.
- `price_*_source_units`는 원천 `price` 수치의 기술 통계다. 통화, 정가, 할인율, 매출액 의미는 코드에서 부여하지 않는다. 따라서 price 합을 매출이라고 표현하지 않는다.
- `sales_channel_id`는 원천 코드 그대로 둔다. 코드 의미와 온라인/매장 대응은 별도 정의를 확인하기 전에는 이름 붙이지 않는다.
- 판매가 관측된 상품·주차만 결과에 나타난다. 행이 없다는 사실을 재고 없음, 품절, 상품 미판매로 확대 해석하지 않는다.
- `observation_period`는 유효한 원천 거래 날짜 범위이며 상품 출시일부터의 경과 주가 아니다.
- 고객별 코호트, 연관 구매, 고객 반응, 향후 판매 추정은 본 파이프라인에서 만들지 않는다. basket/order ID가 확인되지 않아 같은 날짜의 고객별 다중 구매를 함께 산 것으로 간주하지 않는다.

## 실제 다운로드 파일의 처리 기록

2026-11-05 로컬 ZIP을 확인해 다음 결과를 생성했다.

| 점검 항목 | 실제 처리 결과 |
| --- | --- |
| `articles.csv` | 105,542행, 25열, 빈/중복 `article_id` 없음 |
| `transactions_train.csv` | 31,788,324행, 필수 필드 오류 0행 |
| article ID 연결 | 주간 집계 행 중 상품 마스터 미매칭 0행 |
| 관측 기간 | 2018-09-20–2020-09-22 |
| 주간 article × channel aggregate | 2,814,421행 |
| 상품 코드 | 카탈로그상 47,224개 `product_code` |
| 채널 코드별 거래 행 | ID `1`: 9,408,462행 · ID `2`: 22,379,862행. 코드 정의는 미확인이라 의미를 붙이지 않음 |
| 거래 상위 상품군 | Garment Upper body 12,552,755행 (39.49%), Garment Lower body 7,046,054행 (22.17%), Garment Full body 3,552,470행 (11.18%) |

수치의 모집단은 해당 과거 competition 파일의 거래 행이다. 상품군별 구매 점유는 미래 수요나 전사 전체 매출 점유를 뜻하지 않는다. 가격 합계·평균도 원천 정규화 수치라 화폐 매출로 해석하지 않는다. 고객 ID와 고객 단위 이력은 분석 산출물에서 제외했다. 재고, 리뷰, 반품, 시즌은 이 데이터로 보충하지 않는다.

### 품질 감사와 카테고리 집계 기준

`PYTHONPATH=src python3 -m vogue_npp.hm_quality` 실행으로 현재 처리 결과를 점검했다. 카탈로그 105,542행에서 빈/중복 `article_id`는 0건이고 `detail_desc` 결측은 416건이다. 상품 코드 47,224개 중 315개가 복수 상품군 또는 상품유형에 연결된다. 주간 집계 2,814,421행은 31,788,324 구매 행을 나타내며, 중복 주간×상품×채널 키, 상품 마스터 미매칭, 음수/비정상 집계 행은 각각 0건이다.

스타일별 요약은 첫 카탈로그 행을 대표 속성으로 사용한다. 따라서 한 `product_code`가 여러 유형을 포함하면 유형별 판매량이 대표 유형으로 귀속된다. 현재 품질 감사에서 314개 판매 스타일 행에 복수 분류 충돌이 있었고, Article 기준과 Style 대표 속성 기준의 상품군×유형 판매량이 86개 분류에서 달랐다. 정확한 카테고리 분석은 `weekly_sales_by_article_channel.csv`를 `article_catalog.csv`와 `article_id`로 연결해야 한다. Style 요약은 스타일 수준 분석에만 사용한다. 상세 진단은 로컬 산출물 `hm_quality_report.json`에 저장한다.

## 다음 확장 경계

1. 파일이 바뀌면 컬럼·결측·ID 중복·날짜 범위·수치 범위를 다시 확인하고 manifest를 검토한다.
2. [H&M sales adapter](../../src/vogue_npp/hm_sales_adapter.py)는 현재 Style별 집계를 `SalesAnalysisResult`로 바꾼다. 카테고리 수준의 정확도를 위해 상품군/유형 필터는 Article 기준 판매 집계로 전환할 필요가 있다. H&M 분류를 요청 taxonomy로 연결하는 `source_category_map`은 호출자가 명시해야 한다. Agent 2 상품/재고 결과와 상품 ID 매핑이 합의되면 Evidence 참조를 연결한다.
3. 허용된 필드와 데이터 이용 조건을 확인한 뒤에만 RAG용 문서 표현·청킹·검색을 설계한다. 집계 테이블을 그대로 벡터화하지 않는다.
4. LLM 전송, 고객 수준 파생, 리뷰/문의 및 연관 구매 기능은 별도 근거·권한·설계가 필요하다.

다운로드 접근 및 이용은 [Kaggle 데이터 페이지](https://www.kaggle.com/competitions/h-and-m-personalized-fashion-recommendations/data)와 [competition rules](https://www.kaggle.com/competitions/h-and-m-personalized-fashion-recommendations/rules)에 따른다. 데이터의 과거 관측 기간을 보존하며 현재 사업 성과라고 표현하지 않는다.
