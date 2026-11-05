# New Product Planning Agent 설계 제안

- 상태: Proposed
- 작성 목적: 3번 New Product Planning Agent의 구현 경계와 계약 공백을 명확히 해 팀 검토를 받습니다.
- 적용 범위: `KG-RAG-02/new-product-planning-agent` 저장소
- 후속 Product Feasibility Agent: 별도 신규 저장소에서 구현하기로 합의했으며, 이 저장소에는 포함하지 않습니다.
- 구현 상태: 내부 입력 정합성 검사와 컨텍스트 조립 코어가 프로토타입으로 추가되었습니다. 공통 wire schema, 생성기, API 어댑터는 미정입니다.

## 1. 확정 요구사항

이 에이전트는 VOGUE 5단계 흐름 중 3단계입니다. 입력으로 앞 단계 결과를 받아 새 상품 콘셉트를 제안하고, 다음 단계가 검토할 수 있도록 근거와 불확실성을 보존합니다.

| 구분 | 책임 |
| --- | --- |
| 입력 | `PlanningRequest`, `TrendResult`, `InventoryProductResult` |
| 출력 | `ProductConcept` |
| 수행 | 입력 정합성 확인, 기존 자사 상품과의 중복·보완 검토, 기획 기회와 상품 콘셉트·속성 제안, 근거 연결 |
| 보존 | `request_id`, 계약 버전, 입력 상태, Evidence 참조, 누락·불일치·제약 |
| 제외 | 트렌드 검색/인덱스, 상품·재고 원천 조회, 판매량 분석, 경쟁상품 조사, 원가·마진/생산·조달/고객 피드백 분석, 최종 기획안 렌더링·MD 승인 기록 |

근거 없는 고객 니즈는 가설로 표시합니다. 미입력 가격대·고객·소재·핏은 사실처럼 채우지 않습니다. 재고 스냅샷을 수요나 판매 추세로 해석하지 않으며, 상품 채택·가격·발주·외부 공개를 결정하거나 실행하지 않습니다.

## 2. 처리 흐름

```text
PlanningRequest + TrendResult + InventoryProductResult
  → 계약/필수 필드 검증
  → request_id 및 입력 계약 버전 정합성 확인
  → 시즌·시장·채널·카테고리·속성 정합성 확인
  → 입력 상태와 Evidence 참조 보존
  → 트렌드 근거와 자사 상품·현재 재고의 관계 분석
  → 기회, 대상 고객/착용 상황 가설, 상품 정의·속성 제안
  → ProductConcept 조립
```

### 정합성 및 부분 결과 처리

- 입력 간 `request_id`가 다르거나 계약 버전이 호환되지 않으면 결과를 섞지 않습니다. 오류를 반환합니다.
- 시즌·시장·카테고리·속성이 다르면 충돌 필드를 기록하고, 충돌을 해소할 수 없는 주장은 콘셉트 근거로 사용하지 않습니다.
- 입력 `partial`은 확보된 정보와 누락 사유를 함께 전달합니다.
- 입력 `no_results`는 데이터 값 0과 구분합니다. 조회 실패, 자료 없음, 실제 0을 재해석하지 않습니다.
- 사용 권한이 확인되지 않은 원문이나 이미지를 추가로 조회·저장·재배포하지 않습니다.
- 각 제안 속성은 사용자 요청, 입력 근거 기반 관찰, 에이전트 제안, 미확정 중 하나로 출처 성격을 표시합니다.

## 3. 모듈 경계 제안

기술 스택과 기존 파일 구조가 아직 없습니다. 아래는 구현 책임의 논리적 분리이며 디렉터리·언어·프레임워크를 확정하는 안이 아닙니다.

| 모듈 | 책임 | 외부 효과 |
| --- | --- | --- |
| 입력 어댑터 | transport에서 입력을 읽고 공통 계약으로 변환 | API 경계에 한정 |
| 계약 검증 | 버전, 공통 envelope, 필수 구조, enum 값 검증 | 없음 |
| 정합성 검사 | 세 입력의 요청·기간·상품 식별·분류 기준 비교 | 없음 |
| 기회 분석 | 트렌드 Evidence와 자사 상품/재고 근거에서 관찰 가능한 관계 정리 | 없음 |
| 콘셉트 제안기 | 제안 생성. LLM 도입 시 공급자 추상화 뒤에서 사용 | 외부 모델 호출은 별도 선택·승인 필요 |
| Evidence 연결기 | 출력의 각 주장·속성에 입력 Evidence ID 연결 | 없음 |
| 응답 조립기 | `ProductConcept`, 상태, 제약, 오류를 공통 envelope로 반환 | 없음 |

도메인 처리부는 입력을 수정하거나 원천 시스템에 쓰기 요청을 보내지 않는 순수 처리로 유지합니다. 저장소·모델·검색·API 어댑터는 결정 후 연결합니다.

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

