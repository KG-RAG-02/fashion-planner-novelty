# Agent 3 책임 경계 및 현재 구현 대조

- 상태: Notion과 저장소 간 정렬을 위한 작업 문서. 팀의 공통 계약이나 새 범위 승인이 아님
- 기준일: 2026-11-06
- 대상 저장소: `KG-RAG-02/new-product-planning-agent` (`project_06`)

## 목적

이 저장소는 VOGUE의 3번 **New Product Research Agent**를 구현한다. 이 문서는 Notion의 역할 정의와 현재 코드·문서가 같은 범위를 가리키는지 대조하고, 기존 기능을 보존하면서 다음 개발의 책임 경계를 명확히 한다.

Notion VOGUE 및 관련 Workflow/협업 페이지는 조회 당시 `unverified` 상태였다. 따라서 아래 내용은 현황 대조이며, 충돌이 있는 항목을 새로 승인된 정책으로 간주하지 않는다.

## Notion에서 확인한 업무 경계

| 단계 | 담당 | 이 저장소와의 관계 |
| --- | --- | --- |
| 1 | Query & Trend Agent | 요청 조건 정리와 트렌드 자료 검색·근거 반환. 이 저장소는 결과를 입력으로 소비한다. |
| 2 | Product & Inventory Agent | 자사 상품과 현재 재고 조회. 이 저장소는 결과를 입력으로 소비한다. |
| 3 | New Product Research Agent | 입력 근거를 바탕으로 새 상품 기회와 콘셉트를 제안한다. 이 저장소의 책임이다. |
| 4 | Market Research / Product Feasibility Agent | 3번과 공통 입력을 사용해 병렬 조사한다. 상세 범위와 자료원은 별도 합의 대상이다. |
| 5 | Draft Generation & MD Review Agent | 3·4번 결과를 통합해 검토용 기획안과 검토 기록을 만든다. |

3번과 4번은 1·2번의 공통 입력 이후 병렬 실행하며, 어느 한쪽의 완료도 다른 쪽의 시작 조건이 아니다. 상품 채택·가격·수량·발주·최종안은 MD가 결정한다.

## 현재 코드·문서 현황

| 영역 | 현재 구현/문서 | 책임 분류와 안전한 처리 |
| --- | --- | --- |
| 입력 정규화·컨텍스트 | `PlanningRequest`, `TrendResult`, `InventoryProductResult`를 핵심 입력으로 받고 Evidence/status/충돌을 보존. `SalesAnalysisResult`는 선택형 로컬 확장. | #3의 도메인 입력 정합성은 핵심 책임. 내부 모델은 공통 wire 계약이 아니다. |
| 기회 분석·콘셉트 초안 | `domain/analysis.py`, `domain/concept.py`, `domain/generator.py`, `workflows/planning.py`. 결정적 기준선과 내부 `ProductConceptDraft`가 있음. | #3의 핵심. Evidence 기반 관찰·해석·제안·가설·미확정을 분리하고, 공통 `ProductConcept` adapter는 팀 계약 합의 후 연결한다. |
| H&M Kaggle 분석 | `sources/hm/`의 로컬 수집·품질 점검·과거 판매 집계와 별도 UI. ADR 및 구현 로드맵은 이를 사용자가 추가 확인한 범위라고 기록. | 이미 구현된 과거 데이터 분석이므로 보존한다. 운영 판매 연결·미래 수요로 확장하지 않는다. Notion MVP 범위와의 충돌은 팀 결정이 필요하다. |
| TrendBatch/Evaluator | `domain/trend_batch.py`, `domain/trend_evaluator.py`, `workflows/trend_planning.py`가 batch 입력, taxonomy 매핑, Evidence 확인, 카테고리 적합성 평가를 수행함. | raw trend 검색·정의·taxonomy 원천 관리·GraphRAG는 #1 경계와 겹친다. 후보 상품 카테고리에 대한 적용 가능성 평가는 #3의 일부가 될 수 있다. 정확한 분할 전까지 내부/실험 workflow로 유지하고 공통 TrendResult 대신 사용하지 않는다. |
| KG/RAG 및 상품 데이터 포트 | `domain/retrieval.py`, `domain/candidates.py`에 지식·상품·판매·재고 조회 인터페이스와 fixture가 있음. 운영 연결은 미구현. | trend index/retrieval은 #1, 상품·현재 재고 원천은 #2 소유. #3은 전달된 근거와 결과를 소비한다. 이 포트가 필요한 경우 승인된 adapter 경계와 소유자를 먼저 정한다. |
| 점수화·TOP 5 | 후보 점수·구성요소·다양성 selector가 있으며 점수 정책은 fixture/설정형 heuristic으로 문서화됨. | #3의 검토 보조 순위로 합의될 수 있지만 승인된 MD 기준이 아니다. 시장 트렌드 순위·수요 예측·최종 상품 선택처럼 표현하지 않는다. 점수 기준 승인 전에는 운영 판단으로 사용하지 않는다. |
| 로컬 UI·기획서·MD 검토 | `prototype/`, `web/prototype/`, SQLite가 브리프·시안·검토 흐름을 보여줌. | 로컬 프로토타입/검토 UX다. #5의 공통 초안 생성·검토 API나 운영 서비스 계약으로 간주하지 않는다. 기존 시연 흐름은 보존한다. |
| 이미지 프롬프트·생성 | `workflows/image_generation.py`와 프로토타입 폼. 설정 활성화와 호출별 확인이 필요함. | 콘셉트 검토를 위한 선택형 보조 산출물이다. 상품 사양·Evidence·MD 승인으로 취급하지 않으며 자동 호출하지 않는다. |

