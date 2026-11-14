# Project_06 범용 패션 상품기획 도구 설계

- 기준일: 2026-11-10
- 상태: 저장소 기반 설계 초안 · 현업 MD 검증 전 · 데이터/운영 계약 미완료
- 목적: 패션 회사 고객에게 설명 가능한 지원 범위와 검증 로드맵을 정의
- 변경 범위: Project_06 설계 문서만. Project_07/08, Trend, Stock 저장소와 실제 고객 데이터는 변경·사용하지 않음
- 관련 기준: [MD 업무 적합성 검토](md-planning-workflow-fit-review.md), [데이터·Evidence 경계](data-source-and-evidence-plan.md), [HTTP handoff v0.3](../../contracts/http-handoff-v0.3.md)

## 1. 요약과 제품 주장 경계

현재 Project_06은 전달된 입력을 제한된 내부 모델로 정리하고, 근거·상태·오류를 보존하면서 MD 검토용 규칙 기반 기획 초안을 만든다. 현재 확인된 구현만으로는 임의의 쿼리나 사내 자료 형식에 적응하는 범용 기획자, 또는 실제 기업 도입 가능한 완성 제품이라고 주장할 수 없다.

제품의 목표는 “모든 자료를 자동으로 이해”하는 것이 아니라 다음을 만족하는 **통제 가능한 기획 보조 도구**다.

1. 지원하는 데이터 형식·버전·단위를 공개하고 미지원 입력을 명시적으로 돌려준다.
2. 원본과 변환 결과, 출처·시점·범위·Evidence를 함께 추적한다.
3. 관찰 사실, 사용자 요청, 기획 제안, 가설, 미확정을 구분한다.
4. 데이터 상태와 업무 규칙에 맞는 초안 또는 추가 질문을 제공한다.
5. MD가 결과를 수정·비교·보류할 수 있고, 실제 MD 평가로 유용성을 검증한다.
6. 기업 데이터 권한·격리·삭제·감사와 운영 책임이 승인된 범위만 연결한다.

**홍보 가능한 현 단계 표현:** “합성 입력으로 API 계약·근거 보존·규칙 기반 검토 초안 흐름을 검증하는 Project_06 프로토타입.” 실제 MD 검증, 승인된 사내자료 연결, 운영 보안 검증이 완료되기 전에는 업무 시간 절감, 매출 개선, 수요 예측, 범용성, 고객 배포 준비를 주장하지 않는다.

## 2. 현황 감사: 코드에서 확인한 내용

| 영역 | 현재 확인한 구현 | 한계와 의미 |
|---|---|---|
| 공개 호출 | `POST /v1/agents/new-product-agent/runs` | P08 로컬 `vogue-handoff/0.3` 형식으로 구현. cross-project contract 동결과 운영 배포 검증은 남아 있음 |
| 입력 버전 | PlanningRequest `1.0`, Trend `1.1`, Stock `1.0`만 P08 handoff adapter에서 허용 | 이 버전 밖의 입력은 자동 대응하지 않고 호환 오류를 반환해야 함 |
| Trend 변환 | `src/vogue_npp/adapters/draft_inputs.py` validates producer versions and preserves Trend 1.1 provenance while adapting internal input | Version normalization alone does not prove semantic compatibility; maintain versioned fixtures |
| 입력 normalization | server에서 request/trend/stock payload를 `PlanningRequest`, `TrendResult`, `InventoryProductResult` 등으로 수동 변환 | 고정된 필드 매핑 중심. 임의 CSV/Excel/PDF나 producer 변화에 대한 범용 parser가 아님 |
| Project_07 | P08이 P06 초안을 받은 뒤 P07 `/reviews`를 직접 호출 | P06은 P07 응답을 입력으로 받지 않으며 P07 요청을 보내지 않음 |
| 초안 생성 | `RuleBasedConceptGenerator`가 Evidence를 연결한 초안 scaffold를 생성 | 텍스트 LLM provider는 실제 연결되어 있지 않음. 규칙은 제한된 의미의 후보만 다루며 상품기획 전문성·성과를 입증하지 않음 |
| RAG | 별도 TrendBatch/retrieval 라이브러리 prototype과 테스트가 있음 | active `/runs` 요청에서는 호출하지 않으며, 운영 인덱스·자료권한 체계·회사 문서 연결도 없음 |
| 외부 모델 | 선택형 이미지 생성 경로 | 고객 자료 전송 승인, tenant 격리, provider 계약·운영 보호가 확정된 기업 연결로 볼 수 없음 |
| 평가 | 합성/mock 기반 단위·계약 테스트와 평가 계획 | 현업 MD blind 평가, 실제 업무 기준선, 수치화된 유용성 검증은 없음 |
| 업무 결정 | 결과는 `md_review_required`; 판매/시장 계산은 Project_07 소유 | 상품 채택, 가격·원가·마진, 생산 가능성, 수량/발주를 자동 결정하지 않음 |

