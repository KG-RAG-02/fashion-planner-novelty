# New Product Planning Agent 입력·출력 처리 흐름

- 상태: 내부 구현 설계 · 공통 wire 계약/에이전트 API 미확정
- 범위: VOGUE 3번 New Product Planning Agent

## 입력 우선순위

네 입력은 모두 필수다. 우선순위는 수치 가중합이 아니라 컨셉 생성에서 어떤 근거를 먼저 분석하고 제안의 중심으로 삼는지 정하는 정책이다. 상위 자료에 대한 불일치를 숨기거나 하위 값을 상위 사실로 승격하지 않는다. 판매 관찰이 사용자 요청 범위 밖에 있으면 범위 밖 자료임을 표시하고, 사용자의 카테고리를 무시해 다른 상품을 제안하지 않는다.

| 순위 | 입력 | 담당 | 처리 역할 |
| --- | --- | --- | --- |
| 1 | H&M 판매 분석 (`SalesAnalysisResult`) | 3번 에이전트 로컬 파이프라인 | 요청 카테고리에 명시적으로 매핑된 과거 구매 집계와 상품 속성에서 판매 관찰을 만든다. 판매 수치는 결정적 코드로 계산하며 미래 수요로 해석하지 않는다. |
| 2 | 트렌드 (`TrendResult`) | Query & Trend Agent | 판매 관찰과 비교할 트렌드·속성 근거를 제공한다. 관계·차이·불일치를 Evidence로 보존한다. |
| 3 | 사용자 요청 (`PlanningRequest`) | Query & Trend Agent | 시즌·카테고리·지역·채널·요청 속성·제약을 전달한다. 판매/트렌드 관찰의 증거가 아니며 근거와 충돌하면 충돌을 표시한다. |
| 4 | 자사 상품·재고 (`InventoryProductResult`) | Product & Inventory Agent | 자사 구색과 기준 시점 재고를 보조 맥락으로 제공한다. 네 입력 중 낮은 우선순위이며 단독으로 판매/수요를 설명하지 않는다. |

이 우선순위는 사용자 요청을 벗어난 상품을 생성할 권한이 아니다. 제안은 요청된 기획 범위 안에서 구성하고, 그 안에서 판매 Evidence를 가장 먼저 보고 트렌드 근거를 다음으로 연결한다. 요청 조건이 이를 따르지 않으면 요청을 보존하고 데이터 충돌을 명시한다. 재고가 높거나 낮아도 순위나 산술 점수로 기회·성공률을 만들지 않는다.

## 처리 단계

1. **수신:** H&M 판매 집계를 내부 `SalesAnalysisResult`로 만들고, `TrendResult`, `PlanningRequest`, `InventoryProductResult`를 모두 받는다. 공개/공통 transport adapter는 계약 합의 후 연결한다.
2. **검증:** 네 입력의 구조, 요청 ID, schema version, 상태값을 확인한다. 필수 입력이 빠졌거나 요청/버전이 다르면 함께 섞지 않는다.
3. **정규화:** 내부 `PlanningInputs`와 `ProductPlanningContext`로 바꾸고 슬롯별 상태·제한·Evidence를 보존한다. 원본 입력을 덮어쓰지 않는다.
4. **판매 우선 분석:** 처리된 H&M Style 판매 자료에서 요청 카테고리와 연결된 행만 사용한다. Kaggle 상품 분류와 VOGUE 요청 taxonomy의 mapping이 명시적으로 제공되지 않으면 판매 관찰을 요청 카테고리 근거로 사용하지 않는다. 집계 기간·구매 행 수·상품 속성·출처 버전을 기록한다.
5. **트렌드 비교:** 판매 관찰과 트렌드 속성의 일치·차이·불일치를 비교한다. 이 관계는 관찰 수준이며 인과·미래 수요로 해석하지 않는다.
6. **쿼리 반영:** 시즌·카테고리·요청 속성·제약에 따라 제안 범위를 잡는다. 요청과 상위 판매/트렌드 근거가 다르면 둘 다 보존하고, MD 검토 질문을 만든다.
7. **재고 맥락:** 자사 상품과 재고를 별도 참고 신호로 연결한다. 상품 ID·기간·단위·기준 시점이 맞지 않으면 결합하지 않고, 재고를 수요·인기·판매 속도로 해석하지 않는다.
8. **콘셉트 및 출력 검증:** 내부 `ProductConceptDraft`를 만들고 사실/해석/가설/제안/미확정을 나눈다. 핵심 주장 Evidence ID가 입력 allowlist에 있는지 확인한다. 판매 수치 계산은 분석 코드에서 수행하고 LLM에 맡기지 않는다.

