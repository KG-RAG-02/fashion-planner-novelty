# Project_06 기획안 에이전트 책임 경계 및 현재 구현 대조

- 상태: Notion과 저장소 간 정렬을 위한 작업 문서. 팀의 공통 계약이나 새 범위 승인이 아님
- 기준일: 2026-11-06
- 대상 저장소: `KG-RAG-02/new-product-planning-agent` (`project_06`)

## 목적

이 저장소는 VOGUE **Project_06 기획안 에이전트(Planning Agent)**를 구현한다. 상품 기회·콘셉트 생성, 근거 통합 기획안 초안 및 MD 검토 지원을 한 에이전트 책임으로 다룬다. 기존 코드·fixture의 소유권을 성급히 바꾸지 않고, Project_07 판매·시장 데이터 에이전트와의 제안 경계 및 이관 후보를 기록한다.

Notion 공용 페이지에 반영된 새 역할은 Project_06 기획안 에이전트, Project_07 판매·시장 데이터 에이전트이며, Project_07 결과가 Project_06보다 먼저 전달되는 흐름이다. 아래 세부 필드와 이관 범위는 담당자 합의 전 제안이다. 기존 문서 중 과거 단계 번호와 역할 정의는 아래 차이 표를 참고한다.

## Notion에서 확인한 업무 경계

| 단계 | 담당 | 이 저장소와의 관계 |
| --- | --- | --- |
| 1 | Query & Trend Agent | 요청 조건 정리와 트렌드 자료 검색·근거 반환. Project_06은 `PlanningRequest`, `TrendResult`를 소비한다. |
| 2 | Product & Inventory Agent | 자사 상품·재고 조회. Project_06은 `InventoryProductResult`를 소비한다. |
| 7 | Sales & Market Data Agent | 저장소 `market-research-agent`. 판매·시장 자료 조사·분석, 출처/기간/단위/정의/한계가 있는 결과 전달. 자료원과 구현 범위는 미정이다. |
| 6 | Planning Agent | 앞 단계 입력과 Project_07 결과를 통합해 기회·콘셉트 및 `PlanningDraft`를 작성하고 MD 검토를 지원한다. 콘셉트는 초안 내부 구성요소다. |

`사용자 쿼리 → Query & Trend → Product & Inventory → Project_07 Sales & Market Data → Project_06 Planning → MD 최종 판단` 순서다. 별도의 새 상품 생성 에이전트와 기획안 생성 에이전트를 운영 단계로 두지 않는다. 상품 채택·가격·원가·수량·발주·최종안은 MD가 결정한다.

## 현재 코드·문서 현황

| 구분 | 확인된 항목 | 상태 |
| --- | --- | --- |
| 실제 코드 | `sources/hm/hm_data.py`, `hm_analysis.py`, `hm_planning_analysis.py`, `hm_sales_adapter.py`; `prototype/server.py`의 H&M API; `prototype/analytics.py`의 합성 판매 분석 | 로컬 실행 기능. 운영 판매/시장 source 연결 아님 |
| 실행 가능한 실험/fixture | Kaggle 원본이 로컬에 있으면 historical aggregation; `examples/fixtures/prototype_demo.json`, `synthetic_merch_scenario.json`, `planning_operations_demo.json` | 원본 H&M 공개 과거 데이터 또는 명시적 합성. 내부 시스템/시장 사실로 간주 금지 |
| 설계 제안 | `SalesMarketDataResult`, `PlanningDraft` 의미 및 Project_07 이관 | 이 문서 및 입력 모델은 협의 초안. wire schema/adapter 확정 안 됨 |
| 운영 연결 | 사내 판매 원장, 시장 자료 공급원, 사내 API/DB, Project_07 API | 확인된 연결 없음. 조회 권한/자료원도 미확보 |

## 현재 코드·문서 현황

### 구현·실험·운영 연결 구분

