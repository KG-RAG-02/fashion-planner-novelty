# Project_06 Planning Agent 설계 제안

> **현행 HTTP 경계:** 이 문서의 transport 미합의 표기는 과거 설계 상태입니다. 현재 Project_06 `/v1/agents/new-product-agent/runs` 계약과 실행 포트는 [HTTP handoff v0.2](../../contracts/http-handoff-v0.2.md) 및 [저장소 경계 문서](../repository-boundaries.md)를 기준으로 합니다.

- 상태: 경계 설계 제안 · 실제 코드 소유권은 2026-11-06 책임 경계 기록에 따라 판매 분석을 Project_07로 이전
- 작성 목적: Project_06 Planning Agent 경계와 Project_07 handoff 후보를 명확히 합니다.
- 적용 범위: `KG-RAG-02/new-product-planning-agent` 저장소 (현재 연결 remote)
- Project_07 저장소명은 `market-research-agent`로 확인됨. 판매 결과의 공통 wire 계약과 운영 자료원은 여전히 미확정입니다. transport는 HTTP/JSON을 설계 기준안으로 제안하지만 팀 확정 결정은 아닙니다.
- 현재 책임 기준: Project_06은 새상품 기획만 담당합니다. 과거 H&M/synthetic 판매 분석 코드는 Project_07에 이관되었고, 본 문서 내 과거 판매 처리 설명은 현행 책임이 아닙니다. 자세한 현재 상태는 [책임 경계 기록](agent-3-responsibility-map.md)을 기준으로 합니다.

> **읽기 주의:** 본 문서에는 이전 설계안의 일부 표와 설명이 이력 보존을 위해 남아 있습니다. 특히 Project_06이 H&M/Kaggle 판매 pipeline을 소유한다는 제안은 폐기되었습니다. 현행 코드의 근거로는 사용하지 말고 위 책임 경계 기록과 README를 따르세요.

## 1. 확정 요구사항

이 에이전트는 VOGUE 5단계 흐름 중 3단계입니다. 입력으로 앞 단계 결과를 받아 새 상품 콘셉트를 제안하고, 다음 단계가 검토할 수 있도록 근거와 불확실성을 보존합니다.

| 구분 | 책임 |
| --- | --- |
| 입력 | 사용자 요청을 담은 `PlanningRequest`, `TrendResult`, `InventoryProductResult`, Project_07 판매·시장 조사 결과 |
| 내부 출력 | 제안명 `PlanningDraft`; 기존 `ProductConceptDraft`는 현재 내부 호환 모델이며 콘셉트는 초안 내부 요소 |
| 수행 | 입력 정합성 확인, 전달 자료 기반 기회 분석, 콘셉트·근거 통합 기획안 작성, claim/attribute/proposal-level Evidence 연결, MD 검토 지원 |
| 보존 | `request_id`, 계약 버전, 입력 상태, Evidence 참조, 누락·불일치·제약 |
| 제외 | 판매 원천 조회·분석 소유, 시장자료 원천 조회·분석 소유, 트렌드 검색, 실시간 상품·재고 API 소유, 자동 확정/발주 |

H&M 거래 집계는 데이터의 기간·채널·단위와 출처가 있는 과거 관찰로 사용합니다. 관측된 판매 패턴만으로 미래 수요나 인과적 고객 니즈를 단정하지 않습니다. 근거 없는 고객 니즈는 가설로, 미입력 가격대·소재·핏은 미정으로 표시합니다. 재고 스냅샷은 수요나 판매 추세와 구분하며, 상품 채택·가격·발주·외부 공개를 결정하거나 실행하지 않습니다.

## 2. 처리 흐름

```text
PlanningRequest + TrendResult + InventoryProductResult + Project_07 Sales & Market Data result
  → 세 핵심 입력의 구조·요청 ID·계약 버전·상태 검증
  → Project_07 결과가 전달되면 출처·기간·단위·정의·매핑·상태 검증
  → request_id 및 입력 계약 버전 정합성 확인
  → 시즌·시장·채널·카테고리·요청 속성 정합성 확인
  → 입력 상태와 Evidence 참조 보존
  → 1순위 트렌드 Evidence로 콘셉트 방향 검토
  → 2순위 쿼리 조건으로 적용 범위 확인 및 충돌 표시
  → Project_07 판매·시장 관찰을 제한이 명시된 보조 근거로 검토
  → 4순위 자사 상품·재고 맥락을 마지막 보조 근거로 검토
  → 기회, 대상 고객/착용 상황 가설, 상품 정의·속성 제안
  → 콘셉트를 구성요소로 포함한 PlanningDraft 작성 → MD 검토
```

