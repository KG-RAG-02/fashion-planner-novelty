# HTTP 계약: `novelty-handoff`

orchestrator가 novelty를 부르는 요청과 응답의 모양이다. 기준 스키마는 orchestrator 저장소의 계약 파일(`contracts/agents/novelty/`)이 소유한다. 이 문서는 서비스 쪽에서 본 요약이다. 두 저장소를 함께 검토한 뒤에만 바꾼다.

## 요청

`POST /v1/agents/novelty/runs`, `Content-Type: application/json`, 본문 최대 1,000,000바이트.

```json
{
  "contract_version": "novelty-handoff",
  "request_id": "example-001",
  "input": {
    "planning_request": {"schema_version": "1.0.0", "request_id": "example-001", "status": "ok"},
    "trend_result": {"schema_version": "1.0.0", "request_id": "example-001", "status": "ok"},
    "inventory_product_result": {"schema_version": "1.0.0", "request_id": "example-001", "agent_id": "inventory", "status": "ok"}
  }
}
```

- envelope에는 정확히 `contract_version`, `request_id`, `input`만 있어야 한다.
- `input`에는 정확히 위 세 입력만 있어야 하고, 모든 `request_id`가 envelope와 같아야 한다.
- `request_id`는 영숫자로 시작하고 영숫자와 `_ . : -`로만 이루어진 128자 이하 문자열이다.
- 지원하지 않는 스키마 버전, 예상하지 않은 생산자(`trend_result`는 `trend` 또는 생략, `inventory_product_result`는 `inventory`), 잘못된 상태 값은 `422`로 거절한다.
- 받은 입력은 원본 그대로 응답의 `result.input_evidence.*.payload`에 담긴다.

## 응답

```json
{
  "contract_version": "novelty-handoff",
  "request_id": "example-001",
  "producer": {"agent_id": "novelty", "schema_version": "1.0.0"},
  "status": "partial",
  "result": {
    "schema_version": "1.0.0",
    "request_id": "example-001",
    "status": "partial",
    "input_statuses": {},
    "draft": {"title": "…", "review_status": "md_review_required", "product_profile": {}, "trend_basis": {}, "visuals": {}},
    "generation_metadata": {},
    "input_evidence": {},
    "compatibility": {},
    "validation_issues": [],
    "limitations": [],
    "conflicts": [],
    "questions_for_validation": [],
    "planning_analysis": {},
    "image": {},
    "outfit_image": {},
    "planning_board": null
  }
}
```

- `status`: `ok`는 Draft와 이미지 두 장이 만들어지고 상위 입력이 모두 `ok`일 때다. 그 밖에는 `partial`이며 이유는 `validation_issues`에 있다.
- `result.image`와 `result.outfit_image`는 `draft.visuals.product`·`draft.visuals.outfit`과 같은 내용이다.
- 이미지 바이트는 응답에 넣지 않는다. 생성한 이미지는 `artifact://novelty/images/<sha256>.<ext>` 참조와 `media_type`, `size_bytes`, `sha256`으로 알린다. orchestrator는 공유 볼륨에서 읽고 크기와 해시를 검증한다.
- `generation_metadata`에는 엔진(`rule_based` 또는 모델), 상태(`generated`, `fallback`, `disabled`, `unavailable`), 오류 코드, 텍스트 프롬프트 식별(`prompt_version: "novelty-text-planning"`, `prompt_sha256`), 축약 정보(`prompt_reduction`), 이미지 설정, 처리 시간이 있다.
- `planning_board`는 늘 `null`이다. 기획서는 orchestrator가 만든다.

Draft의 필드는 [docs/draft-model.md](../docs/draft-model.md)에 있다.

## 오류

| HTTP | 코드 | 경우 |
|---|---|---|
| 400 | `INVALID_JSON`, `INVALID_CONTENT_LENGTH` | JSON을 읽을 수 없거나 길이 헤더가 숫자가 아님 |
| 401 | `UNAUTHORIZED` | `private`·`service` 모드에서 토큰이 없거나 틀림 |
| 404 | `NOT_FOUND` | 알 수 없는 경로 |
| 409 | `REQUEST_ID_REUSED` | 같은 request ID를 다른 페이로드에 다시 씀 |
| 409 | `IMAGE_REQUEST_IN_PROGRESS_OR_OUTCOME_UNKNOWN` | 같은 request ID의 유료 이미지 시도가 진행 중이거나 결과를 모름 |
| 413 | `PAYLOAD_TOO_LARGE` | 본문이 1,000,000바이트를 넘음(본문을 읽지 않고 응답) |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | JSON이 아님 |
| 422 | `INVALID_INPUT` 등 | 계약에 맞지 않는 입력 |
| 500 | `INTERNAL_ERROR` | 예상하지 못한 오류(세부 내용은 응답에 넣지 않음) |

오류 응답 본문은 `{"error": {"code": "…", "message": "…"}}`이다.
