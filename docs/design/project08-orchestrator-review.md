# Project_08 통합 오케스트레이터 코드 검토

- 검토일: 2026-11-10
- 검토 범위: 로컬 Project_08 checkout의 `core.py`, `connectors.py`, `server.py`, web preview, I/O 계약·통합 검증 문서와 tests
- 현재 Project_08 HEAD: `325a87e` 기준에서 검토 시작; 이번 코드 보완은 Project_08 working tree에 미커밋 상태
- 계약 상태: `vogue-handoff/0.1-proposal`은 미승인 제안

## 결론

Project_08은 **합성 preview와 로컬 adapter 오케스트레이션을 구현한 코어**로는 명확한 단계 순서, request ID 검증, raw payload 보존, MD 최종 판단 경계를 갖췄습니다. 그러나 중앙 오케스트레이터의 운영 통합 설계가 완성된 상태는 아닙니다. Trend API/query adapter가 없고, Project_06의 현재 버전 검증과 Trend `1.1`이 충돌하며, 공통 `/runs` endpoint는 클라이언트만 있고 agent 서버 구현은 확인되지 않았습니다. 인증·timeout·재시도·지속성·실제 자료원도 결정되지 않았습니다.

이번 코드 보완은 연결 상태 응답이 설정값 존재를 pipeline 준비 완료처럼 표시하던 부분만 바로잡았습니다. 미승인 계약, producer 스키마, 데이터 흐름을 임의로 확정하지 않았습니다.

## 확인된 구성과 강점

| 항목 | 현재 코드에서 확인한 점 |
| --- | --- |
| 단계 흐름 | Trend → Stock → Project_07 → Project_06 순차 실행 |
| 실행 모드 | 합성 fixture preview와 명시적 consent가 있는 connected 모드 분리 |
| 추적 | request ID, 단계 상태, producer/version metadata와 raw response를 실행 결과에 보존 |
| 경계 검증 | request ID, producer ID, status, 제안 envelope metadata의 일치 여부를 확인 |
| 실패 은닉 | 예기치 않은 adapter exception 본문은 실행 결과/API 오류에 그대로 노출하지 않음 |
| UI 보안 | loopback 전용 서버, body 크기·query 길이 제한, CSP, `textContent` 기반 결과 표시 |
| 실제 자료 주의 | UI에서 연결 대상과 stock 측 LLM 전송 가능성을 확인받은 후 호출. 기본 synthetic preview는 외부 서비스를 호출하지 않음 |

## 주요 미완료 항목과 위험

| 우선순위 | 확인 사항 | 영향 및 필요한 다음 결정 |
| --- | --- | --- |
| Blocker | Trend 저장소에는 `TrendQuery → TrendAnalysisResult`가 있으나 사용자 원문 parser/API가 없고 Project_08 query-structuring 모듈은 runner와 연결되지 않음. 모듈도 LLM provider가 없음 | 실제 Trend 호출을 시작할 수 없음. parser/provider 승인 또는 명시적 adapter 책임자를 정해야 함 |
| Blocker | Project_08 PlanningRequest `1.0`, Stock `1.0`, Trend `1.1`; Project_06은 세 입력 schema version 일치를 요구 | 현재 runner는 P06 직전 호환성 오류로 멈춤. Trend `1.1` 직접 지원 또는 승인된 source/adapter/internal version mapping을 Project_06·Trend 소유자가 정해야 함. 원본 version 강등은 금지 |
| Blocker | `POST /v1/agents/{agent_id}/runs`는 proposal HTTP client만 확인됨. 네 producer가 공통 endpoint를 구현한 사실은 없음 | Proposal mode는 agent 서버 지원 전 실행 불가. 기존 `/v1/inventory-products`, `/api/planning-draft`, P07 Python API와 하나의 공통 운영 transport로 확정할 수 없음 |
| Blocker | Project_07 HTTP 서버는 확인되지 않았고 현재 connected mode는 같은 프로세스에서 Project_07 Python package를 호출 | 개발 preview에는 유효하지만 별도 서비스 배포·중앙 orchestrator topology와 다름. 배포 방식 합의 필요 |
| High | Project_08의 P07 adapter는 category/query만 context로 전달하고 geography/channel은 지정하지 않음. Project_07 `MarketResearchContext` 기본값은 KR/online | 사용자가 다른 market/channel을 요청해도 기본 범위로 분석될 수 있음. 원문 query를 scope로 추정하지 말고 정규화 ownership·다중 값 처리·missing scope 정책을 정해야 함 |
| High | Proposal HTTP mode는 `continue_after_error=True`로 모든 domain error 뒤 단계를 계속함. 현재 connected mode 기본값은 중단 | 오류 이후 계속 진행할 수 있는 단계별 조건이 다를 수 있음. status 종류와 producer별 downstream 허용 여부를 합의하고 per-stage continuation policy를 정해야 함 |
| High | HTTP `_post_json`에 명시적 timeout·response-size bound·retry가 없음 | 로컬 실험 범위는 문서에 밝혀져 있지만 운영 연결로 사용할 수 없음. timeout/retry 숫자와 응답 크기 정책은 승인 후 정해야 함 |
| High | Auth, service identity, secret 전달, transport trust, 저장/보존, durable idempotency가 없음 | 운영 연결의 보안·장애 복구·중복 실행 보장이 완료되지 않음 |
| Medium | `GET /api/connections`은 설정값과 로컬 checkout을 확인할 뿐 endpoint health, import callable, source 권한, schema negotiation은 수행하지 않음 | 환경 설정 존재를 실제 연결 성공으로 읽지 않도록 readiness 의미를 분리해야 함 |
| Medium | Connected UI는 각 단계 raw response 전체를 화면에서 펼쳐 볼 수 있고 서버는 loopback preview 전용 | 운영 UI로 승격하기 전 인증·역할별 권한·응답 필드 redaction·감사 정책이 필요 |
| Medium | 프로젝트 계약 제안은 입력/출력 초안이며 downstream의 `error` 결과, top-level status aggregation, schema evolution 및 Project_08 소비 형태가 합의되지 않음 | UI/API 계약 승인 전 producer contract를 확정하거나 결과 필드를 줄이지 말 것 |

