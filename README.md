# Project_06 — 새상품 기획 에이전트

Project_06(P06)은 요청·트렌드·상품 정보를 분석해 새상품 기획 초안과 신제품 이미지를 생성합니다. Project_08(P08)이 각 에이전트를 호출하고 결과를 통합합니다. P06은 P07을 직접 호출하지 않습니다.

## 전체 흐름

```text
Input → 분석 흐름 → Output

사용자 요청 + Trend 결과 + Stock 결과
  → P08이 P06 `/runs`에 전달
  → P06이 입력·근거·충돌을 검증
  → 하나의 상품 프로필과 콘셉트를 구성
  → 같은 프로필로 기획 초안과 신제품 이미지 생성
  → P06 결과를 P08에 반환
  → P08이 P06 결과를 review bridge에 보내 P07 요청 payload를 받음
  → P08이 P07 호출 및 결과 통합, 기획안 보드 구성
```

P06의 범위는 **기획 초안, 구조화 상품 프로필, 신제품 이미지, P07 요청 payload 변환**입니다. Trend·Stock·P07 호출, 통합 응답, 기획안 보드는 P08이 담당합니다.

## 1. Input

정식 P06 API는 `POST /v1/agents/new-product-agent/runs`입니다. 요청 envelope는 `vogue-handoff/0.3`이며 `input`에는 다음 세 객체를 포함합니다.

| 입력 | 내용 | P06에서의 사용 |
| --- | --- | --- |
| `planning_request` | 요청 ID, 사용자 기획 질문, 카테고리·시즌 등 명시 조건 | 사용자 의도와 명시된 상품 사양의 기준 |
| `trend_result` | Trend 에이전트 결과, 관측값, Evidence | 트렌드 관찰과 기획 근거 |
| `inventory_product_result` | Stock 에이전트의 상품·재고 정보와 Evidence | 참고할 상품 특성 및 재고 맥락 |

세 입력은 같은 `request_id`로 연결합니다. 각 producer의 schema와 Evidence ID를 검증하고 원본 자료를 결과에 보존합니다. 판매·시장 review 결과는 초안과 이미지 생성 입력이 아닙니다. P06은 운영 DB에서 Trend·Stock 정보를 직접 조회하지 않습니다.

```json
{
  "contract_version": "vogue-handoff/0.3",
  "request_id": "planning-001",
  "input": {
    "planning_request": {
      "schema_version": "1.0",
      "request_id": "planning-001",
      "query": "27SS 아우터 기획"
    },
    "trend_result": {
      "schema_version": "1.1",
      "request_id": "planning-001",
      "status": "partial",
      "trends": [],
      "evidence": []
    },
    "inventory_product_result": {
      "schema_version": "1.0",
      "request_id": "planning-001",
      "agent_id": "stock-agent",
      "status": "ok",
      "products": [],
      "evidence": []
    }
  }
}
```

## 2. 분석 흐름

### 입력 검증 및 근거 정리

P06은 요청 ID, 입력 schema, producer 정보와 Evidence 연결을 확인합니다. 원본 Trend·Stock 자료를 보존하고, 누락·오류·충돌은 상태와 제한사항으로 남깁니다. 근거가 없거나 서로 충돌하는 값은 사실처럼 확정하지 않습니다.

### 상품 프로필과 콘셉트 구성

`product_profile`에 카테고리, 상품 종류, 성별, 시즌, 소재 등 초안에 필요한 필드를 값과 출처 종류, Evidence ID와 함께 구조화합니다. 사용자 입력에서 온 값, 근거 관찰, 기획 제안, 미확정 상태를 구분합니다. 미확정 값은 null/unknown으로 둡니다.

이 프로필과 동일한 분석 결과를 기준으로 서술형 기획 초안을 만듭니다. 별도의 후처리 단계에서 초안으로부터 프로필을 역추출하지 않습니다.

### 신제품 이미지 생성

이미지 프롬프트는 기획 초안과 같은 `product_profile`을 사용합니다. 미정인 소재·색상·디테일은 확정 사양으로 추가하지 않도록 제한합니다. 응답에는 이미지 생성 상태와 사용한 사양, 이미지 참조 방법 및 추적 정보가 포함됩니다. 생성된 픽셀이 프로필과 일치하는지는 자동 판정하지 않습니다.

