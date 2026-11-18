# 운영

## 실행 모드

`NOVELTY_HTTP_MODE`는 반드시 정해야 한다. 정하지 않으면 서비스가 시작하지 않는다.

| 모드 | 인증 | 전송 | 용도 |
|---|---|---|---|
| `local` | 없음 | HTTP | 개발. `NOVELTY_HOST`가 루프백(`127.0.0.1`, `localhost`, `::1`)이 아니면 시작하지 않는다 |
| `private` | bearer 토큰 | HTTP | 격리된 컨테이너 네트워크 안 |
| `service` | bearer 토큰 | HTTPS | TLS 인증서와 키 필요(`NOVELTY_TLS_CERT_FILE`, `NOVELTY_TLS_KEY_FILE`) |

bearer 토큰은 서비스들이 함께 쓰는 `FASHION_PLANNER_SERVICE_TOKEN`이다. `private`·`service` 모드에서는 토큰이 없으면 시작하지 않는다.

```bash
NOVELTY_HTTP_MODE=local python -m fashion_planner_novelty.server
```

`GET /api/health`는 `{"ok": true, "mode": "novelty"}`를 돌려준다. `private`·`service` 모드에서는 health에도 토큰이 필요하다.

## Docker

`compose.yaml`은 이 서비스 하나를 `service` 모드로 띄운다. 호스트에 있는 TLS 인증서·키·CA 경로를 환경변수로 넘긴다.

```bash
export FASHION_PLANNER_SERVICE_TOKEN=...                 # 공유 토큰
export NOVELTY_TLS_CERT_HOST_PATH=/path/to/server.crt
export NOVELTY_TLS_KEY_HOST_PATH=/path/to/server.key
export NOVELTY_TLS_CA_HOST_PATH=/path/to/ca.crt         # healthcheck 검증용
docker compose up --build
```

- 컨테이너는 uid 10001의 `app` 사용자로 돈다.
- 생성 이미지와 원장은 볼륨 `novelty-data`의 `/app/data/local/novelty-artifacts`에 저장한다.
- 다섯 서비스를 함께 띄우는 방법은 orchestrator 저장소에 있다.

## 이미지와 텍스트 제공자

| 설정 | 결과 |
|---|---|
| `LLM_API_KEY` 없음 | 텍스트 LLM을 쓰지 않는다(`generation_metadata.status: "unavailable"`). 이미지는 `NOVELTY_DRAFT_IMAGE_PROVIDER`가 비었으면 `skipped`, `openai`이면 `IMAGE_API_KEY_MISSING`으로 `failed` |
| `LLM_API_KEY` 있음, `NOVELTY_TEXT_GENERATION_ENABLED=false` | 규칙 기반 Draft만(`status: "disabled"`) |
| `LLM_API_KEY` 있음, `NOVELTY_DRAFT_IMAGE_PROVIDER=openai` | 상품 이미지 1회와 착장 편집 1회 호출 |
| `NOVELTY_DRAFT_IMAGE_PROVIDER=synthetic` | 외부 호출 없이 합성 PNG 두 장. API 키가 필요 없다(아래 절) |
| `NOVELTY_DRAFT_IMAGE_PROVIDER`에 다른 값 | `IMAGE_PROVIDER_UNSUPPORTED`로 `failed` |

- 이미지 호출 하나의 시간 제한은 `NOVELTY_DRAFT_IMAGE_TIMEOUT_SECONDS`(기본 180초, 5–300초)다. 상품과 착장을 차례로 부르므로 이미지 단계는 그 두 배쯤 걸릴 수 있다.
- 모델 호출은 자동으로 다시 시도하지 않는다. 시간 초과된 클라이언트는 제공자가 이미 처리하고 청구했는지 알 수 없기 때문이다.
- 실패한 이미지를 일부러 다시 만들려면 **새 request ID**로 요청한다.

### 합성 이미지(`synthetic`)

e2e와 데모에서 이미지 경로 전체를 유료 호출 없이 돌리려고 둔 제공자다(`workflows/synthetic_images.py`).

- 512×512 팔레트 PNG(약 260KB)를 표준 라이브러리만으로 만든다. 그림에는 'SYNTHETIC'과 `PRODUCT`·`OUTFIT` 글자가 크게 들어가고, PNG `tEXt`에도 자리표시 그림이라고 적는다. 글자는 코드 안의 5×7 비트맵으로 그리며 제3자 이미지나 글꼴은 쓰지 않는다.
- 색은 입력 해시에서 정한다. 상품 칸은 상품 사양에서, 착장의 테두리는 상품 이미지 바이트에서, 재고 상품 칸은 재고 상품 사양에서 나온다. 착장은 OpenAI 경로처럼 상품 이미지를 만든 뒤에만 만든다.
- 결정적이다. 같은 입력이면 Python·zlib 판과 상관없이 같은 바이트가 나온다(deflate를 무압축 블록으로 직접 쓴다).
- 응답은 OpenAI 경로와 같은 모양이다. `status: "generated"`, `artifact://novelty/images/<sha256>.png`, 같은 `prompt_version`·`prompt_sha256`, 착장의 `reference_image_sha256`이 들어간다. 다른 점은 `model: "synthetic"`과 `provider_calls: 0`이다. `generation_metadata.image_provider`와 `image_model`도 `synthetic`이다.
- 이미지는 같은 저장소(`images/`, `issued` 표)에 쓰고 응답도 같은 원장에 저장한다. 유료 호출을 위한 선점(`image_run`)과 동시 처리 한도는 쓰지 않는다. 다시 만들어도 같은 바이트가 나오고 비용이 없기 때문이다.
- `limitations`에 합성 그림이라는 문장이 들어간다. orchestrator는 `model`이 `synthetic`이면 기획서에 합성 이미지라고 표시한다.

