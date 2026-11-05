# New Product Planning Agent 설계 제안

- 상태: 내부 구현 기준 · 공통 계약/transport 미확정
- 작성 목적: 3번 New Product Planning Agent의 구현 경계와 계약 공백을 명확히 하고, 자료에 근거한 LLM 생성 및 복수 엔진 비교 목표를 팀과 검토합니다.
- 적용 범위: `KG-RAG-02/new-product-planning-agent` 저장소
- 후속 Product Feasibility Agent: 별도 신규 저장소에서 구현하기로 합의했으며, 이 저장소에는 포함하지 않습니다.
- 구현 상태: 입력 정합성 검사, 컨텍스트 조립, 출처 검증과 결정적 규칙 기반 초안 생성기가 임시 기본값으로 추가되었습니다. 공통 wire schema와 API 어댑터는 미정입니다.

## 1. 확정 요구사항

이 에이전트는 VOGUE 5단계 흐름 중 3단계입니다. 입력으로 앞 단계 결과를 받아 새 상품 콘셉트를 제안하고, 다음 단계가 검토할 수 있도록 근거와 불확실성을 보존합니다.

| 구분 | 책임 |
| --- | --- |
| 입력 | 필수 H&M 판매 분석 `SalesAnalysisResult`, `TrendResult`, `PlanningRequest`, `InventoryProductResult` |
| 내부 출력 | `ProductConceptDraft`; 공통 `ProductConcept` adapter는 합의 후 연결 |
| 수행 | H&M Kaggle 자료의 로컬 수집·정제·판매 실적 집계, 입력 정합성 확인, 자사 상품·실적 관계와 기회 분석, RAG 근거 기반 콘셉트 생성, claim-level Evidence 연결 및 복수 생성 엔진 평가 |
| 보존 | `request_id`, 계약 버전, 입력 상태, Evidence 참조, 누락·불일치·제약 |
| 제외 | 트렌드 원천 검색/인덱스, 실시간 상품·재고 API 소유, 경쟁상품 조사, 원가·마진/생산·조달/고객 피드백 분석, 최종 기획안 렌더링·MD 승인 기록 |

H&M 거래 집계는 데이터의 기간·채널·단위와 출처가 있는 과거 관찰로 사용합니다. 관측된 판매 패턴만으로 미래 수요나 인과적 고객 니즈를 단정하지 않습니다. 근거 없는 고객 니즈는 가설로, 미입력 가격대·소재·핏은 미정으로 표시합니다. 재고 스냅샷은 수요나 판매 추세와 구분하며, 상품 채택·가격·발주·외부 공개를 결정하거나 실행하지 않습니다.

## 2. 처리 흐름

```text
SalesAnalysisResult + TrendResult + PlanningRequest + InventoryProductResult
  → 네 입력의 구조·요청 ID·계약 버전·상태 검증
  → H&M 상품·거래 데이터 manifest 및 집계 Evidence 로드
  → request_id 및 입력 계약 버전 정합성 확인
  → 시즌·시장·채널·카테고리·요청 속성 정합성 확인
  → 입력 상태와 Evidence 참조 보존
  → 1순위 판매 관찰 분석
  → 2순위 트렌드 Evidence 연결
  → 3순위 쿼리 조건을 반영하고 충돌을 표시
  → 4순위 자사 상품·재고 맥락을 보조적으로 참고
  → 기회, 대상 고객/착용 상황 가설, 상품 정의·속성 제안
  → ProductConcept 조립
```

### 정합성 및 부분 결과 처리