### P07 review 요청 변환

초안 생성이 끝나면 P08이 전체 P06 결과 객체를 P06 review bridge에 전달합니다. `/runs` 응답을 사용하는 경우 바깥 envelope가 아니라 `result` 안의 기획 결과 객체를 bridge의 `planning_draft`로 전달합니다. P06 bridge는 request ID, 카테고리, 상품 프로필과 Evidence ID를 검증한 뒤 P07 0.2 요청 payload를 P08에 반환합니다.

Bridge는 P07을 직접 호출하지 않습니다. P08이 반환된 payload를 P07 `/reviews`에 보내고 review 응답을 통합합니다. P07 payload에는 필수 `category`와 확인된 `product_type`, `gender`, `season`, `material`만 포함됩니다. 가격·통화·원가·이미지·내부 Evidence 메타데이터는 전달하지 않습니다.

## 3. Output

### P06 기획·이미지 결과

`/runs` 응답은 `contract_version`, `request_id`, `producer`, `status`, `result`를 포함합니다. `result`에는 다음 주요 값이 들어갑니다.

| 출력 | 내용 |
| --- | --- |
| `draft` | 서술형 기획 초안, `product_profile`, 질문 및 검토 사항 |
| `image` | 생성 상태, 모델, 이미지 URL, 사용한 상품 사양, 프롬프트 추적 정보 |
| `input_statuses` | 각 입력 producer의 처리 상태 |
| `input_evidence` | 입력 원본 및 관련 Evidence 정보 |
| `limitations`, `conflicts` | 미확정 사항, 입력 한계, 충돌 |

P06의 결과 status는 `ok`, `partial`, `no_results`, `error`일 수 있습니다. 이러한 도메인 결과는 HTTP 200으로 반환되며, 잘못된 요청이나 계약은 오류 HTTP 상태와 코드로 반환됩니다.

### P06 bridge 출력

P06 bridge는 P07 0.2 요청 payload만 반환합니다. 확인된 프로필 필드가 없는 선택 항목은 생략됩니다.

```json
{
  "contract_version": "vogue-sales-market-review/0.2-proposal",
  "request_id": "planning-001",
  "input": {
    "request_id": "planning-001",
    "product": {
      "category": "Outerwear",
      "product_type": "Jacket",
      "season": "winter"
    }
  }
}
```

P06은 P07 응답을 받거나 보존하지 않습니다. 최종 통합 결과와 기획안 보드는 P08의 출력입니다.

## 실행 방법

Python 3.12 이상에서 의존성을 설치하고 로컬 서버를 시작합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt

export VOGUE_HTTP_MODE=local
export VOGUE_AGENT_SERVICE_BEARER_TOKEN='로컬에서 사용할 임의의 비밀값'
PYTHONPATH=src python3 -m vogue_npp.prototype.server
```

서버 주소는 기본 `http://127.0.0.1:8767`입니다. `/runs`와 review bridge는 `Authorization: Bearer <token>` 및 `Content-Type: application/json` 헤더가 필요합니다. `GET /api/health`로 서버 상태를 확인할 수 있습니다.

이미지 provider 호출은 기본 비활성화되어 있습니다. 실제 이미지 생성을 켜려면 `VOGUE_IMAGE_GENERATION_ENABLED=true`와 `LLM_API_KEY` 또는 `OPENAI_API_KEY`를 설정합니다. 구조화 텍스트 생성을 사용하려면 `VOGUE_TEXT_GENERATION_ENABLED=true`도 설정합니다. 비밀값은 `.env` 또는 승인된 비밀 저장소에 두고 Git에 커밋하지 마세요. 선택 기능 설정 이름은 `.env.example`을 참고하세요.

## 테스트 및 상세 문서

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

- [HTTP handoff 계약](contracts/http-handoff-v0.3.md)
- [저장소 책임 경계](docs/repository-boundaries.md)
- [구조화 상품 프로필과 P07 변환](docs/design/p06-structured-planning-draft.md)
- [로컬 실행 안내](docs/design/prototype-runbook.md)