## 재요청과 409

| 상황 | 응답 |
|---|---|
| 같은 request ID, 같은 페이로드 | 저장된 응답을 그대로 돌려준다(모델 호출 없음) |
| 같은 request ID, 다른 페이로드 | `409 REQUEST_ID_REUSED` |
| 같은 request ID의 유료 이미지 시도가 진행 중이거나 결과를 모름 | `409 IMAGE_REQUEST_IN_PROGRESS_OR_OUTCOME_UNKNOWN`(`openai`만) |
| 다른 요청이 이미지를 만드는 중 | 두 visual이 `IMAGE_CAPACITY_BUSY`로 `failed`, 결과는 `partial`(`openai`만) |

## 저장소

`NOVELTY_DRAFT_ARTIFACT_DIR`(기본 `data/local/novelty-artifacts`) 아래에 저장한다.

- `images/<sha256>.<ext>`: 생성 이미지. 응답에는 `artifact://novelty/images/<sha256>.<ext>` 참조와 크기·해시만 들어간다.
- `ownership.sqlite3`: 이미지 소유(`issued`), 유료 이미지 선점(`image_run`), 완료 응답(`workflow_response`)

orchestrator는 같은 볼륨을 읽기 전용으로 마운트하고, 가져올 때 크기와 SHA-256을 검증한다. 이 서비스는 이미지를 내려주는 HTTP 경로를 두지 않는다. 보존과 삭제는 [data.md](data.md)를 본다.

## 로그와 처리 시간

로그는 표준 오류로 JSON 한 줄씩 남긴다. 프롬프트, 이미지 바이트, 입력 페이로드, 인증 정보는 남기지 않는다.

| 이벤트 | 내용 |
|---|---|
| `novelty_draft_completed` | request ID, 상태, `partial` 이유 코드, visual별 상태·호출 수·오류 코드, 단계별 처리 시간(응답 저장 포함) |
| `novelty_http_response_serialized` | request ID, 상태, HTTP 상태, 응답 직렬화 시간 |

두 이벤트는 request ID로 잇는다. 응답의 `generation_metadata.timings_ms`에는 입력 검증·정규화, Draft 분석, 이미지 호출별 시간, 이미지 구간 전체, 산출물 저장, 응답 직렬화, 총 처리 시간이 들어간다.

## `partial`의 이유 찾기

`result.validation_issues`의 `code`를 본다. 자주 나오는 코드는 다음과 같다.

| 코드 | 뜻 |
|---|---|
| `UPSTREAM_PARTIAL`, `UPSTREAM_NO_RESULTS`, `UPSTREAM_ERRORS_PRESENT`, `UPSTREAM_DATA_MISSING` | 상위 입력의 상태나 누락 |
| `INPUT_LIMITATION_PRESENT`, `INPUT_CONFLICTS_PRESENT` | 입력에 한계나 충돌이 있음 |
| `PLANNING_ANALYSIS_PARTIAL` | 분석에 필수 필드 누락, 매핑 실패, 충돌 등이 있음 |
| `PRODUCT_CATEGORY_UNRESOLVED` | 카테고리를 정하지 못해 이미지를 만들지 않음 |
| `IMAGE_PROVIDER_NOT_CONFIGURED`, `IMAGE_API_KEY_MISSING`, `IMAGE_API_TIMEOUT`, `IMAGE_API_HTTP_<code>` | 이미지 설정이나 호출 실패 |
| `OUTFIT_REFERENCE_UNAVAILABLE` | 상품 이미지가 없어 착장을 만들지 않음 |
| `ARTIFACT_PERSISTENCE_FAILED` | 이미지 저장 실패 |

텍스트 LLM 경로의 대체 이유는 `generation_metadata.status`와 `error_code`에 있다(예: `TEXT_OUTPUT_INVALID`, `TEXT_INPUT_OVER_BUDGET`, `TEXT_API_NOT_CONFIGURED`).

research 계약의 120자 상한 때문에 프로필 값을 바꿨다면 `generation_metadata.length_limited_fields`에 그 필드가 `product_profile.<필드>` 경로로 남는다. 바뀐 값은 규칙 기반 값이거나 카테고리별 검토 제안값이다([draft-model.md](draft-model.md#research로-넘어가는-값)).