현황은 현재 Project_06 checkout의 코드와 문서를 기준으로 한다. 외부 저장소의 실제 배포 상태나 고객사 업무는 이 감사에서 확인한 사실이 아니다. 담당자 확인 없이 Project_07/08 또는 Trend/Stock contract를 바꾸지 않는다.

### 이번 설계 기반 작업 기록

현재 단계에서는 P08 `/runs` 입력만 대상으로 version registry를 코드로 분리했다. `normalize_workflow_inputs()`는 지원 버전·producer·status·request ID와 top-level input key를 검사하고, 원본 사본·정규화 사본·adapter/version/hash provenance를 반환한다. HTTP `/runs` handler는 이 registry를 사용한다. 다른 CSV/Excel/PDF나 임의 producer version에 자동 대응하는 기능, 업무 의미 확장, Project_08 schema 변경은 구현 범위에 포함되지 않는다.

### 현재 데이터 처리의 강점과 제한

- 강점: request ID·status·Evidence·limitations·errors 및 원본 payload 보존, `no_results`와 실제 수량 0 구분, 재고를 수요로 해석하지 않는 경계, 미등록 Evidence 검증, MD 확인 질문.
- 제한: `schema_version` 지원은 닫힌 목록이며 내부 context가 request/trend/stock의 동일 내부 버전을 요구한다. 새 producer 버전은 명시 adapter·fixture·승인 없이 받을 수 없다.
- 제한: 필드가 보존되는 것과 초안에서 의미 있게 사용되는 것은 다르다. P07은 P06 응답 후 P08이 호출한다. P06에는 P07 payload가 전달되지 않는다.
- 제한: Evidence ID가 현재 입력에 존재하는지 검사하는 것과 그 Evidence가 실제 문장을 뒷받침하는지 검증하는 것은 별도다.

## 3. 현업 MD 업무 설계: 확인할 가설

아래는 인터뷰 전 가설이며 패션업계 전체에 대한 사실 주장이 아니다. 역할과 업무 순서는 브랜드, 카테고리, 유통 방식에 따라 달라질 수 있다.

| 업무 구간 가설 | 확인할 질문 | 이해관계자 |
|---|---|---|
| 시즌/카테고리 방향 설정 | 시즌 목표·브랜드 전략·카테고리 계획은 어디서 오고 누가 확정하는가? | MD 리더, 브랜드 기획 |
| 기회 조사와 상품 구상 | Trend, 과거 상품, 판매/재고, 고객 의견 중 어떤 자료가 실제로 쓰이고 우선순위는 무엇인가? | 카테고리 MD, 리서치 |
| 라인업/속성 계획 | 스타일 수, 옵션 폭, 소재·컬러·핏·가격대, SKU 구성이 어떤 단계에서 정해지는가? | MD, 디자인, 상품운영 |
| 리뷰/수정/보류 | 리뷰어가 보는 문서 형식, 필수 근거, 수정 이력, 보류 조건은 무엇인가? | MD, 디자인, 상품기획 책임자 |
| 샘플·소싱·원가 연결 | Project_06 이후 원가/생산성·MOQ·리드타임을 누가 어느 문서에서 검토하는가? | 소싱, 생산, 재무 |
| 판매/시장 결과 활용 | 과거 판매 관찰, 시장 조사, 고객 반응이 향후 기획 판단에 어떻게 쓰이며 제한은 무엇인가? | Project_07 담당, MD, 영업 |
| 산출물 인계 | 승인된 기획안은 어떤 시스템이나 파일로 이동하고 누가 후속 상태를 관리하는가? | MD, 업무 시스템 담당 |