### 정합성 및 부분 결과 처리

- 입력 간 `request_id`가 다르거나 계약 버전이 호환되지 않으면 결과를 섞지 않습니다. 오류를 반환합니다.
- 시즌·시장·속성이 다르면 충돌 필드를 기록하고, 충돌을 해소할 수 없는 주장은 콘셉트 근거로 사용하지 않습니다. 요청 상품과 재고 상품의 카테고리가 다르더라도 내부 `outfit-role-pairing-v1` 규칙이 상·하의 코디 보완 관계를 명확히 찾으면 재고 상품을 요청 상품으로 병합하지 않고 별도의 코디 제안으로 기록합니다. 역할 분류가 없거나 애매하면 기존처럼 충돌/확인 질문을 남깁니다.
- 입력 `partial`은 확보된 정보와 누락 사유를 함께 전달합니다.
- 입력 `no_results`는 데이터 값 0과 구분합니다. 조회 실패, 자료 없음, 실제 0을 재해석하지 않습니다.
- Project_07 결과가 미제공이면 판매 관찰을 생성하지 않고 `not_provided`로 구분합니다. 실제 판매량 0, 조건에 맞는 자료 없음(`no_results`), 조회 실패/timeout(`error`), 권한 부족, 상품 ID 매핑 실패 및 정의 불일치를 서로 구별합니다.
- 현행 HTTP 초안 생성 API에서는 `sales_market_result` 객체를 필수로 받습니다. Project_07이 정상 실행됐지만 분석 결과를 찾지 못한 경우 `status: "no_results"` 객체를 전달하고, 요청 누락·`null`은 입력 오류입니다. 이 필수화는 Project_07의 상세 필드 계약을 확정하거나 opaque payload를 해석할 수 있도록 허용하지 않습니다.
- `partial/no_results/error`, 입력별 누락·충돌·제한, Evidence ID, 기간, 단위, 통화 및 지표 정의를 기획안 초안에 보존합니다. 이름과 구체 필드는 팀 합의 전 제안입니다.
- 판매 관측은 미래 수요·고객 선호·시장 성장 증거가 아닙니다. 재고 스냅샷은 판매 추세 대리값이 아닙니다. 출처/기간/정의/단위가 없으면 숫자를 추정하지 않습니다.
- 상품 속성과 재고 수량은 의미를 구분합니다. `InventoryProductResult`는 필수지만 개별 데이터에 재고 수량이 없으면 미확정으로 표시하고 상품 속성만 활용합니다. 수량은 `quantity`, `unit`, `inventory_definition`, `as_of`, Evidence를 함께 확인한 경우에만 스냅샷 사실로 기록합니다.
- 코디 목적의 내부 역할 정규화는 `PlanningRequest.product_role`, `InventoryProduct.product_role`, 또는 명확한 상/하의 상품 분류 문구를 사용할 수 있습니다. `outfit-role-pairing-v1`은 상의와 하의를 분리해 코디 후보로 연결할 뿐, 수요·선호·재고 소진 효과를 입증하지 않습니다. Upstream adapter에서 역할/메모 필드를 전달할 수 있는지와 분류 용어를 담당자와 합의해야 하며, 이 내부 필드들을 공통 wire contract로 간주하지 않습니다.
- 처리 순서는 Query & Trend → Product & Inventory → Project_07 Sales & Market Data → Project_06 Planning입니다. 이 순서는 앞 단계의 실패나 미제공을 사실로 대체하지 않습니다.
- 사용 권한이 확인되지 않은 원문이나 이미지를 추가로 조회·저장·재배포하지 않습니다.
- 각 제안 속성은 사용자 요청, 입력 근거 기반 관찰, 에이전트 제안, 미확정 중 하나로 출처 성격을 표시합니다.

## 3. 모듈 경계 제안

기존 저장소에는 Python 도메인 코어와 `ConceptGenerator` 포트가 있습니다. 아래는 구현 책임의 논리적 분리이며 운영 API·모델 제공자·프레임워크를 확정하는 안이 아닙니다.