## 내부 모델 매핑

현재 내부 필드 이름은 공통 계약의 확정 필드명이 아니다. 계약이 확정되면 adapter에서 매핑한다.

| 내부 모델 | 전달받은 값 | 확인 사항 |
| --- | --- | --- |
| `SalesAnalysisResult` | `result`, `observations[]`: mapped category, product code/group, purchase rows, period, source/evidence IDs, catalog attributes, category-mapping version | H&M style aggregate adapter는 요청 ID/version과 버전이 지정된 source-category map을 받는다. 데이터에 시즌이 없어 시즌을 추정하지 않는다. 적용 가능한 카테고리 행이 없으면 `no_results`로 반환한다. |
| `TrendResult` | `result`, `candidates[]` 및 후보의 분류 차원·속성·Evidence | 트렌드의 출처·기준일은 Evidence 메타데이터에서 보존한다. 판매량/미래 수요 증명으로 승격하지 않는다. |
| `PlanningRequest` | `result`, `original_query`, `season`, `market`, `channel`, `category`, `requested_attributes`, `missing_fields`, `constraints`, `field_origins` | 대상 고객·목표 가격대 등 내부 모델에 없는 요청 필드는 계약 협의 전 임의로 끼워 넣지 않고 미결정으로 기록한다. |
| `InventoryProductResult` | `result`, `products[]` | 입력 객체는 필수다. 개별 상품의 `quantity`, `unit`, `inventory_definition`, `as_of` 누락은 상위 result status 및 제한사항과 함께 보존한다. |
| `ProductConceptDraft` | 요청 조건, 속성, 기회 관찰, 자사 상품 관계, 상태, 제한, 질문, Evidence ID | 내부 검토 출력이다. 합의 전 공통 `ProductConcept` wire payload로 부르지 않는다. |

## 상태별 동작

| 상황 | 동작 |
| --- | --- |
| 요청 누락/형식 오류 | 입력 오류로 처리하고 조건을 추측하지 않는다. |
| 판매 입력 `no_results` 또는 오류 | 필수 슬롯 상태를 보존하고 판매 근거 주장을 만들지 않는다. 나머지 입력은 계약상 허용하는 제한 모드에서만 쓴다. |
| 트렌드 결과 누락/오류 | 필수 슬롯 상태와 제한을 보존한다. 유효 트렌드 Evidence를 사실 근거로 사용하지 않는다. |
| 트렌드 `partial` | 확인 가능한 Evidence로 범위를 좁혀 제안하고 부분 상태를 보존한다. |
| 트렌드 `no_results` | 결과 없음으로 표시한다. 트렌드가 없다는 사실을 시장에 트렌드가 없다는 뜻으로 바꾸지 않는다. |
| 재고 입력 누락/오류 | 필수 슬롯 입력 오류/상태로 보존하고 재고 근거를 만들지 않는다. |
| 상품 정보 제공, 재고 수량 생략 | 상품 속성 비교는 할 수 있지만 재고 수량은 미확정으로 남기고 조회 한계를 표시한다. |
| 재고 조회 `no_results` | 수량 0으로 치환하지 않는다. 상품 결과에 별도로 제공된 상품 속성만 비교할 수 있다. |
| 실제 수량 0 | 단위·재고 정의·기준 시점·Evidence가 확인되면 조회 시점의 0으로 기록한다. 수요·판매·품절의 의미를 부여하지 않는다. |
| 차원/ID/단위 충돌 | 임의 매핑·환산 없이 충돌과 미사용 사유를 보존한다. |

## 책임 경계와 미결정 사항

이 에이전트는 경쟁상품 조사, 원가·마진 산정, 생산·조달 판단, 고객 피드백 분석, 최종 기획안 렌더링·MD 승인을 수행하지 않는다. H&M 판매 파이프라인은 판매 관찰 입력을 제공하지만, 현재 웹 데모의 합성 브리프와 자동 병합하지 않는다.

아직 정해야 하는 사항은 공통 요청·응답 스키마의 필드명과 버전, Evidence 구조, status/error 매핑, API 전송 방식, 재고 신선도 기준, 요청에 포함될 대상 고객·목표 가격대 필드다. 결정 전까지 내부 모델을 저장소 간 표준으로 간주하지 않는다.