### 고객 인터뷰 질문과 가치 가설

인터뷰에서는 다음을 확인하고 수치나 우선순위를 응답 전에 정하지 않는다.

- 최근 완료한 한 건의 기획 업무를 처음 입력부터 승인/보류까지 재구성할 수 있는가? 실제 산출물은 어느 단계에 있었는가?
- 반복 복사·검색·근거 확인·문서화 중 가장 큰 마찰은 무엇인가? 빈도와 현재 소요 시간을 어떻게 관찰할 수 있는가?
- 초안이 유용하려면 어떤 부분을 미리 채우고 어떤 부분은 반드시 질문으로 남겨야 하는가?
- 잘못된 추천이 초래하는 업무 비용과 안전하게 보류할 조건은 무엇인가?
- 사내 문서의 접근 권한, 민감도, 학습·추론 목적 사용 허가, 저장·삭제 조건은 무엇인가?
- 적합한 파일럿 성공지표는 작성시간, 수정 횟수, 근거 검증시간, 검토자 만족도, 사용 지속성 중 무엇인가? 기준선과 측정 방법은 있는가?

가치 가설은 “검색·근거정리·초안 편집을 도울 가능성” 정도로 둔다. 실제 현업 파일럿 전에는 시간 절감이나 기획 품질 상승을 성과로 표현하지 않는다.

## 4. 입력 자료 지원 설계

### 수용 원칙

1. 외부 wire payload는 producer schema/version과 소유 경계를 유지한다.
2. adapter는 `source_payload`, `source_schema_version`, `adapter_id/version`, `normalized_payload`, 변환 경고를 분리해 보존한다.
3. 정규화 schema는 내부 계산을 위한 별도 버전이며 producer version을 대신하지 않는다.
4. 자동 변환은 승인된 mapping table과 검증 fixture가 있는 경우에만 한다. 알 수 없는 컬럼·단위·코드·문서 유형은 보존하고 `unsupported/unmapped` 상태로 드러낸다.
5. 원본에 존재하지 않는 “0”, 통화, 기간, 국가, 채널, 고객 속성을 만들어내지 않는다.
6. 검색·생성 전에 자료 소유자, 사용 목적, 역할 기반 권한, 테넌트 경계를 검증한다.

### 초기 지원 매트릭스

이 표의 “후보”는 내부 설계 대상이지 현재 구현 완료를 뜻하지 않는다. 형식과 producer schema는 파일럿 기업과 담당자가 확인한 뒤 지원 선언한다.

| 데이터 종류 | 현재 Project_06 사용/지원 | 정규화 후보와 필수 provenance | 미지원·검토 경계 |
|---|---|---|---|
| PlanningRequest/사용자 쿼리 | 합의 handoff에서 version `1.0`; 내부에 query/context/attributes/constraints/missing fields | 원문, request ID, 필드별 origin(user/inferred/unknown), 명시 scope | 자유 문장만으로 시즌·시장·고객을 확정 추출하지 않음. 미확정은 질문 |
| Trend 결과 | 합의 handoff `1.1`; 일부 trend/candidate 구조 매핑 | 원본 JSON, producer/version, 추출 candidate와 각 Evidence ID, 필터·기간·제한 | 새 schema나 의미가 바뀐 필드는 adapter 승인 전 사용 금지 |
| 상품/SKU 카탈로그 | 일부 상품 및 속성 구조를 현재 parser가 소비 | style/SKU ID, taxonomy version, category, attributes, locale, effective dates, source | 고객별 임의 Excel/ERP schema 자동 지원 아님; field mapping 필요 |
| 재고 스냅샷 | Stock `1.0` 일부 필드; quantity/unit/as_of/definition 보존 | 제품 ID, 위치·가용 정의, 단위, as-of, 조회 기간, Evidence | 재고 snapshot은 demand/sell-through가 아님. 위치/예약/반품 포함 여부 불명 시 미확정 |
| 판매/반품/가격/프로모션 시계열 | Project_07 결과 `1.0`을 opaque handoff로 전달·보존 | 계산 주체가 만든 지표 정의, 기간, 채널/시장, 통화/단위, 집계 기준, 제한·Evidence | Project_06에서 원장 재집계/매출·수요 예측 불가. 새 계산은 Project_07 승인 필요 |
| Trend 리포트/문서 | 현재 Trend payload에 연결된 관찰 중심 | 문서 ID, 페이지/섹션 locator, 작성일/관찰기간, 인용, 사용권한 | 임의 PDF/웹 검색 ingest는 현재 지원 완료가 아님 |
| 과거 기획서/명세서/가이드 | 합성 RAG corpus 및 검색 포트 | 승인 문서 ID, version, owner, 승인/효력일, section, permission, chunk hash/index version | 운영 사내 문서 인덱스·권한 필터·삭제 반영은 연결 전 TBD |
| 상품 taxonomy/용어 사전 | 내부 query/retrieval 설계 후보 | 코드·label·locale·부모 관계·유효 기간·사전 version·mapping confidence | 동의어/유사어를 자동으로 정식 코드로 확정하지 않음 |