| 모듈 | 책임 | 외부 효과 |
| --- | --- | --- |
| 입력 어댑터 | transport에서 입력을 읽고 공통 계약으로 변환 | API 경계에 한정 |
| 계약 검증 | 버전, 공통 envelope, 필수 구조, enum 값 검증 | 없음 |
| 정합성 검사 | 세 핵심 입력의 요청·분류 기준 비교. 선택 판매 확장이 있으면 기간·상품 식별·분류도 확인 | 없음 |
| 기회 분석 | 트렌드 Evidence로 방향을 검토하고 요청 범위를 확인한 뒤 자사 상품/재고 관계를 비교. 선택 판매 관찰은 추가 맥락 | 없음 |
| Kaggle 데이터 pipeline (폐기된 과거 제안) | 과거 초안에서 Project_06에 배정했으나 현재 Project_07 책임으로 이관됨 | 현행 Project_06 구현 범위가 아님 |
| 콘셉트 제안기 | 규칙 기반 기준선과 Evidence-grounded LLM 생성기를 같은 포트 뒤에서 실행 | 복수 엔진 비교는 허용 모델·자료 전송 범위 합의 후 실행 |
| 실험 실행기 | 고정된 입력/Evidence를 각 생성 엔진에 재생하고 설정·출력을 기록 | API 키·민감 원문을 기록하지 않음 |
| Evidence 연결기 | 출력의 각 주장·속성에 입력 Evidence ID 연결 | 없음 |
| 응답 조립기 | `ProductConcept`, 상태, 제약, 오류를 공통 envelope로 반환 | 없음 |

도메인 처리부는 원천 파일을 수정하지 않습니다. Kaggle 원본은 로컬 불변 입력으로 보관하며, 정제·집계는 별도 source adapter에서 수행합니다. 실시간 운영 API·재고 조회는 구현하지 않습니다.

## 4. `ProductConcept` 계약 초안

아래는 이름부터 합의 전인 의미 제안입니다. **공용 wire schema나 운영 계약이 아닙니다.**

`SalesMarketDataResult (proposed)`는 `schema_version`, `request_id`, `agent_id`, `status`, `summary`, `findings`, 판매 관측 및/또는 시장 결과, Evidence(`source`, `locator`, 기간/as-of, 지역, 채널, 상품 매핑), 단위·통화·metric 정의·계산 참조, 제한·결측·오류·후속 질문을 포함할 수 있습니다. 해당 의미를 유지하는 임시 내부 호환 필드를 도메인에 두었으나 필드명과 envelope는 담당자 합의가 필요합니다.

`PlanningDraft` 역시 제안명입니다. 기존 `ProductConceptDraft` 내부 모델은 이행 중 유지되며, 공용 출력 serializer/nesting은 확정하지 않습니다. `PlanningDraft`에는 하나 이상의 콘셉트 요소, 근거 주장·속성·제안별 Evidence ID, 상태 및 입력별 제한이 포함되어야 합니다.

```json
{
  "schema_version": "1.0",
  "request_id": "req_example",
  "agent_id": "new-product-planning-agent",
  "status": "partial",
  "summary": "제안의 간단한 요약",
  "findings": {
    "concept_id": "concept_example",
    "season": null,
    "category": null,
    "opportunity": {
      "statement": "검토할 기회",
      "kind": "hypothesis",
      "evidence_ids": []
    },
    "target_customer": {
      "value": null,
      "kind": "unknown",
      "evidence_ids": []
    },
    "product_definition": {
      "description": "상품 콘셉트 설명",
      "attributes": [
        {
          "name": "color",
          "value": null,
          "kind": "user_requested",
          "evidence_ids": []
        }
      ]
    },
    "relation_to_own_products": [],
    "differentiation": [],
    "risks": [],
    "questions_for_validation": []
  },
  "evidence": [],
  "limitations": [],
  "errors": []
}
```

### Project_07 / 공용 스키마 합의 항목

