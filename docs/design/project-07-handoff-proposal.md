# Project_07 handoff implementation note

> **Historical proposal:** the active P06 planning handoff is `vogue-handoff/0.3`, documented in [the implemented HTTP handoff](../../contracts/http-handoff-v0.3.md). The sales/market payload proposal below remains historical context, not the P06 review bridge contract.

Status: proposal only; not a ratified shared wire contract. Project_07 owns the sales/market result schema proposal; Project_06 treats that result as an opaque handoff until Project_07, Project_06, and the designated contract steward approve a shared contract.

Project_06 treats the complete Project_07 result as an opaque mapping. It checks the request ID, agent identity, and top-level status, preserves the original mapping in the planning draft, and recursively carries Evidence IDs plus block-level limitations, errors, and missing-data notes into review context. It does not aggregate sales or market values, compute margins, reinterpret metrics, or convert missing data into zero.

The handoff transport is undecided as a team decision. The current design baseline proposes HTTP/JSON; this is not an approved implementation contract. The local `/api/planning-draft` is a prototype adapter, not a production service contract.

## HTTP/API 연동 부록 (제안, 미합의)

이 부록은 API Design 페이지의 HTTP/API transport 제안을 Project_06/Project_07 handoff 문맥에 연결합니다. **검토용 설계 기준안이며 팀 확정 결정이나 운영 사양이 아닙니다.** 승인 전에는 서비스 주소, 자격 증명, 운영 재시도, 배포를 구현 확정 사항으로 취급하지 않습니다.

### 전송 경계 제안

- 공통 envelope를 `POST /v1/agents/{agent_id}/runs`의 요청 및 응답 JSON body에 담습니다. HTTP/JSON은 현재 설계 기준안으로 제안하는 것이며, 팀 transport 결정은 미합의입니다.
- 요청 body는 `contract_version`, `request_id`, agent별 `input`을 포함하는 안입니다. 응답 envelope는 `contract_version`, `request_id`, `producer`, `status`, `result`를 포함하는 안입니다.
- producer 원본 결과 전체를 응답의 `result` 아래 보존합니다. 명시적으로 합의된 adapter 변환이 없는 한 원본 필드와 구조를 제거하거나 추측 변환하지 않습니다.
- 각 agent는 자신의 `schema_version`과 로컬 payload를 소유합니다. envelope의 `contract_version`은 전송 계약 버전이며 producer payload 버전과 별개입니다.
- orchestrator는 순서 및 호출, envelope/schema 호환성 검증, 요청·상태 정합성 확인, 원본 결과와 Evidence/제한 보존을 담당하는 안입니다.

### API Design 제안값 및 승인 전 상태

| 항목 | API Design 제안 | 상태/제약 |
| --- | --- | --- |
| Endpoint | `POST /v1/agents/{agent_id}/runs` | 제안, 팀 미합의 |
| 응답 본문 | 공통 envelope JSON, producer 원본은 `result` 아래 | 제안, 상세 공통 schema는 미합의 |
| 인증 | 서비스 간 TLS(HTTPS), OAuth 2.0 client credentials Bearer token 후보 | 인증 후보만 제안; 발급자, audience/scope, 키 회전 등 TBD |
| 연결 timeout | 3초 | 제안 초기값; 담당자 승인 전 TBD |
| 전체 요청 timeout | agent 호출당 60초 | 제안 초기값; 담당자 승인 전 TBD |
| 재시도 | 연결 실패 및 HTTP 429/502/503/504에 최대 1회 추가 시도; 429는 Retry-After 존중 | 제안; 실제 정책/숫자, backoff/jitter는 승인 전 TBD. 멱등성 합의 전 자동 재시도 비활성화가 안전 기본값이라는 제안 |
| Idempotency | `Idempotency-Key: {request_id}:{agent_id}` | 키 형식 제안; 저장 기간, 중복 본문 처리 규칙은 TBD |
| 서비스 주소·자격 증명·배포 | 미정 | 별도 승인 전 구현 확정 사항 아님 |

위 timeout·재시도·idempotency 값은 [API Design](https://app.notion.com/p/40d3269b1acd818bb6eaecb6d1db5f8b)의 제안값을 옮긴 것이며, 운영 설정 승인을 뜻하지 않습니다. 동기/비동기 운영, base URL, 실패 시 계속/중단/재개, 전체 orchestration deadline, 오류 상세 schema 및 계약 배포 절차도 미합의입니다.

Project_06의 현재 `/api/planning-draft` 동작, 공통 envelope 후보 비교, producer별 버전 호환 제안과 합성 검증 사례는 [HTTP 연동 계약 제안](http-integration-contract-proposal.md)에 별도로 정리했습니다. 해당 문서와 fixture도 담당자 합의 전 제안입니다.