현재 저장소에는 언어, 런타임, 프레임워크, 의존성, CI, 실행 설정이 없습니다. 내부 컨텍스트 코어의 동작 경계를 보여주기 위해 표준 라이브러리만 사용하는 Python 프로토타입을 추가했으며, 이를 서비스 구현 스택으로 확정한 것은 아닙니다.

| 결정 | 후보/질문 | 영향 |
| --- | --- | --- |
| 언어·런타임 | Python, TypeScript 등 팀 표준 확인 | 모델 SDK, 검증 도구, 배포와 연동 |
| 계약 검증 | JSON Schema 또는 언어별 검증 라이브러리 | 여러 저장소에서 일관된 검증 가능성 |
| 생성 방식 | 규칙 기반, LLM 구조화 출력, 또는 단계적 조합 | 설명 가능성, 품질 평가, 비용·지연 |
| API 전송 | HTTP, gRPC, 메시지 큐 등 | 호출 경계와 운영 방식; 현재 Notion API Design에서 TBD |
| 모델/외부 API | 제공자·모델·권한·데이터 처리 조건 미정 | 민감 데이터 전송, 비용, 재현성 |
| 상태 저장 | 무상태 처리 우선 여부와 저장 필요성 | 재현성, 보존·삭제·접근 통제 |

추천: 먼저 팀의 기존 언어·배포 표준을 확인하고, 도메인 로직과 외부 모델 호출을 분리합니다. 스택 결정 후에 API·모델 어댑터를 추가합니다. Python 프로토타입은 이 경계를 검토하기 위한 안이며 확정 결정이 아닙니다.

## 7. 구현 진행 현황

현재 `src/vogue_npp/context.py`는 이미 정규화된 내부 입력 모델 세 개를 받아 다음을 처리합니다.

- `request_id`와 `schema_version`의 동일성 검증
- upstream `agent_id` 중복과 알려지지 않은 상태값 검사
- 요청·트렌드·상품/재고의 시즌·카테고리·시장 값 충돌 기록
- 각 단계 상태, 제한사항, 누락 필드 질문, Evidence ID를 보존한 `ProductPlanningContext` 조립

이 모듈은 JSON wire payload를 직접 파싱하지 않고 공통 계약을 직렬화하지 않습니다. 상품 아이디어를 생성하거나 재고를 순위화하지도 않습니다. 이를 위해서는 먼저 공통 계약과 생성기 방식이 합의되어야 합니다.

## 8. MVP 인수 기준

- 계약 버전, 요청 ID, 상태를 검증하거나 검증 불가 사유를 명확히 반환합니다.
- 세 입력의 조건 불일치와 부분 상태를 숨기지 않습니다.
- 유효한 입력에서 `ProductConcept`를 구성하고 핵심 주장마다 Evidence 또는 명시적 가설·미확정 표기를 연결합니다.
- 사용자 요청, 근거 기반 관찰, 제안, 가설, 미확정을 구분합니다.
- 판매량·경쟁상품 분석과 원가·생산·조달·고객 반응 분석을 수행하지 않습니다.
- 가격·발주·최종 채택·외부 공개를 자동으로 실행하지 않습니다.
- 예제 요청·응답은 샘플임을 명시하고 실제 데이터를 가장하지 않습니다.

## 9. 구현 전 팀 합의가 필요한 항목

1. 다섯 에이전트의 공통 계약 저장소별 동기화 책임자와 변경 반영 절차
2. `ProductConcept`와 공통 envelope의 정확한 nesting 및 필수 필드
3. 속성·기회·근거 분류 enum과 다중 콘셉트 허용 여부
4. 팀 표준 언어/런타임 및 서비스 실행·배포 방식
5. LLM을 도입할지, 도입한다면 허용 모델·데이터 전송 범위·평가 기준
6. 입력 중 하나가 `no_results`일 때 결과를 계속 생성할지에 대한 정책

## 참고 문서

- [Project Overview](https://app.notion.com/p/40d3269b1acd809c98c5dc5de4f61d24)
- [Project Workflow](https://app.notion.com/p/40f3269b1acd81378143f35b599ef9a0)
- [저장소 분리 협업 가이드](https://app.notion.com/p/40e3269b1acd81489fecc1052e033b54)
- [API Design](https://app.notion.com/p/40d3269b1acd818bb6eaecb6d1db5f8b)
- [Architecture & Technical Design](https://app.notion.com/p/40d3269b1acd81b8b16fce9010a37a5e)
- [Data & Knowledge](https://app.notion.com/p/40d3269b1acd81a28e69c991870f7fbd)
- [Experiments & Evaluation](https://app.notion.com/p/40d3269b1acd81ac80eae832d87226bd)
