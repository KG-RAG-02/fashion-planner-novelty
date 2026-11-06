# New Product Planning Agent 입력·출력 처리 흐름

- 상태: 내부 구현 설계 · 공통 wire 계약/에이전트 API 미확정
- 범위: VOGUE 3번 New Product Planning Agent

## 입력 우선순위

네 입력은 모두 필수다. 우선순위는 점수나 가중합이 아니라 콘셉트 분석에서 근거를 검토하는 순서다. 트렌드 근거로 방향을 파악한 뒤 요청 조건으로 적용 범위를 확인하고, 판매 관찰과 자사 상품·재고를 보조 맥락으로 검토한다. 입력 간 불일치는 숨기거나 임의로 해소하지 않는다. 특히 트렌드 우선순위가 사용자 요청 조건을 무시할 권한을 주지는 않는다. 충돌 시 두 값을 보존하고 확인 질문을 남긴다.

| 순위 | 입력 | 담당 | 처리 역할 |
| --- | --- | --- | --- |
| 1 | 트렌드 (`TrendResult`) | Query & Trend Agent | 근거가 연결된 트렌드명과 속성을 콘셉트 방향의 첫 검토 기준으로 제공한다. 판매량이나 미래 수요의 증명으로 해석하지 않는다. |
| 2 | 사용자 요청 (`PlanningRequest`) | Query & Trend Agent | 시즌·카테고리·지역·채널·요청 속성·제약으로 트렌드의 적용 범위를 확인한다. 트렌드와 충돌하면 둘 다 보존하고 확인 질문을 남긴다. |
| 3 | H&M 판매 분석 (`SalesAnalysisResult`) | 3번 에이전트 로컬 파이프라인 | 요청 범위에 명시적으로 매핑된 과거 구매 집계와 상품 속성을 보조 근거로 검토한다. 판매 수치는 결정적 코드로 계산하며 미래 수요로 해석하지 않는다. |
| 4 | 자사 상품·재고 (`InventoryProductResult`) | Product & Inventory Agent | 자사 구색과 기준 시점 재고를 마지막 보조 맥락으로 검토한다. 단독으로 판매/수요를 설명하지 않는다. |

트렌드는 콘셉트 방향의 첫 근거이고, 요청은 그 방향이 적용될 상품·시즌 범위를 정한다. 요청과 트렌드 속성이 충돌하면 어느 한쪽으로 자동 변경하지 않는다. 판매는 방향을 확정하거나 뒤집는 점수가 아니라 과거 관찰이며, 재고는 마지막 보조 맥락이다. 재고가 높거나 낮아도 순위나 산술 점수로 기회·성공률을 만들지 않는다. 다만 요청 상품과 재고 상품의 분류가 다른 것만으로 즉시 충돌 처리하지 않는다. 내부의 버전 지정 상·하의 분류 규칙으로 코디 보완 관계가 명확한 경우에는 재고 사실과 별도인 코디 기획 제안으로 남긴다.

## 처리 단계

