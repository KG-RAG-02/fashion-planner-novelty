# Project_06 — 신제품 기획 에이전트

Project_06(P06)은 P08이 전달한 사용자 요청, Trend 결과, Stock 결과를 분석해 **신제품 기획 초안과 상품·착장 이미지**를 반환합니다. P06은 Trend·Stock 조회, P07 review 호출, 통합 응답, 기획안 보드를 담당하지 않습니다. 그 호출과 최종 통합은 P08이 담당합니다.

## 입력 → 분석 → 출력

```text
입력
  P08 → P06 POST /v1/agents/new-product-agent/runs
       ├─ planning_request (schema 1.0)
       ├─ trend_result (schema 1.1)
       └─ inventory_product_result (schema 1.0)
       모든 request_id는 요청 envelope의 ID와 같아야 함

분석
  1. envelope·request ID·producer·schema·status 검증
  2. 입력 원본과 provenance 보존
  3. Trend 입력을 내부 분석 형식으로 정규화
  4. 요청·Trend·Stock 근거, 누락, 충돌을 분석해 product_profile과 Draft 작성
  5. 실제 이미지 provider가 설정된 경우 동일 상품 프로필로 product/outfit 이미지 생성
  6. artifact를 저장하고 요청 ID에 소유권을 연결

출력
  P06 → P08에 Draft, product_profile, 입력 provenance,
       validation issues, product/outfit 이미지 상태와 artifact 메타데이터 반환
  P08 → P07 /reviews 호출, 결과 통합 및 기획안 보드 생성
```

## 입력 계약

현재 P08 연동은 `vogue-handoff/0.3`을 사용합니다. `input`에는 아래 세 객체만 허용합니다.

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
      "status": "ok"
    },
    "inventory_product_result": {
      "schema_version": "1.0",
      "request_id": "planning-001",
      "agent_id": "stock-agent",
      "status": "ok"
    }
  }
}
```

지원 schema는 PlanningRequest 1.0, Trend 1.1, Stock 1.0입니다. 각 입력 ID, 허용 producer와 상태를 확인합니다. Trend 1.1은 원본을 보존한 채 내부 분석용 복사본만 정규화합니다. 지원하지 않는 schema, 잘못된 상태, producer 또는 request ID는 요청 오류로 반환합니다.

## 분석 결과와 상태

성공 응답 envelope는 `contract_version`, `request_id`, `producer`, `status`, `result`를 포함합니다. `result.draft`에는 읽을 수 있는 기획 초안, 출처가 구분된 `product_profile`, `visuals.product`, `visuals.outfit`이 들어갑니다. `result.input_evidence`와 `compatibility`에는 입력 원본, provenance, schema 변환 정보가 보존됩니다. `validation_issues`, `limitations`, `conflicts`, `questions_for_validation`에서 결과의 한계와 확인할 사항을 확인할 수 있습니다.

- `ok`: 입력 분석과 요청된 출력이 완료됐습니다.
- `partial`: 입력에 부분 결과·누락·충돌이 있거나 이미지 생성/저장이 완료되지 않았습니다. 구체적인 원인은 `validation_issues`의 코드로 확인합니다.
- 입력 계약 오류는 4xx로 거부됩니다.
- 처리 완료 후 같은 `request_id`를 다른 입력에 재사용하면 `409 REQUEST_ID_REUSED`를 반환합니다. 같은 입력의 동시 요청은 최초 저장된 응답으로 수렴합니다.
- 유료 이미지 요청이 처리 중이거나 결과가 불확실하면 중복 호출을 막기 위해 `409 IMAGE_REQUEST_IN_PROGRESS_OR_OUTCOME_UNKNOWN`을 반환할 수 있습니다.

P06은 P07을 호출하지 않습니다. P08은 P06의 `product_profile`에서 P07 허용 필드를 구성해 review를 호출하고, review와 Draft를 통합합니다.

## 환경 변수와 데이터 연결

P06은 업무용 Trend·Stock 데이터베이스에 직접 접속하지 않습니다. P08이 해당 데이터를 조회해 `trend_result`와 `inventory_product_result`로 전달합니다. 따라서 P06 `.env`에는 Trend·Stock DB 키가 필요하지 않으며, P06의 로컬 SQLite는 artifact 소유권과 요청 재생 처리만 기록합니다. 현재 `/runs`에서 실제 외부 모델을 호출하는 기능은 이미지 생성이며, 이때 `LLM_API_KEY`를 사용합니다. 텍스트 생성 코드는 별도 경로로 존재하지만 현재 `/runs`에서는 호출하지 않습니다.

향후 데이터 조회를 통합할 때는 키를 P06에 복사하는 대신, 데이터베이스 소유 서비스(P08 또는 별도 upstream)가 하나의 credential로 필요한 데이터셋을 묶어 조회하고 현재 입력 계약에 맞는 결과를 P06에 전달하도록 설계합니다. `.env`와 `.envrc`는 각 저장소·실행 컴퓨터의 로컬 설정이므로 저장소 사이에 공유되지 않습니다.

현재 `/runs`는 규칙 기반 Draft 생성 경로를 사용하며 `find_categories` 도구나 외부 텍스트 모델을 호출하지 않습니다. 입력에 전달된 도구 진단 문구는 provenance와 limitation에 보존합니다. 상류 status가 `ok`이고 필수 Draft·시각자료가 생성됐으며 오류·누락·충돌이 없다면, 복구된 규칙 경고 문구만으로 결과를 `partial`로 바꾸지 않습니다.

## 상품·착장 이미지

실제 이미지 생성은 `VOGUE_DRAFT_IMAGE_PROVIDER=openai`와 이미지 API 키가 함께 설정된 경우에만 실행됩니다. provider를 지정하지 않으면 두 visual이 `skipped`로 반환됩니다. 지원하지 않는 provider 이름은 `IMAGE_PROVIDER_UNSUPPORTED` 오류로 나타납니다. 실제 생성 또는 artifact 저장에 실패하면 해당 visual은 `failed`가 되고 전체 결과는 `partial`입니다.

P06은 이미지 두 장을 최대 2개 동시 작업으로 생성합니다. 동일 상품 프로필의 hash를 각 visual에 기록하지만 이미지 픽셀의 디자인 일치는 자동 검증하지 않습니다. P08은 공유 artifact 저장소에서 `artifact://p06/images/<sha256>.<ext>`를 해석하고, 소유권·크기·SHA-256을 검증해야 합니다. 이미지 바이트 자체는 Draft JSON에 넣지 않습니다.

