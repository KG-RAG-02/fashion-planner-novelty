# P06 구조화 상품 초안 설계

상태: P06 내부 구현 완료. Project_08 소비자와의 별도 검토 및 P06/P07 공통 wire contract 합의는 남아 있다.

## 목적

P06 초안의 설명문에서 상품 속성을 추측해 P07로 보내지 않는다. 초안은 MD가 읽는 서술형 기획 내용과 시스템이 전달·검증하는 구조화 상품 프로필을 함께 가진다. P07 adapter는 구조화 프로필만 읽고 P07이 허용한 필드만 전달한다.

## 현재 출력과 한계

현재 `ProductConceptDraft`는 `category`, `season`, 서술형 `product_definition`, `attributes[]` 등을 반환한다. `category`와 `season`은 정형 필드지만 상품 종류, 성별, 소재는 항상 별도 필드로 생성되지 않는다. P07 adapter가 `attributes[]`에서 이름이 일치하는 값을 찾아 보완하는 방식은 속성 이름이 달라지거나 서술문에만 값이 있을 때 누락을 일으킨다.

## 제안 구조

기존 초안 필드는 유지하고 `ProductConceptDraft.product_profile`을 추가했다. 각 값은 값 자체와 출처/확실성을 함께 담는다.

```json
{
  "product_profile": {
    "category": {"value": "men-shorts", "kind": "user_requested", "evidence_ids": []},
    "product_type": {"value": "shorts", "kind": "user_requested", "evidence_ids": []},
    "gender": {"value": "men", "kind": "user_requested", "evidence_ids": []},
    "season": {"value": "S/S", "kind": "user_requested", "evidence_ids": []},
    "material": {"value": null, "kind": "unknown", "evidence_ids": []}
  }
}
```

필드 의미:

| 필드 | 필수성 | 생성·검증 규칙 |
| --- | --- | --- |
| `category` | 필수 | 검증된 PlanningRequest 카테고리를 복사한다. 없으면 초안 생성 또는 P07 사후 검토를 유효한 입력 부족으로 표시한다. |
| `product_type` | 선택 | 명시된 요청/상품 taxonomy 또는 근거가 있는 상품 종류만 기록한다. category 문자열을 임의 분해하지 않는다. |
| `gender` | 선택 | `women`, `men`, `unisex`, `unknown`, `null`만 허용한다. 명시 입력 또는 버전 관리 taxonomy mapping으로만 설정한다. |
| `season` | 선택 | 검증된 PlanningRequest 시즌을 복사한다. |
| `material` | 선택 | 명시 입력, 상품 근거 또는 기획 제안으로 분류한다. 제안값은 근거 관측값처럼 표시하지 않는다. |

`kind`는 기존 claim 종류를 재사용한다. 규칙 기반 입력 정규화에서 미확정은 `unknown`, `value=null`로 표현한다. `evidence_ids`는 현재 입력에서 검증된 ID만 허용한다. `proposal`은 검토용 제안이며 사실 단정이 아니다. 세부 디자인 항목은 이름이 있는 attribute claim으로 표현한다.

## 입력과 생성 규칙

1. 요청에서 category/season, 사용자가 명시한 구조화 속성을 먼저 넣는다. 규칙 기반 생성기의 기획 attributes에서 모호하지 않은 상품 속성과 시각 제안을 프로필로 투영한다.
2. LLM 생성은 새 v6 strict JSON Schema로 프로필을 초안과 함께 반환한다. 로컬 검증기가 타입, gender enum, `kind`/`value` 관계, 요청 ID, Evidence ID allowlist 및 category/season 일치를 재검증한다.
3. 규칙 기반 fallback도 같은 `ProductProfile` 모델을 생성한다. 값을 확인할 수 없으면 `null`/`unknown`으로 둔다.
4. 입력 충돌은 기존 context conflict로 보존한다. 이미지 워크플로는 draft를 받고 profile 명세를 이미지 프롬프트의 binding spec으로 사용한다. 기존 서술형 product_definition과 attributes를 별도 이미지 사양으로 추가하지 않는다. API는 동일 프로필 객체를 사용했는지 표시하지만, 이미지 provider가 실제 픽셀에서 사양을 지켰는지는 자동 검증하지 않는다.
5. 기존 `attributes[]`와 `product_definition`은 설명용으로 유지한다. P07 전송값의 source of truth는 `product_profile` 하나다.