### 값과 품질 상태 모델

최소 상태는 `present`, `missing`, `not_provided`, `no_results`, `error`, `unknown`, `not_applicable`, `stale`, `conflict`, `unmapped`로 분리하는 방안을 제안한다. 수치 필드는 값과 단위, 기간, 기준시점, 측정 정의를 함께 둔다. `0`은 source record의 실제 숫자만 나타내며 결측 sentinel로 쓰지 않는다. `partial`은 결과 자체와 미수집 범위/오류를 함께 기록한다.

중복 데이터는 ID와 출처 기준으로 식별하되, 충돌값을 임의로 하나 선택하지 않는다. 같은 상품의 코드가 다르면 승인된 crosswalk가 없을 때 별도 레코드/매핑 필요로 표시한다. 오래된 문서·재고는 freshness 정책을 합의하기 전 임의로 최신값처럼 취급하지 않는다.

## 5. Adapter와 정규화 구조 제안

```text
producer-owned payload
  → size/content/type validation
  → producer + source schema allowlist
  → explicit versioned adapter
  → normalized internal request/trend/catalog/inventory/market slots
  → consistency + provenance + permission checks
  → planning context
  → generator / retrieval
  → claim-evidence + output validation
  → review draft + raw/normalized trace
```

Adapter 결과에는 최소 `producer_id`, `source_schema_version`, `adapter_id`, `adapter_version`, `normalized_schema_version`, `source_payload_hash`, 변환 경고/오류, 변환된 필드 경로를 남긴다. 원본 저장 정책에 따라 응답에 원문 대신 보호된 reference/hash를 둘 수 있지만, 접근 권한과 retention을 먼저 합의한다. 현재 handoff 응답은 trace에 raw JSON을 포함하므로 운영 tenant별 redaction/크기 제한은 제품화 전 결정해야 한다.

어댑터 호환표는 `src/vogue_npp/adapters/draft_inputs.py`와 함께 바뀌어야 한다. 새 producer version은 fixture와 adapter 검증 없이 지원 목록에 추가하지 않는다.

## 6. 기획 출력: 주장, 대안, Evidence 연결

### 제안 내부 결과 구조

아래는 내부 설계 제안이며 현재 wire schema의 확정 변경은 아니다.

```text
PlanningReviewDraft
  request_id, draft_id, draft_schema_version, status, review_status
  request_scope: season / brand / category / market / channel / origin
  input_summary[]: producer / status / source_version / period / unit / limitations
  concepts[]
    concept_id, title, planning_intent
    claims[]: claim_id, text, kind, evidence_refs[], source_scope, confidence_note
    proposed_attributes[]: field, value, kind, evidence_refs[], open_questions[]
    relation_to_assortment: observed_matches[], observed_differences[], coverage_limits[]
    alternatives[]: difference_axes[], tradeoffs[], assumptions[], risks[]
    md_decisions[]: question, reason, owner_role, response_effect, status
  conflicts[], missing_information[], limitations[], errors[]
  decision_boundary: review_only, non_decisions[]
  provenance: raw_input_refs/hashes, adapter versions, retrieval/index version, generator version
```