1. **수신:** H&M 판매 집계를 내부 `SalesAnalysisResult`로 만들고, `TrendResult`, `PlanningRequest`, `InventoryProductResult`를 모두 받는다. 공개/공통 transport adapter는 계약 합의 후 연결한다.
2. **검증:** 네 입력의 구조, 요청 ID, schema version, 상태값을 확인한다. 필수 입력이 빠졌거나 요청/버전이 다르면 함께 섞지 않는다.
3. **정규화:** 내부 `PlanningInputs`와 `ProductPlanningContext`로 바꾸고 슬롯별 상태·제한·Evidence를 보존한다. 원본 입력을 덮어쓰지 않는다.
4. **트렌드 우선 검토:** 근거가 연결된 후보명과 속성을 먼저 정리한다. 후보 상태, Evidence, 시즌·카테고리·지역·채널을 함께 보존한다.
5. **요청 범위 확인:** 시즌·카테고리·요청 속성·제약을 기준으로 트렌드 적용 가능성을 확인한다. 충돌은 임의로 해소하지 않고 확인 질문으로 남긴다.
6. **판매 보조 분석:** 처리된 H&M Style 판매 자료 중 요청 카테고리에 명시적으로 매핑된 행만 검토한다. 집계 기간·구매 행 수·상품 속성·출처 버전을 기록하고, 과거 관찰을 미래 수요로 해석하지 않는다.
7. **재고 보조 맥락:** 자사 상품과 재고를 마지막으로 검토한다. SKU/수량/단위/기준 시점/Evidence가 제공되면 그 재고 주장에 연결한다. 요청 대상(예: 상의)과 재고 상품(예: 청바지/하의)은 서로 다른 상품으로 유지한다. `outfit-role-pairing-v1` 역할 규칙이 상·하의 보완 관계를 식별하면 별도 코디 제안으로 기록하며, 해당 규칙은 수요·스타일 선호·재고 소진 효과의 Evidence가 아니다. 역할을 알 수 없거나 관계가 애매하면 불일치를 임의 해소하지 않고 질문으로 남긴다.
8. **콘셉트 및 출력 검증:** 내부 `ProductConceptDraft`를 만들고 사실/해석/가설/제안/미확정을 나눈다. 핵심 주장 Evidence ID가 입력 allowlist에 있는지 확인한다. 판매 수치 계산은 분석 코드에서 수행하고 LLM에 맡기지 않는다.

## 내부 모델 매핑

현재 내부 필드 이름은 공통 계약의 확정 필드명이 아니다. 계약이 확정되면 adapter에서 매핑한다.

| 내부 모델 | 전달받은 값 | 확인 사항 |
| --- | --- | --- |
| `SalesAnalysisResult` | `result`, `observations[]`: mapped category, product code/group, purchase rows, period, source/evidence IDs, catalog attributes, category-mapping version | H&M style aggregate adapter는 요청 ID/version과 버전이 지정된 source-category map을 받는다. 데이터에 시즌이 없어 시즌을 추정하지 않는다. 적용 가능한 카테고리 행이 없으면 `no_results`로 반환한다. |
| `TrendResult` | `result`, `candidates[]` 및 후보의 분류 차원·속성·Evidence | 트렌드의 출처·기준일은 Evidence 메타데이터에서 보존한다. 판매량/미래 수요 증명으로 승격하지 않는다. |
| `PlanningRequest` | `result`, `original_query`, `season`, `market`, `channel`, `category`, 선택적 `product_role`, `requested_attributes`, `missing_fields`, `constraints`, `field_origins` | `product_role`은 내부 상/하의 역할 정규화 필드다. 공통 계약 필드로 가정하지 않으며 transport adapter에서 upstream과 매핑 협의가 필요하다. 대상 고객·목표 가격대 등은 계속 미결정으로 기록한다. |
| `InventoryProductResult` | `result`, `products[]` | 각 상품에 선택적 `product_role`, 비정형 `note`/`note_origin` 및 기존 상품·재고 필드를 보존한다. `quantity`, `unit`, `inventory_definition`, `as_of` 누락은 상위 status와 제한사항에 남기며, 메모만으로 수량을 만들지 않는다. |
| `ProductConceptDraft` | 요청 조건, 속성, 기회 관찰, 자사 상품 관계, 상태, 제한, 질문, Evidence ID | 내부 검토 출력이다. 합의 전 공통 `ProductConcept` wire payload로 부르지 않는다. |

## 실제 데이터 필드 계약과 현재 연결 상태

이 표는 저장소 내부 adapter 계약이다. 각 upstream 팀과 합의한 외부 wire schema가 아니므로 API 필드명으로 복사하지 않는다.

