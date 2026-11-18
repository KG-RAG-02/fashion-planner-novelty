# 변경 기록

이 문서는 [Keep a Changelog 1.1](https://keepachangelog.com/ko/1.1.0/) 형식을 따르고, 버전은 [유의적 버전](https://semver.org/lang/ko/)을 따른다.

## [1.0.0] - 2026-11-18

첫 공개 릴리스. 팀 내부에서 쓰던 서비스를 공개용으로 정리했다.

### 추가
- `POST /v1/agents/novelty/runs`: 기획 요청과 트렌드·재고 결과를 받아 근거가 연결된 신상품 Draft를 돌려준다.
- 주 트렌드 하나를 규칙으로 고르고 `draft.trend_basis`에 기록한다.
- 텍스트 LLM 기획(선택): 구조화 출력, 근거 ID 허용 목록, 필수 프로필 필드, 24,000자 결정적 프롬프트 예산, 실패 시 규칙 기반 Draft로 대체.
- 상품 이미지와, 그 이미지를 편집해 재고 상품 하나와 함께 입힌 착장 이미지(선택). 내용 해시 저장소와 SQLite 원장으로 재요청을 안전하게 처리한다.
- 응답의 `generation_metadata.prompt_sha256`과 `draft.visuals.*.prompt_sha256`: 프롬프트 템플릿을 내용 해시로 식별한다.
- `pyproject.toml`(Python 3.11 이상), `scripts/run_offline_tests.py`(네트워크를 막은 테스트 실행), GitHub Actions CI(Python 3.11·3.13).
- HTTP 관문 테스트: 401·413(본문을 읽기 전)·415·400 응답.
- research로 넘어가는 다섯 프로필 값을 research 계약의 120자 이하로 보장한다. 넘는 값은 규칙 기반 값이나 카테고리별 제안값으로 바꾸고 `generation_metadata.length_limited_fields`에 남긴다. 120자를 넘는 요청 `category`·`season`은 422로 거절한다.
- 문서: 아키텍처, Draft 데이터 모델, 운영, 데이터 카드, 프롬프트 안전, 트러블슈팅, 설계 결정(ADR 6개), 다이어그램과 근거표.

### 변경
- 패키지와 import 이름을 `fashion-planner-novelty`/`fashion_planner_novelty`로 맞추고, 실행 진입점을 `python -m fashion_planner_novelty.server`로 정했다.
- 서비스 식별자를 역할 이름으로 바꿨다: agent_id `novelty`, 전송 이름 `novelty-handoff`, `schema_version` `1.0.0`, 산출물 URI `artifact://novelty/images/`, 환경변수 `NOVELTY_*`와 공용 토큰 `FASHION_PLANNER_SERVICE_TOKEN`.
- 규칙·프롬프트 이름에서 순번을 뺐다(예: `most_evidence_linked_design_attributes`, `novelty-draft-visuals`). 버전은 `schema_version` 필드 한 곳에만 둔다.
- 프롬프트 디렉터리에서 버전 경로를 뺐다(`prompts/text_planning/`, `prompts/concept_image/`).

### 수정
- `generation_metadata.llm_empty_fields`가 LLM이 비운 색·실루엣을 보고하지 않던 회귀를 고쳤다.
- 프로필 동작 변경과 맞지 않던 테스트 기대값을 현행 동작에 맞췄다. 기준 커밋에서 실패하던 15건(오래된 기대값 14건, 위 회귀 1건)이 모두 통과한다.

### 삭제
- HTTP 서비스에서 쓰지 않던 TrendBatch·검색 라이브러리와 옛 이미지 워크플로 함수, 고아 프롬프트.
- 쓰이지 않던 토큰 별칭 환경변수.
- 내부 상태·계획 문서와 평가 사례 픽스처, 번호 표기로 쓴 옛 설계 문서(현행 문서로 다시 씀).
- 테스트에 있던 실제 상품 ID와 개발 중 요청 ID(합성 값으로 바꿈).

[1.0.0]: https://github.com/KG-RAG-02/fashion-planner-novelty/releases/tag/v1.0.0