Claim kind 후보는 `user_requested`, `evidence_observation`, `proposal`, `hypothesis`, `unknown`이다. 기존 코드에서 쓰는 `agent_proposal`, `to_validate`, `interpretation` 등과의 mapping은 backward compatibility review가 필요하며 무조건 enum을 교체하지 않는다. 제안 claim의 Evidence는 직접 뒷받침하는 ID만 연결한다. Evidence 없음은 `hypothesis`나 `unknown`으로 표현한다.

### 비교 원칙

- 비교 대안은 동일한 요청 scope와 입력 snapshot에 기초해야 한다.
- 옵션 수, 평가 점수, 가중치, 승자 추천은 MD가 업무 필요와 기준을 승인하기 전 고정하지 않는다.
- 차이가 데이터에서 관찰된 것인지 새 제안인지, 어떤 판단을 MD에게 맡기는지 분리한다.
- 기존 상품 coverage가 불완전하면 “상품 공백”이 아니라 “현재 조회 범위에서 확인되지 않음”으로 표현한다.
- Project_07 지표는 출처의 집계 단위와 의미를 그대로 참조한다. Project_06이 재집계하지 않는다.
- 응답 소비처(Project_08 UI)가 기존 필드에 의존하는지 확인하고, 새 구조는 versioned output 또는 additive migration으로 합의한다.

## 7. 생성, 검색 및 안전 경계

### 단계별 생성

1. **입력 이해**: 제한된 schema와 사용자 요청에서 명시된 범위만 추출. 미확정 값은 사용자 확인 대상으로 표시.
2. **검증/정규화**: version allowlist, type, units, dates, IDs, permissions, request ID를 확인. 오류 결과는 evidence로 사용하지 않음.
3. **근거 retrieval**: 허가된 가이드·taxonomy·과거 기획서만 검색. 상품/판매/시장 데이터 계산은 각 producer 소유.
4. **기획 분석**: Trend×category 적합성, 자사 구색 관계, 근거·충돌·coverage를 보여주되 매출 성공/시장 수요의 결론으로 승격하지 않음.
5. **대안 작성**: 근거가 충분하고 MD 업무에 필요할 때만 상이한 방향 제안. 불충분하면 초안 축소와 질문 우선.
6. **출력 검증**: schema, Evidence allowlist, claim kind, request scope, source status, value unit, prohibited decisions 검증.
7. **MD 검토**: 수정·보류·추가자료 요청·승인 등 상태 전이는 UI/workflow owner와 합의 후 제공.

현재 첫 두 단계 일부와 규칙 기반 scaffold, 합성 retrieval이 구현되어 있지만 단계 3은 운영 corpus 미연결, 대안 생성/현업 판단 품질은 검증되지 않았다. 텍스트 LLM provider는 현재 실제 연결되지 않았다. 모델을 도입해도 prompt injection 방어가 완전하다고 주장하지 않고 tool/network/file 권한을 기본 차단한다.

## 8. 평가와 고객 증거 계획

### 평가 트랙 분리

| 트랙 | 무엇을 입증하는가 | 데이터/평가자 | 결과를 주장할 수 있는 범위 |
|---|---|---|---|
| 계약·adapter test | 입력 버전, 변환, raw trace, 오류 동작의 구현 정확성 | 합성 fixture와 mock | 해당 fixture/contract 사례의 처리만 |
| 생성기 자동 평가 | 상태·schema·Evidence ID·scope·금지 판단 준수 | 고정 합성 set, deterministic checks | 지정 set의 자동 검증 결과만 |
| MD blind review | 초안 유용성·근거·편집 가능성·업무 적합성 | 현업 MD, 승인된 검토 set | 평가 참여자·카테고리·사례 범위에 한정 |
| 고객 파일럿 | 실제 업무 맥락에서의 운영성과/효용 | 고객 승인 자료, baseline, 기간, 측정 담당 | 해당 고객/업무/기간의 관찰 결과만 |

### 합성 평가 set과 루브릭