| 구분 | 확인된 항목 | 상태 |
| --- | --- | --- |
| 실제 코드 | `sources/hm/hm_data.py`, `hm_quality.py`, `hm_analysis.py`, `hm_planning_analysis.py`, `hm_sales_adapter.py`; `prototype/server.py` H&M API; `prototype/analytics.py` 합성 판매 분석 | 로컬 기능이며 운영 source 연결 아님 |
| 실행 실험/fixture | Kaggle 원본이 로컬에 있으면 historical aggregation; `prototype_demo.json`, `synthetic_merch_scenario.json`, `planning_operations_demo.json` | 공개 과거 데이터 또는 명시적 합성 |
| 설계 제안 | `SalesMarketDataResult`, `PlanningDraft`, Project_07 이관 | 협의 초안. wire schema와 adapter 확정 안 됨 |
| 운영 연결 | 사내 판매 원장, 시장 자료, 사내 API/DB, Project_07 API | 확인된 연결·권한·자료원 없음 |

### 기존 분석의 이관 후보와 현재 사용처

| 후보 | 현재 사용처 | 제안된 조치 |
| --- | --- | --- |
| H&M Kaggle ingestion/quality/aggregation | `hm_data`, `hm_quality`, `hm_analysis`, `hm_planning_analysis`; processed reports와 Evidence manifest | Project_07 historical sales adapter 후보. 합의 전 유지. raw/derived data는 옮기지 말고 소유권·재현 절차 합의 |
| H&M domain sales adapter | `PlanningInputs.sales`, context/opportunity/generator, adapter 및 analysis tests | Project_07 output normalization으로 교체/이관할지 협의. 내부 dataclass는 공용 계약 아님 |
| H&M UI 및 검토 저장 | `/api/hm-analysis`, planning analysis/review/brief endpoints, `web/prototype`, SQLite `hm_*` tables | P06 초안과 P07 분석 UX의 소유권 합의. 기존 사용자 상태 영향 검토 전 삭제 금지 |
| 합성 판매·재고 분석 | `analytics.py`, planning operations/synthetic scenario API/UI와 fixture/tests | P07 이관/공유 후보. 합성 표시 유지, 실제 판매 사실로 혼합 금지 |
| 판매 중심 후보 scoring/retrieval ports | `domain/candidates.py`, `domain/retrieval.py`, trend workflow 및 tests | 사용처별 책임 분할. 운영 연결 미구현이므로 즉시 이동 안 함 |