1. Workflow 예시는 `ProductConcept` 도메인 객체 형태지만 공통 envelope 예시의 `findings`·`evidence` 위치와 완전히 정렬되어 있지 않습니다. 출력 nesting을 먼저 합의해야 합니다.
2. 최상위 `evidence_ids`와 공통 `evidence` 배열 중 어느 표현을 사용할지, 중복 참조를 어떻게 피할지 정해야 합니다.
3. 필수/선택/null 허용 필드, `kind` enum, `status`와 오류 코드, 다중 콘셉트 허용 여부가 미확정입니다.
4. Evidence ID의 namespace 규칙, 입력 단계 Evidence를 그대로 참조하는 방식, 출력 주장별 참조 강도를 정해야 합니다.
5. 속성 이름의 표준 용어집과 시즌·시장·카테고리 정규화 규칙이 필요합니다.

계약 변경은 이 저장소 단독으로 확정할 수 없습니다. 공통 계약 파일을 사용하는 각 담당자와 같은 경로·버전·내용으로 반영하는 절차를 합의한 뒤 적용해야 합니다. 별도 `vogue-contracts` 저장소는 만들지 않습니다.

## 5. 실패·제한 처리

| 조건 | 제안 동작 |
| --- | --- |
| 잘못된 입력 구조/필수 envelope 누락 | `error`; 안전한 오류 코드와 `request_id` 가능한 경우 보존 |
| request ID 또는 계약 버전 충돌 | 결과 결합 중단; 충돌 정보 기록 |
| 트렌드 자료 없음 | 입력의 `no_results` 유지; 자사 상품 자료가 유효하면 그 근거만으로 제한적 결과 가능 여부를 정책으로 합의 |
| 자사 상품·재고 결과 없음 | 입력 상태 보존; 실제 0으로 대체하지 않음 |
| 일부 입력만 있음 | `partial`; 실제 근거가 있는 제안만 생성하고 누락·한계 기재 |
| 근거 간 충돌 | 임의 선택 금지; 충돌을 제한사항/검증 질문으로 표시 |
| Evidence를 연결할 수 없는 생성 주장 | 사실 주장으로 출력하지 않음; 제거하거나 가설/미확정으로 표시 |

외부 모델을 사용한다면 모델 오류와 입력 오류를 구분하고, 자동 재시도·timeout·개인정보 전송 기준은 모델·전송 설계가 합의된 후 정합니다.

## 6. 미확정 기술 선택과 대안

팀 결정을 기다리지 않고 도메인 작업을 이어가기 위해 아래 기본값을 임시 적용했습니다. 상세 결정·대안·통합 시 교체 경계는 [임시 구현 기본값 ADR](../decisions/adr-0001-provisional-implementation-defaults.md)에 기록합니다. 이는 팀 전체의 공통 계약이나 운영 스택 합의가 아닙니다.