성별은 자유 텍스트나 창작 제안에서 추론하지 않는다. `men-shorts` 같은 카테고리 ID를 성별로 바꾸려면 승인된 versioned taxonomy mapping이 있어야 하지만 아직 연결되지 않았다. 현재는 요청의 명시적 성별 속성만 쓰며, 그 외에는 `gender.value=null`이다.

## P07 전달 변환

P07의 현재 `vogue-sales-market-review/0.1-proposal` 입력에서는 `planning_draft.product.category`가 필수다. 선택 필드는 `product_type`, `gender`, `season`, `material` 등이다. Project_06은 이 네 선택 필드를 `product_profile`에서만 가져오며, null/unknown/검증 실패 값은 생략한다. `gender`는 P07 enum에 맞는 값만 전달한다. `proposed_price`, `currency`, `costing`, 이미지, Evidence 내부 메타데이터는 이 P06→P07 payload에 넣지 않는다.

```json
{
  "contract_version": "vogue-sales-market-review/0.1-proposal",
  "request_id": "request-123",
  "input": {
    "request_id": "request-123",
    "planning_draft": {
      "schema_version": "1.0",
      "draft_id": "request-123",
      "product": {
        "category": "men-shorts",
        "product_type": "shorts",
        "gender": "men",
        "season": "S/S",
        "material": "cotton blend"
      }
    }
  }
}
```

P07 payload에는 전달 가능한 값만 직렬화한다. 내부 provenance는 P06 초안과 입력 Evidence에 보존하며, P07 schema가 허용하지 않는 필드를 새로 추가하지 않는다.

## 버전·호환성

- P06 API 응답의 기존 `draft` 필드는 유지하고 `draft.product_profile`을 추가했다. 이미지 응답에는 생성에 사용한 `product_specification`, 동일 프로필 사용 여부, 시각 일치가 자동 검증되지 않았다는 상태, `prompt_version`, `prompt_sha256`가 포함된다.
- `schema_version`을 실제 wire contract처럼 올리기 전, Project_08 소비자와 P07 호출 경로의 version handling을 함께 확인한다. 현재 공유 계약이 확정되지 않았으므로 내부 응답 `schema_version=1.0`을 외부 합의 버전으로 해석하지 않는다.
- 구버전 초안에 `product_profile`이 없으면 P07 adapter가 review 전달을 거부한다. 생성된 서술문이나 `attributes[]`를 자동 승격하지 않는다. Project_08은 최신 P06 응답의 `draft.product_profile`을 review proxy에 전달해야 한다.

## 구현 순서

1. 완료: `domain/concept.py`에 typed `ProductProfile`을 추가했다.
2. 완료: rule-based generator와 LLM v6 schema/parser/validator가 같은 모델을 반환한다.
3. 완료: API `draft.product_profile` 및 image `product_specification`을 노출한다.
4. 완료: P07 adapter가 profile만 읽으며 가격·통화·원가·이미지를 보내지 않는다.
5. 생성·검증·이미지·handoff 회귀 테스트를 갱신했다. 전체 suite에는 기존 `PrototypeHandler` import 누락 문제가 별도로 남아 있다.

## 미결정 사항

- 카테고리와 상품 종류의 canonical ID 목록 및 소유자
- 성별 taxonomy mapping의 데이터/버전 책임자
- 소재를 상품 사실, upstream attribute, 또는 기획 proposal 중 어떤 근거로 쓸 수 있는지에 대한 정책
- P06 응답의 `product_profile`과 P07 wire payload를 공식 계약으로 승인할 담당자