- 입력 간 `request_id`가 다르거나 계약 버전이 호환되지 않으면 결과를 섞지 않습니다. 오류를 반환합니다.
- 시즌·시장·카테고리·속성이 다르면 충돌 필드를 기록하고, 충돌을 해소할 수 없는 주장은 콘셉트 근거로 사용하지 않습니다.
- 입력 `partial`은 확보된 정보와 누락 사유를 함께 전달합니다.
- 입력 `no_results`는 데이터 값 0과 구분합니다. 조회 실패, 자료 없음, 실제 0을 재해석하지 않습니다.
- 네 입력은 모두 필수입니다. 판매 분석 결과, 트렌드, 요청, 상품·재고 입력 중 하나가 빠지면 유효 초안으로 가장하지 않고 입력 오류를 반환합니다. 다만 각 입력의 `partial`, `no_results`, `error` 상태는 계약상 가능한 제한 모드로 보존합니다.
- 상품 속성과 재고 수량은 의미를 구분합니다. `InventoryProductResult`는 필수지만 개별 데이터에 재고 수량이 없으면 미확정으로 표시하고 상품 속성만 활용합니다. 수량은 `quantity`, `unit`, `inventory_definition`, `as_of`, Evidence를 함께 확인한 경우에만 스냅샷 사실로 기록합니다.
- 데이터 우선순위는 판매 분석 → 트렌드 → 사용자 쿼리 → 자사 상품·재고입니다. 이는 산술 점수가 아니며, 쿼리 범위를 무시하는 권한도 아닙니다. 충돌은 숨기지 않고 영향받는 주장과 검토 질문을 표시합니다.
- 사용 권한이 확인되지 않은 원문이나 이미지를 추가로 조회·저장·재배포하지 않습니다.
- 각 제안 속성은 사용자 요청, 입력 근거 기반 관찰, 에이전트 제안, 미확정 중 하나로 출처 성격을 표시합니다.

## 3. 모듈 경계 제안

기존 저장소에는 Python 도메인 코어와 `ConceptGenerator` 포트가 있습니다. 아래는 구현 책임의 논리적 분리이며 운영 API·모델 제공자·프레임워크를 확정하는 안이 아닙니다.

| 모듈 | 책임 | 외부 효과 |
| --- | --- | --- |
| 입력 어댑터 | transport에서 입력을 읽고 공통 계약으로 변환 | API 경계에 한정 |
| 계약 검증 | 버전, 공통 envelope, 필수 구조, enum 값 검증 | 없음 |
| 정합성 검사 | 네 입력의 요청·기간·상품 식별·분류 기준 비교 | 없음 |
| 기회 분석 | 판매 관찰을 먼저 정리하고 트렌드 Evidence와 자사 상품/재고 관계를 순서대로 비교 | 없음 |
| Kaggle 데이터 pipeline | H&M competition 원본 수집, 정제, 품질 요약, 기간·article·channel 집계 및 Evidence manifest | 파일 다운로드/로컬 처리. raw data는 Git/외부 전송 금지 |
| 콘셉트 제안기 | 규칙 기반 기준선과 Evidence-grounded LLM 생성기를 같은 포트 뒤에서 실행 | 복수 엔진 비교는 허용 모델·자료 전송 범위 합의 후 실행 |
| 실험 실행기 | 고정된 입력/Evidence를 각 생성 엔진에 재생하고 설정·출력을 기록 | API 키·민감 원문을 기록하지 않음 |
| Evidence 연결기 | 출력의 각 주장·속성에 입력 Evidence ID 연결 | 없음 |
| 응답 조립기 | `ProductConcept`, 상태, 제약, 오류를 공통 envelope로 반환 | 없음 |

도메인 처리부는 원천 파일을 수정하지 않습니다. Kaggle 원본은 로컬 불변 입력으로 보관하며, 정제·집계는 별도 source adapter에서 수행합니다. 실시간 운영 API·재고 조회는 구현하지 않습니다.

## 4. `ProductConcept` 계약 초안

아래는 현재 Workflow의 개념 예시를 정리한 제안입니다. **합의된 스키마가 아니며**, 구현에서 그대로 확정하지 않습니다.

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

### 스키마에 대한 계약 검토 항목

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
| API 전송 | 임시 기본값: 순수 함수 경계, 네트워크 호출 없음 | HTTP/gRPC/메시지 큐 결정 후 얇은 transport adapter 추가 |
| 모델/외부 API | 현재 기본값: 호출하지 않음. 엔진/제공자 미선정 | 평가 대상 엔진, 권한·자료 처리·자격 증명 관리 합의 후 adapter로 연결 |
| 상태 저장 | 임시 기본값: 무상태 처리, 원천/결과 저장 없음 | 재현·이력 요구와 보존/삭제/접근 통제가 합의되면 별도 저장 어댑터 추가 |