| 결정 | 후보/질문 | 영향 |
| --- | --- | --- |
| 언어·런타임 | 임시 기본값: Python 표준 라이브러리 기반 도메인 코어 | 팀 표준과 다르면 도메인 계층을 이전하거나 어댑터를 재작성 |
| 계약 검증 | 임시 기본값: 내부 dataclass 검증. 공통 JSON Schema/wire validator는 미작성 | 필드·envelope 합의 후 저장소별 동일 계약 파일과 어댑터 추가 |
| 생성 방식 | 현재 기준선: 투명한 결정적 규칙. 목표: 근거 기반 LLM 생성 및 복수 엔진 비교 | 허용 엔진·자료 전송·평가 기준을 정한 뒤 같은 generator 포트에 어댑터 연결 |
| API 전송 | 구현 기본값: 순수 함수 경계, 네트워크 호출 없음. 설계 제안 기준안은 HTTP/JSON이며 팀 미합의 | 승인된 공통 계약과 transport 결정 후 얇은 adapter 추가; 제안은 [HTTP/API 연동 부록](project-07-handoff-proposal.md#httpapi-연동-부록-제안-미합의) 참조 |
| 모델/외부 API | 현재 기본값: 호출하지 않음. 엔진/제공자 미선정 | 평가 대상 엔진, 권한·자료 처리·자격 증명 관리 합의 후 adapter로 연결 |
| 상태 저장 | 임시 기본값: 무상태 처리, 원천/결과 저장 없음 | 재현·이력 요구와 보존/삭제/접근 통제가 합의되면 별도 저장 어댑터 추가 |

이 임시 구현은 팀 통합 시 `internal models → agreed ProductConcept schema` 변환 경계에서 계약 차이를 흡수하도록 둡니다. 통합 시 내부 모델 자체를 공통 wire schema라고 간주하지 않습니다. 다섯 저장소에 공통 계약 파일을 반영하기로 한 Notion 결정을 따르며, 이 저장소 단독으로 `contracts/` 기준본을 만들지 않습니다.

### HTTP/API 연동 부록 (제안, 미합의)

현재 설계 기준안은 API Design 페이지의 제안에 따라 HTTP/JSON입니다. 이는 팀의 transport 확정이나 승인된 wire/운영 계약을 의미하지 않습니다. 공통 envelope는 `POST /v1/agents/{agent_id}/runs` 요청/응답 JSON body에 담는 안이며, producer의 원본 결과는 응답 `result` 아래 보존합니다. `contract_version`은 envelope 계약 버전, 각 producer의 `schema_version`은 해당 agent가 소유하는 payload 버전입니다. agent는 자체 schema와 로컬 payload를 유지하고, orchestrator는 순서·호출·호환성 검증 및 원본 결과 보존을 담당하는 안입니다.

API Design의 제안값은 연결 timeout 3초, agent 호출 전체 timeout 60초, 연결 실패 및 HTTP 429/502/503/504에 최대 1회 추가 시도(429는 `Retry-After` 존중), `Idempotency-Key: {request_id}:{agent_id}`입니다. 이 값들은 검토 시작점이며 승인 전까지 모두 TBD입니다. 자동 재시도는 idempotency 동작 합의가 전제이고, 해당 합의 전에는 비활성화가 안전 기본값이라는 제안입니다. 인증은 서비스 간 TLS와 Bearer token(OAuth 2.0 client credentials) 후보입니다. 토큰 발급자·audience/scope·키 회전, 실제 서비스 주소, 운영 재시도, 배포 토폴로지 및 동기/비동기 운영은 TBD이며 별도 승인 전 구현 확정 사항으로 다루지 않습니다. 상세 항목은 [Project_07 handoff 부록](project-07-handoff-proposal.md#httpapi-연동-부록-제안-미합의) 및 [API Design](https://app.notion.com/p/40d3269b1acd818bb6eaecb6d1db5f8b)을 참조합니다.

## 7. 구현 진행 현황

프롬프트 인젝션과 모델 경계 현황은 [기획안 생성 프롬프트 인젝션 경계](prompt-injection-boundary.md)에 기록합니다. 운영 API는 기본적으로 결정적 규칙 기반을 사용합니다. `VOGUE_TEXT_GENERATION_ENABLED`와 주입형 provider 경계를 둔 버전 관리 구조화 텍스트 프롬프트를 추가했지만, 제공자·모델·자료 전송이 승인되지 않아 실제 텍스트 LLM은 연결되지 않았습니다. 플래그만 켜면 규칙 기반 초안과 비가용 상태를 반환합니다. 실제 외부 모델 경로는 명시적으로 활성화·요청한 이미지 생성입니다.

현재 `src/vogue_npp/domain/context.py`는 이미 정규화된 내부 입력 모델 세 개를 받아 다음을 처리합니다.

- `request_id`와 `schema_version`의 동일성 검증
- 각 입력의 `agent_id` 존재와 알려지지 않은 상태값 검사. 하나의 에이전트가 `PlanningRequest`와 `TrendResult`를 함께 반환할 수 있으므로 상태는 입력 종류별로 기록
- 요청·트렌드·상품/재고의 시즌·카테고리·시장·채널 값 및 요청 속성 충돌 기록
- 각 입력 슬롯(`planning_request`, `trend_result`, `inventory_product_result`)별 상태, 제한사항, 누락 필드 질문, Evidence ID를 보존한 `ProductPlanningContext` 조립. 같은 에이전트가 첫 두 입력을 생성해도 허용
- 원문 쿼리와 입력 필드 출처, 요청 제약을 내부 모델에서 보존하고 초안 결과에 요청 제약을 전달

`src/vogue_npp/domain/analysis.py`는 요청 조건과 일치하고 Evidence가 연결된 트렌드 속성을 Evidence가 연결된 자사 상품 속성과 비교합니다. 비교값이 같거나 다르다는 사실을 기록하고 MD 확인 질문을 붙일 뿐, 이를 수요·시장 공백·차별화 성공으로 해석하지 않습니다. 카탈로그 완전성이 정해지지 않아 결과에 없는 속성을 실제 부재로 단정하지 않습니다. `src/vogue_npp/domain/concept.py`에는 내부 검토 초안 모델 및 출처 안전 검사기가 있고, `src/vogue_npp/domain/generator.py`의 `ConceptGenerator` 포트 뒤에 결정적 규칙 기반 구현체를 둡니다. 요청 속성은 사용자 요청으로, Evidence가 있는 트렌드 속성은 관찰로, 근거가 빠진 후보는 검증 대상으로 표시합니다. 자사 상품과 재고 관계는 참조용 관찰로만 기록하며, 명시된 실제 재고 0도 수요·판매 추세로 해석하지 않습니다. 입력별 상태, 입력 충돌, Evidence ID와 제한사항도 초안에 보존합니다. 요청 ID, 알 수 없는 Evidence ID, Evidence 없는 관찰 주장, 미확정으로 표시하면서 값을 단정하는 경우, 요청되지 않은 속성을 사용자 입력으로 표시하는 경우 등을 검사합니다. 이 검사는 입력 권한, 최신성, 의미적 근거 타당성까지 판정하지 않습니다.

이 모듈은 JSON wire payload를 직접 파싱하거나 공통 계약을 직렬화하지 않습니다. 상품 수요를 예측하거나 재고를 순위화하지도 않습니다. 생성기는 다음 단계의 사람이 검토할 출발 초안이며, 제안 품질은 실제 승인된 샘플과 평가 기준을 확보한 뒤 측정해야 합니다.

불일치 검사는 요청 속성 값이 트렌드/재고 결과에 존재하는 값 집합과 서로 겹치는지 확인하는 보수적 경고입니다. 값이 없다는 사실만으로 충돌을 만들지 않습니다. 실제 상품 ID 매핑, 기간·단위 호환성, 속성 용어 표준화는 공통 계약과 입력 데이터 정의가 확정된 후 추가해야 합니다.

## 8. MVP 인수 기준

- 계약 버전, 요청 ID, 상태를 검증하거나 검증 불가 사유를 명확히 반환합니다.
- 세 핵심 입력의 조건 불일치와 부분 상태를 숨기지 않습니다. 선택 판매 확장의 상태도 구분합니다.
- 유효한 입력에서 내부 콘셉트 초안을 구성하고 핵심 주장마다 Evidence 또는 명시적 제안·미확정 표기를 연결합니다.
- 사용자 요청, 근거 기반 관찰, 제안, 가설, 미확정을 구분합니다.
- 판매량·경쟁상품 분석과 원가·생산·조달·고객 반응 분석을 수행하지 않습니다.
- 가격·발주·최종 채택·외부 공개를 자동으로 실행하지 않습니다.
- 예제 요청·응답은 샘플임을 명시하고 실제 데이터를 가장하지 않습니다.

## 9. 구현 전 팀 합의가 필요한 항목

1. 다섯 에이전트의 공통 계약 파일 동기화 책임자와 변경 반영 절차
2. `ProductConcept`와 공통 envelope의 정확한 nesting 및 필수 필드
3. 속성·기회·근거 분류 enum과 다중 콘셉트 허용 여부
4. 팀 표준 언어/런타임 및 서비스 실행·배포 방식
5. 복수 엔진 평가에 사용할 허용 모델·자료 전송 범위·자격 증명 관리 방식
6. 비교 지표, 최소 근거성/제약 준수 기준, MD 평가 루브릭·검토자
7. 입력 중 하나가 `no_results`일 때 결과를 계속 생성할지에 대한 정책

## 참고 문서

- [Project Overview](https://app.notion.com/p/40d3269b1acd809c98c5dc5de4f61d24)
- [Project Workflow](https://app.notion.com/p/40f3269b1acd81378143f35b599ef9a0)
- [저장소 분리 협업 가이드](https://app.notion.com/p/40e3269b1acd81489fecc1052e033b54)
- [API Design](https://app.notion.com/p/40d3269b1acd818bb6eaecb6d1db5f8b)
- [Architecture & Technical Design](https://app.notion.com/p/40d3269b1acd81b8b16fce9010a37a5e)
- [Data & Knowledge](https://app.notion.com/p/40d3269b1acd81a28e69c991870f7fbd)
- [Experiments & Evaluation](https://app.notion.com/p/40d3269b1acd81ac80eae832d87226bd)
