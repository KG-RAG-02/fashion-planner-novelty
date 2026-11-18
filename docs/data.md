# 데이터 카드

**MIT 라이선스는 이 저장소의 코드에만 적용된다.** 데이터셋, 배포 환경이 받는 데이터, 모델 출력은 MIT의 대상이 아니다.

## 이 저장소에 들어 있는 것

| 경로 | 내용 | 출처 |
|---|---|---|
| `tests/fixtures/`, `tests/*.py` | 작은 요청·재고 픽스처와 테스트 입력 | 합성. `SYN-`, `synthetic-` 같은 식별자를 쓰는 지어낸 값이며 어떤 데이터셋에서도 파생하지 않았다 |
| `examples/request.synthetic.json` | 빠른 시작용 요청 | 합성 |
| `prompts/` | 이 프로젝트를 위해 쓴 프롬프트 템플릿 | 직접 작성, MIT |

이 저장소와 공개 히스토리에는 데이터셋, 모델 출력, 생성 이미지, 기사 원문, 제3자 사진이 없다.

## 서비스가 받는 것

요청마다 입력 세 개가 들어온다. 보통 orchestrator가 모아서 보낸다.

| 입력 | 만드는 곳 | 들어 있을 수 있는 것 |
|---|---|---|
| `planning_request` | orchestrator | 사용자 질문과 정규화한 필드(시즌, 카테고리, 요청 속성, 제약) |
| `trend_result` | trend 서비스 | 패션 기사에서 뽑은 트렌드의 이름, 설명, 디자인 속성, 근거 ID |
| `inventory_product_result` | inventory 서비스 | 재고 상품의 속성과 수량, 트렌드와의 연결, 상품마다 사진 한 장(base64, 선택) |

데이터의 출처와 이용 조건은 각 상위 서비스 저장소가 밝힌다. 이 서비스는 데이터를 내려받지 않고 어떤 데이터베이스에도 접속하지 않는다.

## 서비스가 제3자에게 보내는 것

`LLM_API_KEY`를 설정하지 않으면 아무것도 보내지 않는다. 키가 있으면 다음을 보낸다.

| 받는 곳 | 보내는 때 | 보내는 데이터 |
|---|---|---|
| OpenAI Responses API(텍스트) | `NOVELTY_TEXT_GENERATION_ENABLED`가 `true`일 때(기본값) | 요청 필드, 주 트렌드의 이름·설명·속성·근거 ID, 재고 상품 요약, 한계·충돌 문장. 최대 24,000자이며 이미지는 없다 |
| OpenAI Images API, generations | `NOVELTY_DRAFT_IMAGE_PROVIDER=openai`일 때 | 상품 사양(카테고리, 종류, 시즌, 소재, 실루엣, 색, 디테일) |
| OpenAI Images API, edits | 같은 설정에서 상품 이미지가 만들어진 뒤 | 생성된 상품 이미지, 동반 재고 상품의 속성, 재고 결과에 사진이 있으면 그 사진 |

**이미지를 켜기 전에 상위 데이터의 이용 조건을 확인한다.**

- 착장 편집 호출은 재고 상품 사진을 이미지 제공자에게 보낸다.
- 재고 사진이 이용 조건이 제한된 데이터셋에서 왔다면 제3자 API로 보내는 것이 허용되지 않을 수 있다. 예를 들어 경진대회 데이터셋은 비상업적 이용만 허용하고 재배포를 금지하는 경우가 많다.
- 그런 경우에는 `NOVELTY_DRAFT_IMAGE_PROVIDER`를 비워 둔다. 서비스는 Draft만 돌려주고 두 이미지는 `skipped`로 표시한다.
- `NOVELTY_DRAFT_IMAGE_PROVIDER=synthetic`은 아무것도 보내지 않는다. 재고 사진도 쓰지 않고, 입력의 해시로 색만 정한 자리표시 그림을 서비스 안에서 만든다.

## 서비스가 저장하는 것

모두 `NOVELTY_DRAFT_ARTIFACT_DIR`(기본값 `data/local/novelty-artifacts`, Git이 무시함) 아래에 저장한다.

| 파일 | 내용 | 보존 |
|---|---|---|
| `images/<sha256>.<ext>` | 생성한 상품·착장 이미지 | 직접 지울 때까지 |
| `ownership.sqlite3`의 `issued` 표 | 이미지가 어느 요청 것인지 | 유지 |
| `ownership.sqlite3`의 `image_run` 표 | 유료 이미지 호출 전에 잡은 선점 | 유지 |
| `ownership.sqlite3`의 `workflow_response` 표 | 완료한 요청의 전체 응답 | 유지 |

- 응답은 출처 추적을 위해 받은 입력을 `result.input_evidence.*.payload`에 그대로 담는다. 그래서 저장된 응답에도 입력에 들어 있던 재고 사진이 남는다.
- 모두 지우려면 디렉터리를 지운다. 다음 요청 때 서비스가 다시 만든다.
- 로그에는 request ID, 상태와 오류 코드, 처리 시간만 남는다. 프롬프트, 이미지 바이트, 입력 페이로드, 인증 정보는 남기지 않는다.

## 생성 이미지

이미지는 설정한 제공자가 만들며 그 제공자의 이용 조건을 따른다. 검토용 콘셉트 시안이고 상품 사진이 아니다. 이 저장소에는 생성 이미지를 넣지 않는다.

## 스키마

- 응답 구조: [contracts/http-handoff.md](../contracts/http-handoff.md)
- Draft 모델: [draft-model.md](draft-model.md)
