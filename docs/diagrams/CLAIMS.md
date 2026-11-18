# 다이어그램 근거표

`docs/diagrams/src/*.dot`의 노드와 엣지마다 그것을 뒷받침하는 코드 위치를 적는다.
줄 번호는 문자열 앵커로 계산한 값이다. 코드를 바꾸면 다시 생성한다.

## request-flow

| 요소 | 근거 | 확인 방법 |
|---|---|---|
| orchestrator → POST /v1/agents/novelty/runs | `src/fashion_planner_novelty/server/app.py:485` | tests/test_handoff_runs.py: test_http_runs_route_and_retired_drafts_route |
| 1 HTTP 관문: bearer 토큰(private·service) | `src/fashion_planner_novelty/server/app.py:460` | tests/test_http_gate.py |
| 1 HTTP 관문: application/json만 허용 | `src/fashion_planner_novelty/server/app.py:494` | tests/test_http_gate.py |
| 1 HTTP 관문: Content-Length ≤ 1,000,000 B | `src/fashion_planner_novelty/server/app.py:36` | tests/test_http_gate.py; 트러블슈팅 T-HTTP-01 |
| 1 → 조기 응답: 본문을 읽기 전 413 | `src/fashion_planner_novelty/server/app.py:499` | tests/test_http_gate.py |
| 1 → 조기 응답: 401 | `src/fashion_planner_novelty/server/app.py:476` | tests/test_http_gate.py |
| 1 → 조기 응답: 400 잘못된 JSON | `src/fashion_planner_novelty/server/app.py:504` | tests/test_http_gate.py |
| 2 입력 정규화: envelope 키 | `src/fashion_planner_novelty/server/app.py:171` | tests/test_handoff_runs.py: test_request_id_contract_and_input_validation |
| 2 입력 정규화: 지원 스키마 | `src/fashion_planner_novelty/adapters/draft_inputs.py:18` | tests/test_workflow_input_adapter.py |
| 2 입력 정규화: 허용 생산자 | `src/fashion_planner_novelty/adapters/draft_inputs.py:23` | 코드 확인 |
| 2 입력 정규화: 내부 사본(1.0.0), 원본 보존 | `src/fashion_planner_novelty/adapters/draft_inputs.py:104` | tests/test_workflow_input_adapter.py |
| 2 입력 정규화: 지원 버전 1.0.0 | `src/fashion_planner_novelty/adapters/draft_inputs.py:17` | tests/test_workflow_input_adapter.py |
| 3 재요청 확인 | `src/fashion_planner_novelty/server/app.py:182` | tests/test_handoff_runs.py |
| 3 → 조기 응답: 409 REQUEST_ID_REUSED | `src/fashion_planner_novelty/server/app.py:513` | tests/test_handoff_runs.py |
| 4 기획 컨텍스트 | `src/fashion_planner_novelty/workflows/planning_draft.py:428` | tests/test_planning_analysis.py |
| 5 주 트렌드 선택 규칙 | `src/fashion_planner_novelty/domain/trend_basis.py:83` | tests/test_trend_basis.py |
| 5 → draft.trend_basis | `src/fashion_planner_novelty/domain/trend_basis.py:88` | tests/test_trend_basis.py |
| 5 쓸 수 있는 후보: 이름·근거·요청 차원 일치 | `src/fashion_planner_novelty/domain/trend_basis.py:53` | tests/test_trend_basis.py |
| 6 규칙 기반 Draft | `src/fashion_planner_novelty/domain/generator.py:610` | tests/test_trend_basis.py: RuleDraftTests |
| 6 빈 칸 → 표시된 제안값 | `src/fashion_planner_novelty/domain/generator.py:225` | tests/test_planning_analysis.py |
| 5 → 7 LLM 기본 켜짐 | `src/fashion_planner_novelty/server/app.py:51` | 코드 확인 |
| LLM에는 API 키가 필요 | `src/fashion_planner_novelty/server/app.py:56` | tests/test_text_concept_generation.py |
| 7 프롬프트 예산: 24,000자 상한 | `src/fashion_planner_novelty/domain/prompt_safety.py:8` | tests/test_prompt_budget.py |
| 7 프롬프트 예산: T1–T5 축약 | `src/fashion_planner_novelty/domain/prompt_budget.py:36` | tests/test_prompt_budget.py |
| 7 → 6 상한 초과: 호출 안 함 | `src/fashion_planner_novelty/workflows/text_concept_generation.py:489` | tests/test_prompt_budget.py |
| OpenAI Responses 호출 | `src/fashion_planner_novelty/sources/openai_text_provider.py:152` | tests/test_openai_text_provider.py (mock) |
| 8 모델 출력 검증 | `src/fashion_planner_novelty/workflows/text_concept_generation.py:257` | tests/test_text_concept_generation.py |
| 8 필수 프로필 필드 | `src/fashion_planner_novelty/workflows/text_concept_generation.py:298` | tests/test_text_concept_generation.py |
| 8 → 6 검증 실패: 규칙 Draft로 대체 | `src/fashion_planner_novelty/workflows/text_concept_generation.py:525` | tests/test_text_concept_generation.py |
| 9 병합: 빈 필드 채움 | `src/fashion_planner_novelty/workflows/text_concept_generation.py:513` | tests/test_text_concept_generation.py |
| 9 병합: 첫 근거 색 규칙 | `src/fashion_planner_novelty/workflows/text_concept_generation.py:514` | tests/test_trend_basis.py: FirstEvidenceColourTests |
| 10 동반 재고 상품 | `src/fashion_planner_novelty/domain/outfit_companion.py:63` | tests/test_outfit_companion.py |
| 10 같은 착장 역할이면 건너뜀 | `src/fashion_planner_novelty/domain/outfit_companion.py:81` | tests/test_outfit_companion.py |
| 11 이미지 사양 | `src/fashion_planner_novelty/server/app.py:135` | tests/test_handoff_runs.py |
| 11 사양 sha256 | `src/fashion_planner_novelty/server/app.py:213` | tests/test_handoff_runs.py |
| OpenAI Images generations | `src/fashion_planner_novelty/workflows/image_generation.py:102` | tests/test_image_generation.py (mock) |
| 상품 이미지 → 착장 편집(순차) | `src/fashion_planner_novelty/server/app.py:294` | tests/test_handoff_runs.py |
| OpenAI Images edits | `src/fashion_planner_novelty/workflows/image_generation.py:128` | tests/test_handoff_runs.py (urlopen mock) |
| 재고 사진 → 착장 편집 | `src/fashion_planner_novelty/server/app.py:92` | tests/test_outfit_companion.py |
| 상품 이미지 실패 → 착장 건너뜀 | `src/fashion_planner_novelty/server/app.py:308` | tests/test_handoff_runs.py |
| 12 산출물 저장소: 내용 주소 이미지 | `src/fashion_planner_novelty/workflows/draft_artifacts.py:209` | tests/test_handoff_runs.py |
| 12 원장: 이미지 소유 표 | `src/fashion_planner_novelty/workflows/draft_artifacts.py:142` | tests/test_handoff_runs.py |
| 12 원장: 이미지 실행 표 | `src/fashion_planner_novelty/workflows/draft_artifacts.py:173` | tests/test_handoff_runs.py |
| 12 원장: 저장된 응답 | `src/fashion_planner_novelty/server/app.py:415` | tests/test_handoff_runs.py |
| 13 status ok 규칙 | `src/fashion_planner_novelty/server/app.py:346` | tests/test_handoff_runs.py |