| 영역 | 현재 구현/문서 | 책임 분류와 안전한 처리 |
| --- | --- | --- |
| 입력 정규화·컨텍스트 | `PlanningRequest`, `TrendResult`, `InventoryProductResult`를 핵심 입력으로 받고 Evidence/status/충돌을 보존. `SalesAnalysisResult`는 선택형 로컬 확장. | #3의 도메인 입력 정합성은 핵심 책임. 내부 모델은 공통 wire 계약이 아니다. |
| 기회 분석·콘셉트 초안 | `domain/analysis.py`, `domain/concept.py`, `domain/generator.py`, `workflows/planning.py`. 결정적 기준선과 내부 `ProductConceptDraft`가 있음. | #3의 핵심. Evidence 기반 관찰·해석·제안·가설·미확정을 분리하고, 공통 `ProductConcept` adapter는 팀 계약 합의 후 연결한다. |
| H&M Kaggle 분석 | `sources/hm/`의 로컬 수집·품질 점검·과거 판매 집계, `hm_sales_adapter.py`와 별도 H&M UI. 로컬 데이터 필요. | 기존 분석 책임은 Project_07 이관 후보. 즉시 삭제/이동 금지. raw/processed 데이터와 adapter/UI/테스트 의존을 유지하고 담당자 합의 후 이관 경로·라이선스·재현성을 정한다. Project_06 생성 경로는 판매 입력이 없으면 판매 사실을 만들지 않는다. |
| TrendBatch/Evaluator | `domain/trend_batch.py`, `domain/trend_evaluator.py`, `workflows/trend_planning.py`가 batch 입력, taxonomy 매핑, Evidence 확인, 카테고리 적합성 평가를 수행함. | raw trend 검색·정의·taxonomy 원천 관리·GraphRAG는 #1 경계와 겹친다. 후보 상품 카테고리에 대한 적용 가능성 평가는 #3의 일부가 될 수 있다. 정확한 분할 전까지 내부/실험 workflow로 유지하고 공통 TrendResult 대신 사용하지 않는다. |
| KG/RAG 및 상품 데이터 포트 | `domain/retrieval.py`, `domain/candidates.py`에 지식·상품·판매·재고 조회 인터페이스와 fixture가 있음. 운영 연결은 미구현. | trend index/retrieval은 #1, 상품·현재 재고 원천은 #2 소유. #3은 전달된 근거와 결과를 소비한다. 이 포트가 필요한 경우 승인된 adapter 경계와 소유자를 먼저 정한다. |
| 점수화·TOP 5 | 후보 점수·구성요소·다양성 selector가 있으며 점수 정책은 fixture/설정형 heuristic으로 문서화됨. | #3의 검토 보조 순위로 합의될 수 있지만 승인된 MD 기준이 아니다. 시장 트렌드 순위·수요 예측·최종 상품 선택처럼 표현하지 않는다. 점수 기준 승인 전에는 운영 판단으로 사용하지 않는다. |
| 로컬 UI·기획서·MD 검토 | `prototype/`, `web/prototype/`, SQLite가 합성/H&M 브리프·시안·검토 흐름을 보여줌. | 기존 로컬 UX를 보존한다. 합성 시나리오의 판매 분석 UI는 이관/공유 후보이며, H&M 전용 브리프는 Project_06 통합 초안과 별도다. Project_07 실제 결과 연결 전에는 모두 합성 또는 로컬 과거 자료로 표시한다. |
| 이미지 프롬프트·생성 | `workflows/image_generation.py`와 프로토타입 폼. 설정 활성화와 호출별 확인이 필요함. | 콘셉트 검토를 위한 선택형 보조 산출물이다. 상품 사양·Evidence·MD 승인으로 취급하지 않으며 자동 호출하지 않는다. |

## 확인된 불일치 및 미결정 사항

1. **역할 기준 차이:** 일부 설계 문서의 3번 New Product Research, 병렬 Feasibility, 5번 Draft Generation 역할은 새 Project_06/07 순차 흐름과 맞지 않는다. 이 문서와 README를 먼저 정렬했으며, 나머지 문서는 후속 갱신 대상이다.
2. **판매 분석 소유권:** 기존 Project_06에 H&M 과거 판매 분석과 판매 중심 fixture가 실제 구현되어 있다. Project_07로 조율할 후보이나 삭제·이동은 하지 않았다. 운영 원장/시장자료/API 연결은 확인되지 않았다.
3. **공용 계약:** `SalesMarketDataResult`와 `PlanningDraft`는 협의 전 제안이며 공통 wire schema가 아니다.
4. **Notion/저장소 간 차이:** 공용 Notion 역할 반영은 확인했으나 상세 필드, 입력별 실패 정책, 이관 범위는 코드/문서에 확정되지 않았다. 기존 Notion 설계 링크 중 구 역할 문구가 남아 있을 수 있으며 페이지별 동기화 확인이 필요하다.

## 다음 개발에서 적용할 안전한 기본 경계

- Project_06 핵심 경로는 `PlanningRequest`, `TrendResult`, `InventoryProductResult`, Project_07 결과(선택적/합의 후 입력)를 받아 기회·콘셉트를 포함한 하나의 `PlanningDraft`를 생성하는 것이다.
- 판매·시장 결과가 미제공이면 `not_provided`로 남긴다. 0, `no_results`, 실패, 권한 부족, 매핑 실패는 각각 구별하며 미확보 값을 생성하지 않는다.
- TrendBatch 실험은 별도 내부 경로로 유지한다. #1이 소유하는 원천 trend search와 taxonomy를 복제하지 않고, #3이 필요한 category-application 검토와 구분한다.
- 관측 판매는 미래 수요·고객 선호·성장 증거로 자동 해석하지 않는다. 재고는 판매 추세 대리값이 아니다.
- `partial/no_results/error`, 결측, 충돌, 조회 실패 및 각 입력 한계를 초안까지 보존한다.
- MD만 채택·가격·원가·수량·발주·최종안을 결정한다. 이미지 생성 등 외부 부작용은 명시 요청과 호출 확인 없이는 수행하지 않는다.
- 미승인 점수, 합성 fixture, Kaggle 과거 자료, 운영 데이터의 경계를 표시한다. 미조회·결측을 0으로 바꾸지 않는다.
- 사용자 변경사항, `.env`, `data/`, 로컬 SQLite 및 생성 파일을 보존한다. 기능 소유권 조정은 문서화와 adapter 경계부터 시작하고, 기존 구현 이동·삭제는 별도 검토 없이 하지 않는다.