완료 응답은 동일 request ID와 동일 요청 본문에 재사용됩니다. 같은 입력의 동시 요청도 최초 저장된 응답으로 수렴합니다. 다른 본문에 같은 request ID를 사용하면 `409 REQUEST_ID_REUSED`입니다. 유료 이미지 요청의 처리 결과가 불확실하면 중복 과금을 막기 위해 같은 ID의 재호출을 거부할 수 있습니다. 실패 이미지를 의도적으로 다시 요청하려면 새 request ID를 사용하세요. 자동 재시도는 하지 않습니다.

## 실행

### 로컬

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
VOGUE_HTTP_MODE=local \
VOGUE_DRAFT_ARTIFACT_DIR=data/local/p06-artifacts \
PYTHONPATH=src python3 -m vogue_npp.prototype.server
```

기본 주소는 `http://127.0.0.1:8767`이고 health check는 `GET /api/health`입니다. `local` 모드는 loopback 연결만 허용합니다. 서비스 간 격리 네트워크의 `private` 모드는 bearer 인증을 사용하고, `service` 모드는 bearer 인증과 TLS가 필요합니다.

### Docker

저장소의 `.env.example`을 참고해 비밀값을 로컬 환경에 준비한 뒤:

```bash
docker compose up --build
```

Docker 설정은 `VOGUE_HTTP_MODE=service`와 TLS 인증서를 사용합니다. P08과 함께 실행할 때는 두 서비스가 같은 artifact volume을 보도록 배포 설정을 맞춰야 합니다. 키나 인증 토큰을 Git, 채팅, 로그에 기록하지 마세요.

### 실제 이미지 provider 설정

```bash
VOGUE_DRAFT_IMAGE_PROVIDER=openai
VOGUE_DRAFT_IMAGE_MODEL=gpt-image-2.5-sunburst
VOGUE_DRAFT_IMAGE_TIMEOUT_SECONDS=180
LLM_API_KEY=<승인된 secret 저장소에서 주입>
```

timeout 기본값은 180초이며 허용 범위는 5–300초입니다. 이미지 API 호출은 비용이 발생할 수 있습니다. 테스트는 합성 입력과 mock provider를 사용하며 실제 모델을 호출하지 않습니다. **합성 fixture 이미지 생성 모드는 제공하지 않습니다.**

## 지연·부분 상태 진단

`generation_metadata.timings_ms`에는 입력 검증·정규화, Draft 분석, 각 이미지 호출, 이미지 구간 전체 시간, artifact 저장, 응답 직렬화 시간이 기록됩니다. Docker 로그의 `p06_draft_completed`에는 캐시 저장 시간을 포함한 총 처리 시간이 추가됩니다. `p06_http_response_serialized` 로그에는 같은 request ID의 HTTP status와 응답 JSON 직렬화 시간이 기록됩니다. 두 로그를 request ID로 연결해 확인하세요. 로그에는 프롬프트, 이미지 바이트, upstream 원본 payload, 비밀값을 남기지 않습니다.

## 테스트

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

자세한 내용: [저장소 책임 경계](docs/repository-boundaries.md), [입력·출력 흐름](docs/design/input-output-processing-flow.md), [서비스 runbook](docs/design/prototype-runbook.md), [구조화 상품 프로필](docs/design/p06-structured-planning-draft.md).