## 확인된 불일치 및 미결정 사항

1. **판매 분석 범위:** Notion 저장소 분리 협업 가이드는 판매량 분석을 MVP에서 제외한다고 적는다. 반면 로컬 ADR은 H&M Kaggle 과거 분석이 추가 확인된 저장소 범위라고 기록한다. 내부 코드에서는 이를 선택형 로컬 확장으로 분리했지만, 해당 자료를 통합 에이전트 결과에 노출할지 여부는 팀 합의가 필요하다.
2. **TrendBatch 책임:** Notion의 공통 흐름은 #1이 `TrendResult`를 전달하고 #3이 이를 소비하는 형태다. 현재 TrendBatch workflow는 batch validation·trend taxonomy/근거 평가를 거쳐 후보 선택까지 수행한다. 입력 어댑터 검증, 트렌드 자체 평가, 상품 카테고리 적용 평가는 분리 경계가 필요하다.
3. **상품·판매·재고 조회 소유권:** 현재 내부 retrieval 포트가 여러 데이터를 함께 다룬다. Notion에서는 자사 카탈로그·현재 재고가 #2 책임이며 trend retrieval은 #1 책임이다. 실제 원천 소유권과 읽기 권한은 확인되지 않았다.
4. **점수 및 결과 개수:** TrendBatch 문서의 TOP 5와 heuristic 점수는 로컬 설계/fixture다. 승인된 팀 평가 기준이나 공통 출력 계약으로 확정되지 않았다.
5. **초안·시안·검토:** 로컬 프로토타입은 #5 단계처럼 보이는 기능을 시연하지만, 별도 공통 API나 다른 에이전트의 구현으로 통합되지 않았다.

## 다음 개발에서 적용할 안전한 기본 경계

- #3의 핵심 경로는 공통 입력 후보인 `PlanningRequest`, `TrendResult`, `InventoryProductResult`를 바탕으로 Evidence 기반 `ProductConceptDraft`를 생성하는 것이다.
- `SalesAnalysisResult`는 현재 구현된 H&M 과거 분석의 선택형 로컬 입력이다. 세 핵심 입력만으로도 컨텍스트와 검토용 초안을 만들 수 있으며, 판매 근거를 사용하지 않은 상태를 표시한다. 이 입력을 공통 계약에 포함할지는 별도 팀 합의가 필요하다.
- TrendBatch 실험은 별도 내부 경로로 유지한다. #1이 소유하는 원천 trend search와 taxonomy를 복제하지 않고, #3이 필요한 category-application 검토와 구분한다.
- #3은 #4의 시장성 조사 또는 #5의 최종 기획안 통합 완료를 기다리지 않는다. #3 출력은 독립적으로 전달 가능한 상태·근거·제한을 포함한다.
- 미승인 점수, 합성 fixture, Kaggle 과거 자료, 운영 데이터의 경계를 표시한다. 미조회·결측을 0으로 바꾸지 않는다.
- 사용자 변경사항, `.env`, `data/`, 로컬 SQLite 및 생성 파일을 보존한다. 기능 소유권 조정은 문서화와 adapter 경계부터 시작하고, 기존 구현 이동·삭제는 별도 검토 없이 하지 않는다.

## 후속 팀 결정이 필요한 항목

| 결정 | 현재 상태 | 결정 영향 |
| --- | --- | --- |
| H&M 과거 판매 관찰을 #3 로컬 분석에 선택적으로 사용할지, 통합 MVP 결과에서 제외할지 | Notion 지침과 로컬 ADR/README 사이에 범위 차이가 있음 | 공통 결과에 판매 Evidence를 포함할지와 평가 범위 |
| TrendBatch validator·taxonomy 매핑·Trend × Category 평가의 #1/#3 분할 | 내부 workflow에 구현됐으나 공통 `TrendResult`와 분리 필요 | 모듈 소유권, 입력 adapter, 평가 책임 |
| 상품/판매/재고 query 포트의 데이터 소유자와 허용 범위 | 운영 DB 연결 없음 | adapter 및 입력 contract |
| 후보 점수와 TOP 5의 MD 승인 기준 | 현재 heuristic/fixture | 사용 여부, 해석 문구, 평가 데이터 |
| `ProductConcept` 공통 schema와 #5 핸드오프 | 미합의·내부 `ProductConceptDraft`만 존재 | serializer, 공통 버전, 저장소 간 호환성 |

## 참조

- [Notion VOGUE(유행)](https://app.notion.com/p/40d3269b1acd80b78989d62024105d4d)
- [Notion Project Workflow](https://app.notion.com/p/40f3269b1acd81378143f35b599ef9a0)
- [Notion Team & Responsibilities](https://app.notion.com/p/40d3269b1acd81f881fac5798ffbe201)
- [Notion 저장소 분리 협업 가이드](https://app.notion.com/p/40e3269b1acd81489fecc1052e033b54)
- [Notion GitHub Workflow](https://app.notion.com/p/40d3269b1acd81a88e21f6c534604e70)
- [`implementation-roadmap.md`](implementation-roadmap.md)
- [`trend-batch-kg-rag-product-planning.md`](trend-batch-kg-rag-product-planning.md)
- [`adr-0001-provisional-implementation-defaults.md`](../decisions/adr-0001-provisional-implementation-defaults.md)