## 후속 팀 결정이 필요한 항목

| 결정 | 현재 상태 | 결정 영향 |
| --- | --- | --- |
| H&M 과거 판매 분석과 합성 판매 분석/UI/fixture를 Project_07로 언제/어떤 단위로 이관할지 | 후보 목록 작성, 구현은 유지 | 저장소 경로·데이터 라이선스·adapter 및 회귀 검증 |
| TrendBatch validator·taxonomy 매핑·Trend × Category 평가의 #1/#3 분할 | 내부 workflow에 구현됐으나 공통 `TrendResult`와 분리 필요 | 모듈 소유권, 입력 adapter, 평가 책임 |
| 상품/판매/재고 query 포트의 데이터 소유자와 허용 범위 | 운영 DB 연결 없음 | adapter 및 입력 contract |
| 후보 점수와 TOP 5의 MD 승인 기준 | 현재 heuristic/fixture | 사용 여부, 해석 문구, 평가 데이터 |
| Notion 설계 문서의 새 역할 반영 책임/시점 | Project_06 저장소 README 및 책임 맵은 새 역할 반영; 나머지 링크 대상 문서는 과거 역할 표현이 포함된 것으로 보임 | Notion 담당자의 공용 페이지 갱신/확인 |
| Project_07 결과명/필드/status/evidence envelope | 아래 제안만 있음 | adapter, versioning, 실패/결측 의미 |
| `PlanningDraft` nesting, 콘셉트 다중성, MD 검토 필드 | 내부 `ProductConceptDraft`만 존재 | serializer와 최종 판단 경계 |

## Project_07 전달 모델 제안 (합의 전)

```text
SalesMarketDataResult (proposed; name and fields TBD)
- schema_version, request_id, agent_id, status
- summary, findings
- sales observations and/or market findings
- evidence: source, locator, period/as-of, geography, channel, product mapping
- units, currency, metric definitions and calculation references
- limitations, missing data, errors, follow-up questions
```

입력별 상태/제한과 Evidence 참조는 초안에 보존한다. 판매 0은 근거 있는 관측값이고, `no_results`는 조건에 맞는 결과 없음, `error`는 조회 실패, 권한 부족은 별도 원인, ID mapping failure와 기간·채널·단위·통화 정의 충돌은 unresolved constraint다. 결과 이름, 상태 상세, 필드와 운송 방식은 양 담당자의 합의 전 미확정이다.

## 참조

- [Notion VOGUE(유행)](https://app.notion.com/p/40d3269b1acd80b78989d62024105d4d)
- [Notion Project Workflow](https://app.notion.com/p/40f3269b1acd81378143f35b599ef9a0)
- [Notion Team & Responsibilities](https://app.notion.com/p/40d3269b1acd81f881fac5798ffbe201)
- [Notion 저장소 분리 협업 가이드](https://app.notion.com/p/40e3269b1acd81489fecc1052e033b54)
- [Notion GitHub Workflow](https://app.notion.com/p/40d3269b1acd81a88e21f6c534604e70)
- [`implementation-roadmap.md`](implementation-roadmap.md)
- [`trend-batch-kg-rag-product-planning.md`](trend-batch-kg-rag-product-planning.md)
- [`adr-0001-provisional-implementation-defaults.md`](../decisions/adr-0001-provisional-implementation-defaults.md)