### Scope 전달 상세

현재 `_project07_adapter`는 `requested_category`와 `requested_query`를 채웁니다. Project_07 context에 geography/channel 인자를 생략하면 P07 모델의 기본값 `KR`/`online`이 적용됩니다. Project_08 query module의 현재 `TrendQuery` schema에는 market/channel 필드가 없습니다. 그러므로 query parsing을 연결하는 것만으로 market/channel 전달 문제가 해결된다고 가정할 수 없습니다. 중복/복수 scope 값과 미기재 scope의 뜻을 양 소유자가 정해야 합니다.

## 이번에 보완한 Project_08 코드

기존 `/api/connections`는 필수 설정값이 모두 있으면 `ready=true`를 반환했습니다. 같은 응답의 Project_06 설명은 이미 알려진 Trend `1.1` / PlanningRequest·Stock `1.0` 차이로 P06 호출이 실패한다고 했습니다. 따라서 “전체 설정 완료” 표시는 연결된 전체 pipeline이 작동할 것처럼 과장될 수 있었습니다.

이를 다음처럼 바꿨습니다.

- `configuration_complete`: 필수 환경 설정과 로컬 Project_07 package/source factory 항목이 존재하는지 표시
- `ready`: 알려진 local blocker가 없을 때만 true. 현재 P06 schema blocker 때문에 모든 설정값이 있어도 false
- `known_blockers`, `readiness_note`: 이유와 확인 범위를 machine-readable로 반환
- UI: “설정 입력 완료”와 “해결되지 않은 호환 문제”를 구분. 이는 API 호출을 금지하지 않고, 연결 실행에서 해당 오류를 검증할 수는 있음

수정 파일: Project_08 `src/vogue_orchestrator/connectors.py`, `web/app.js`, `tests/test_connectors.py`, `docs/orchestration-design.md`, `README.md`.

## 운영 투입 전 합의 순서 제안

1. 사용자 원문 → TrendQuery 및 PlanningRequest 정규화 소유자, 필드 출처·미확정 규칙, market/channel scope mapping을 확정합니다.
2. Trend `1.1`을 Project_06이 받는지와 호환 adapter 책임·추적 metadata를 producer fixture와 함께 승인합니다.
3. 모든 단계의 공통 route ID와 응답 producer ID를 분리 정의하고, HTTP endpoint success/domain error/transport error를 합의합니다.
4. Producer별 `partial`, `no_results`, `error`를 다음 각 단계가 받아도 되는 조건을 표로 확정합니다. 일괄 continuation 대신 단계별 동작을 승인합니다.
5. HTTP 인증·timeout·response size·retry/backoff·idempotency storage·로그/retention을 승인하고 구현합니다.
6. Project_08 → Trend → Stock → Project_07 → Project_06의 실제 합성 HTTP fixture test를 구성합니다. External/corporate data는 사용하지 않습니다.
7. 실제 자료 연결은 각 source owner가 접근권한·허용 목적·삭제/보존·외부 모델 전송 여부를 승인한 뒤 별도 환경에서 수행합니다.

이 순서와 proposal endpoint는 설계 보완 제안이며 팀 확정 결정은 아닙니다.

## 검증

- Project_08: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests` — 83 tests discovered; 40 passed, 43 skipped because optional query extra (`pydantic`) is not installed.
- JavaScript syntax: `node --check web/app.js` — passed.
- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 examples/synthetic_local_integration.py` — passed with `trend/no_results → stock/no_results → Project_07/partial → Project_06/partial`; same request ID and P07 payload preservation confirmed. It used an explicit synthetic P07 source and the actual P06 handler on an ephemeral `127.0.0.1` port; P08 owned the P07 call using the validated request payload returned by P06.
- External Trend/Stock services, credentials, operational sources, and deployment were not used.