고정 합성 set은 여러 카테고리(예: 상의·하의·아우터·잡화), 시즌, scope 명시/누락, Trend·재고·판매 결과 상태(`ok/partial/no_results/error`), 충돌, 구색 coverage 부족, 단위/기간 변형, prompt injection 문구를 포함한다. 각 사례에는 입력 raw snapshot, 지원 schema version, 기대 status 처리, 허용 claim/금지 claim, Evidence allowlist, MD 검토 질문을 기록한다.

MD 평가는 출력 순서를 무작위화하고 엔진 이름을 가린 뒤 다음 차원을 개별 평가한다: 업무 관련성, 요청 충족, 대안 차이의 실질성, 근거 연결 정확성, 불확실성 정직성, 수정 가능성, 필요한 질문, 읽기/편집 부담. 평가자간 차이는 단순 평균만으로 숨기지 않고 사례별 의견과 불일치를 남긴다. 점수 정의·통과선은 MD 및 제품 책임자 승인 전 TBD다.

출시 전 최소 통과 조건 후보: unsupported factual claims 0 허용 사례에서 0건, Evidence ID 미등록 0건, scope/schema 위반 0건, 치명적 권한 누출 0건, 각 target category에서 MD 유용성 기준을 사전 합의된 수준 이상 충족. 실제 수치·표본·신뢰수준은 평가자와 합의 후 정한다. 기준이 정해지지 않으면 “평가 통과”라고 하지 않는다.

현재 테스트는 parser·domain behavior·경계 조건을 검증한다. 실제 MD blind review나 고객 파일럿이 완료된 것은 아니다. synthetic 결과는 실제 회사의 실제 데이터 성능을 대변하지 않는다.

## 9. 기업 고객 도입 준비도

| 주제 | 현재 상태 | 파일럿/운영 전에 필요한 일 | 승인 주체 후보 |
|---|---|---|---|
| Transport/API | `/runs` `vogue-handoff/0.3`; local/private/service HTTP 보안 모드 | 운영 배포의 ingress/TLS 경계와 cross-project contract 동결 검증 | Project_06/08, platform |
| Auth/secret | service mode Bearer token 검사 | 발급자·audience·rotation·secret store·폐기/감사 | security/platform |
| Tenant isolation | 업무 데이터 tenant model 확인 불가 | 모든 DB/index/cache/log/request에 tenant scope 강제 및 교차 tenant 시험 | 고객 보안, platform |
| 사내 문서 권한 | 합성 corpus 정책만; 운영 index 미연결 | source ACL 상속, 사용자별 retrieval filter, 삭제/권한 철회 전파, 허가 문서 목록 | 고객 data owner/security |
| Data retention/deletion | persistent handoff trace 정책 미합의 | 요청/원본/embedding/output retention·삭제·backup 만료 정의 | 고객 data owner/legal |
| 개인정보/기밀 | 원문 log 금지 일부 구현 | 분류, 최소수집, redaction, 지역, DPA/처리목적 승인 | 고객 privacy/security |
| 모델 전송 | 텍스트 모델 provider 미연결, 이미지 API 선택 경로 존재 | 어떤 필드가 어디로 전송되는지 allowlist, no-train/retention 조건, 고객 opt-in | 고객/security/product |
| Audit/observability | 개발 테스트 수준 | 사용자·tenant·adapter/model/version/status 중심 최소 감사, 원문/secret 제외 | platform/security |
| Availability/recovery | 로컬 prototype | SLO, rate limit, queue, circuit breaker, backup/restore, incident runbook | SRE/product |
| Idempotency/retry | `/runs`는 request ID와 payload hash로 완료 응답을 재사용하고, 다른 payload 재사용 및 불확실한 이미지 재시도를 거부. 자동 provider retry 없음 | 다중 인스턴스 운영 보장과 retention 정책은 별도 검증 필요 | Project_06/08 |
| Timeout/cost | 이미지 호출 timeout 기본 180초(5–300초 범위); 호출자 HTTP deadline은 P08 소유 | end-to-end deadline propagation, 공급자 제한과 비용 운영 기준은 별도 합의 필요 | Project_06/08/platform |
| Human approval | `md_review_required` | UI 권한, review state transition, 승인 이력, 자동 채택 금지 확인 | MD workflow owner/Project_08 |