| 흐름 | 내부 필드/식별자 | 버전·기준 시점 | 누락·충돌 처리 | 현재 연결 |
| --- | --- | --- | --- | --- |
| 기획 요청 | `request_id`, `schema_version`, `original_query`, `season`, `market[]`, `channel[]`, `category`, 선택적 `product_role`, `requested_attributes[]`, `constraints[]`, `missing_fields[]`, `field_origins{}` | request별 식별자·schema version 필수 | 미입력 값은 `None`/빈 값과 `missing_fields`로 보존; taxonomy 임의 변환 금지 | 내부 dataclass; 외부 transport 미연결 |
| 트렌드 | `AgentResult` + `TrendCandidate{name, qualification, season, market[], channel[], category, attributes[], evidence_ids[]}` | 공급자 결과의 schema version 및 각 Evidence의 문서 버전/기준일 | `no_results`, `partial`, `error`를 값 0/부재 사실로 치환하지 않음 | 내부 dataclass; Agent 1 연결 미확정 |
| 판매 | `SalesObservation{category, purchase_rows, period_start/end, product_group, attributes[], source_channel_code, evidence_ids[]}` | Kaggle manifest `pipeline_version`, 원천 SHA-256, 관측기간; 매핑 버전은 호출자가 전달 | 미매칭 article은 제한사항으로 알림; 원천 분류와 요청 taxonomy 명시 map 없이는 결과를 매핑하지 않음 | 로컬 Article 집계 adapter |
| 상품·재고 | `InventoryProduct{style_id, sku_ids[], season, category, product_role, note, note_origin, market[], channel[], quantity, unit, inventory_definition, as_of, evidence_ids[]}` | 스냅샷 `as_of`, upstream schema version; 역할 매핑 규칙 `outfit-role-pairing-v1` | 속성과 수량 결측을 구분; 실제 0만 0으로 유지; 단위/정의 충돌은 결합하지 않음. 카테고리가 다른 상·하의는 규칙 매핑이 명확할 때만 별도 코디 관계로 보존 | 내부 dataclass; Agent 2 연결 미확정 |
| 콘셉트 초안 | `ProductConceptDraft` 및 claim별 `kind`, `evidence_ids[]`, 상태·제약 | request/schema version, source Evidence IDs | 미근거 사실은 검증 오류; 해석·가설·제안·미확정으로 낮추거나 제거 | 결정적 generator 연결; LLM adapter 미연결 |

### H&M 판매 adapter의 집계 경계

`load_hm_sales_analysis()`는 `weekly_sales_by_article_channel.csv`의 `article_id`를 `article_catalog.csv`의 `article_id`와 결합하고, 실제 article의 `product_group_name`·`product_type_name` 분류로 요청 category에 매핑한 뒤 기간 전체 구매 행을 합산한다. 한 product_code의 article이 여러 상품유형에 연결되면 각 article을 해당 유형에 귀속한다. 스타일 대표값 파일을 카테고리 집계 원천으로 사용하지 않는다. 기본값은 관측을 자르지 않으며 `observation_limit`을 명시한 경우 반환 관측이 일부로 제한되었다는 제한사항을 결과에 추가한다.

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
| 카테고리는 다르나 상·하의 역할이 확인됨 | `outfit-role-pairing-v1`과 역할 분류 출처를 남기고 코디 제안으로 연결한다. 상품별 재고 사실은 별도 claim으로 보존하며, 역할이 애매하면 기존 충돌 질문을 유지한다. |

## 책임 경계와 미결정 사항

이 에이전트는 경쟁상품 조사, 원가·마진 산정, 생산·조달 판단, 고객 피드백 분석, 최종 기획안 렌더링·MD 승인을 수행하지 않는다. H&M 판매 파이프라인은 판매 관찰 입력을 제공하지만, 현재 웹 데모의 합성 브리프와 자동 병합하지 않는다.

아직 정해야 하는 사항은 공통 요청·응답 스키마의 필드명과 버전, Evidence 구조, status/error 매핑, API 전송 방식, 재고 신선도 기준, 요청에 포함될 대상 고객·목표 가격대 필드다. 결정 전까지 내부 모델을 저장소 간 표준으로 간주하지 않는다.