## draft-model

| 요소 | 근거 | 확인 방법 |
|---|---|---|
| ProductConceptDraft | `src/fashion_planner_novelty/domain/concept.py:159` | dataclass 필드 |
| ProductProfile (값 7개 + details) | `src/fashion_planner_novelty/domain/concept.py:61` | dataclass 필드 |
| SourcedClaim | `src/fashion_planner_novelty/domain/concept.py:34` | dataclass 필드 |
| kind 값 | `src/fashion_planner_novelty/domain/concept.py:22` | Literal 값 |
| ProposedAttribute | `src/fashion_planner_novelty/domain/concept.py:41` | dataclass 필드 |
| OpportunityFinding | `src/fashion_planner_novelty/domain/concept.py:49` | dataclass 필드 |
| TrendBasis | `src/fashion_planner_novelty/domain/concept.py:141` | dataclass 필드 |
| 결과 조립 때 title 추가 | `src/fashion_planner_novelty/workflows/planning_draft.py:475` | 코드 확인 |
| review_status | `src/fashion_planner_novelty/server/app.py:203` | tests/test_handoff_runs.py |
| 결과 조립 때 visuals 추가 | `src/fashion_planner_novelty/server/app.py:333` | tests/test_handoff_runs.py |
| artifact 필드 | `src/fashion_planner_novelty/workflows/draft_artifacts.py:215` | tests/test_handoff_runs.py |
| visual: product_specification_sha256 | `src/fashion_planner_novelty/server/app.py:329` | tests/test_handoff_runs.py |
| visual: prompt_sha256 | `src/fashion_planner_novelty/server/app.py:330` | tests/test_handoff_runs.py, tests/test_prompt_registry.py |
| visual: prompt_version novelty-draft-visuals | `src/fashion_planner_novelty/workflows/draft_artifacts.py:73` | tests/test_handoff_runs.py |
| 착장: reference_image_sha256 | `src/fashion_planner_novelty/server/app.py:296` | tests/test_handoff_runs.py |
| 착장: companion | `src/fashion_planner_novelty/server/app.py:297` | tests/test_outfit_companion.py |