운영 전 보안 검토, 고객 데이터 처리 승인, 자료 사용권 확인, 삭제 테스트, tenant 침투 테스트가 필요하다. 코드상 설정이 존재하는 것과 생산 운영 승인·적합성 검증은 별개다.

## 10. 단계별 로드맵과 완료 기준

| 단계 | 작업 | 선행 결정 | 완료 기준 |
|---|---|---|---|
| A. 업무 발견 | MD 인터뷰, 실제 기획 단계 지도, 기존 수작업 baseline 설계 | 고객 참여·자료 관찰 허가 | 역할별 workflow, 문제 가설, 테스트 가능한 업무 성공 지표와 미결정 목록 |
| B. 입력 계약 카탈로그 | 현 upstream version/field/unit/owner/permissions 목록과 fixture 정리 | 각 producer owner sanitized schema/fixture 제공 | 승인된 source/version matrix, unknown/zero/error semantics, raw retention 승인 |
| C. adapter registry | producer별 parser·version mapping·warning·trace 모델 분리 | B 승인 | 지원 fixture 통과, unknown version/field는 silent drop 없이 오류/검토 표시 |
| D. 기획 review model | concept alternatives, claim/evidence, tradeoff, question, review state를 표현할 내부 구조 | MD와 Project_08 소비처 합의 | backward compatibility plan, fixture snapshots, output validation |
| E. 검색/자료 거버넌스 | 승인 corpus, tenant/access filters, provenance and deletion | 고객 자료 사용권·ACL owner 승인 | unauthorized retrieval 0건, provenance/deletion tests, index version trace |
| F. 평가 baseline | synthetic suite 확장, MD blind review rubric/prior baseline | 평가자와 점수/통과선 승인 | 사례 및 평가 계획 동결; 점수와 불일치 재현 가능 |
| G. 제한 파일럿 | 한 고객/한 업무범위/승인 자료로 shadow 또는 human-in-loop pilot | security/legal/operations approvals | agreed metrics, failure handling, rollback, user acceptance |
| H. 제품 운영 | multi-tenant, SLO, audit, support, lifecycle | pilot outcome and production review | 운영 책임자, support/runbook, monitoring/restore/access reviews 완료 |

다른 프로젝트 소유 schema나 업무정책 변경은 해당 owner의 명시 승인 뒤 별도 저장소 작업으로 한다. 이 문서 자체는 공통 API schema 또는 모든 입력 지원을 승인하지 않는다.

## 11. 미결정과 담당자 확인 목록

1. 우선 고객군·브랜드 규모·카테고리와 첫 파일럿 업무는 무엇인가? (제품/영업 + MD)
2. MD가 실제로 비교해야 하는 대안 수와 필수 비교 축은 무엇인가? (현업 MD)
3. 사용할 사내 자료 유형별 소유자·권리·필드 dictionary·보존 규칙은 무엇인가? (고객 data owner/security)
4. Trend/Stock/Project_07의 sanitized schema fixture, producer ID, version governance 주체는 누구인가? (producer owners)
5. Project_07 지표 중 Project_06 초안에서 원본 그대로 보여줄 field와 세부 meaning은 무엇인가? (Project_07/MD)
6. 고객별 tenancy, 검색 권한, 외부 model 전송 허용 여부를 어떤 계약·기술로 보장할 것인가? (security/legal/platform)
7. Project_08 UI에서 raw trace 접근 권한, 편집, review state와 export는 어떻게 동작하는가? (Project_08/MD)
8. MD 평가 참여자, baseline, 점수 정의, 통과선, 불일치 분석 방법은 무엇인가? (MD/product)
9. 제품 운영 SLO, retry/idempotency, retention/deletion 및 incident owner는 누구인가? (SRE/product/security)

## 12. 문서 변경 이력과 구현 경계

이 문서는 설계 기준을 한 곳에 정리한 초안이다. 기존 MD 적합성, data/evidence, RAG, generator evaluation, handoff 문서는 도메인 상세 설명의 원본으로 유지한다. 이 문서 추가는 runtime 코드, wire schema, producer contract, service setting, external data source를 변경하지 않는다. 테스트 결과나 고객 효과 수치는 새로 주장하지 않는다.