이 임시 구현은 팀 통합 시 `internal models → agreed ProductConcept schema` 변환 경계에서 계약 차이를 흡수하도록 둡니다. 통합 시 내부 모델 자체를 공통 wire schema라고 간주하지 않습니다. 다섯 저장소에 공통 계약 파일을 반영하기로 한 Notion 결정을 따르며, 이 저장소 단독으로 `contracts/` 기준본을 만들지 않습니다.

## 7. 구현 진행 현황

현재 `src/vogue_npp/context.py`는 이미 정규화된 내부 입력 모델 세 개를 받아 다음을 처리합니다.

- `request_id`와 `schema_version`의 동일성 검증
- 각 입력의 `agent_id` 존재와 알려지지 않은 상태값 검사. 하나의 에이전트가 `PlanningRequest`와 `TrendResult`를 함께 반환할 수 있으므로 상태는 입력 종류별로 기록
- 요청·트렌드·상품/재고의 시즌·카테고리·시장·채널 값 및 요청 속성 충돌 기록
- 각 입력 슬롯(`planning_request`, `trend_result`, `inventory_product_result`)별 상태, 제한사항, 누락 필드 질문, Evidence ID를 보존한 `ProductPlanningContext` 조립. 같은 에이전트가 첫 두 입력을 생성해도 허용
- 원문 쿼리와 입력 필드 출처, 요청 제약을 내부 모델에서 보존하고 초안 결과에 요청 제약을 전달

`src/vogue_npp/analysis.py`는 요청 조건과 일치하고 Evidence가 연결된 트렌드 속성을 Evidence가 연결된 자사 상품 속성과 비교합니다. 비교값이 같거나 다르다는 사실을 기록하고 MD 확인 질문을 붙일 뿐, 이를 수요·시장 공백·차별화 성공으로 해석하지 않습니다. 카탈로그 완전성이 정해지지 않아 결과에 없는 속성을 실제 부재로 단정하지 않습니다. `src/vogue_npp/concept.py`에는 내부 검토 초안 모델 및 출처 안전 검사기가 있고, `src/vogue_npp/generator.py`의 `ConceptGenerator` 포트 뒤에 결정적 규칙 기반 구현체를 둡니다. 요청 속성은 사용자 요청으로, Evidence가 있는 트렌드 속성은 관찰로, 근거가 빠진 후보는 검증 대상으로 표시합니다. 자사 상품과 재고 관계는 참조용 관찰로만 기록하며, 명시된 실제 재고 0도 수요·판매 추세로 해석하지 않습니다. 입력별 상태, 입력 충돌, Evidence ID와 제한사항도 초안에 보존합니다. 요청 ID, 알 수 없는 Evidence ID, Evidence 없는 관찰 주장, 미확정으로 표시하면서 값을 단정하는 경우, 요청되지 않은 속성을 사용자 입력으로 표시하는 경우 등을 검사합니다. 이 검사는 입력 권한, 최신성, 의미적 근거 타당성까지 판정하지 않습니다.

이 모듈은 JSON wire payload를 직접 파싱하거나 공통 계약을 직렬화하지 않습니다. 상품 수요를 예측하거나 재고를 순위화하지도 않습니다. 생성기는 다음 단계의 사람이 검토할 출발 초안이며, 제안 품질은 실제 승인된 샘플과 평가 기준을 확보한 뒤 측정해야 합니다.

불일치 검사는 요청 속성 값이 트렌드/재고 결과에 존재하는 값 집합과 서로 겹치는지 확인하는 보수적 경고입니다. 값이 없다는 사실만으로 충돌을 만들지 않습니다. 실제 상품 ID 매핑, 기간·단위 호환성, 속성 용어 표준화는 공통 계약과 입력 데이터 정의가 확정된 후 추가해야 합니다.

## 8. MVP 인수 기준

- 계약 버전, 요청 ID, 상태를 검증하거나 검증 불가 사유를 명확히 반환합니다.
- 네 입력의 조건 불일치와 부분 상태를 숨기지 않습니다.
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
