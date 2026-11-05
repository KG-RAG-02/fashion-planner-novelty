# ADR 0001: 임시 구현 기본값

- 상태: 임시 적용 · 팀 통합 시 재검토
- 날짜: 2026-11-05
- 범위: `new-product-planning-agent` 저장소 내부 도메인 코어
- 근거 문서: Notion Project Overview, Project Workflow, 저장소 분리 협업 가이드, API Design

## 맥락

기본 워크플로우는 3번 에이전트의 입력을 `PlanningRequest`, `TrendResult`, `InventoryProductResult`, 출력을 `ProductConcept`으로 정의합니다. 이 ADR 작성 당시 경쟁상품·판매량 분석은 제외되어 있었습니다. 사용자는 이후 H&M 소속 MD 페르소나와 H&M Kaggle 자료를 확정하고, 로컬 데이터 수집·판매 실적 분석을 포함하도록 범위를 갱신했습니다. 현재 사용자 요청과 [H&M Kaggle 처리 계획](../design/hm-kaggle-data-pipeline.md)이 이 항목의 최신 결정입니다. 경쟁상품 조사 및 4번 에이전트의 원가·생산·조달·고객 피드백 분석은 여전히 제외합니다.

API Design에서 최종 wire schema의 상세 필드, 전송, 인증, timeout/retry는 미정입니다. 공통 계약 파일은 모든 에이전트 저장소에 같은 경로·내용·버전으로 복제하고, 단일 기준 저장소를 만들지 않는다는 팀 결정이 있습니다. 이 때문에 구현을 멈추지 않으면서도 임의의 wire schema를 고착시키지 않을 내부 기본값이 필요합니다.

## 결정

1. **언어/의존성:** 도메인 코어는 Python 표준 라이브러리 중심으로 유지합니다. 로컬 `.env` 읽기용 `python-dotenv`만 추가하고, 별도 웹 프레임워크·모델 SDK·데이터베이스 드라이버는 제공자/운영 방식을 선택할 때까지 추가하지 않습니다.
2. **도메인 경계:** 내부 dataclass 모델과 순수 함수로 입력 정합성, 콘텍스트 조립, 초안 생성 및 provenance shape 검사를 분리합니다.
3. **초안 생성:** 첫 구현은 결정적 규칙 기반 생성기입니다. 요청에서 명시된 속성과 Evidence가 연결된 트렌드 속성을 정리해 검토용 콘셉트 초안을 만듭니다.
4. **RAG/LLM 경계:** 프로젝트 전체에서 트렌드 검색/RAG 인덱스는 Query & Trend Agent 책임입니다. 이 Agent는 전달된 Evidence만 사용하며 `ConceptGenerator` 포트 뒤에 현재 규칙 생성기를 둡니다. 승인된 모델을 고른 뒤 해당 포트에 Evidence-grounded LLM 구현을 추가할 수 있습니다.
5. **주장 정책:** 판매 집계는 Kaggle 원천의 관측 기간·필터·정의가 보존된 과거 관찰로 사용합니다. 이를 미래 수요나 인과적 고객 니즈로 확대하지 않습니다. 입력에 없는 가격 기준·반품·품절·생산 가능성은 unknown 또는 검증 질문으로 남깁니다. 재고는 기준 시점 스냅샷으로 취급합니다.
6. **통신/저장:** live operational API와 외부 모델 호출은 하지 않습니다. 승인된 Kaggle competition 파일은 프로젝트의 Git-ignored `data/raw/`에 내려받고, 재현 가능한 로컬 배치 수집·처리 경계를 별도 설계합니다. 실패·부분 상태는 도메인 결과와 검증 이슈로 호출자에게 보존합니다.
7. **입력 상태:** 상태는 에이전트 ID가 아니라 `planning_request`, `trend_result`, `inventory_product_result` 입력 슬롯별로 보존합니다. 같은 Query & Trend Agent가 요청 구조체와 트렌드 결과를 모두 만들 수 있기 때문입니다.
8. **공통 계약:** 이 저장소에서 별도 `contracts/` 또는 public ProductConcept serializer를 만들지 않습니다. 합의된 동일 계약 파일이 준비되면 transport/contract adapter를 추가합니다.
9. **후속 에이전트:** Product Feasibility Agent는 이후 별도 저장소에서 진행합니다. 이 저장소의 범위에 포함하지 않습니다.

## 고려한 대안

| 대안 | 장점 | 이번 단계에서 보류한 이유 |
| --- | --- | --- |
| 즉시 특정 LLM SDK를 도메인 코드에 도입 | 자연어 콘셉트 표현이 풍부함 | 제공자, 데이터 전송, 평가 기준, 비용·보안 조건이 미정이고 모델 코드와 도메인이 결합됨 |
| 공통 wire schema를 임의 확정 | API 예시를 빠르게 작성 가능 | 팀의 다섯 저장소 계약 동기화 결정을 앞서가며 통합 때 호환성 비용을 만듦 |
| API/framework부터 구현 | 서비스 호출 형태를 일찍 확인 가능 | 전송 프로토콜과 인증이 미정이라 도메인 로직과 결합될 수 있음 |
| 구현 대기 | 임시 결정이 없음 | 독립적으로 검토 가능한 핵심 기획 흐름까지 멈추게 됨 |

## 통합 시 변경 경계

```text
공통 wire payload
    ↕ 합의된 계약/transport adapter
내부 PlanningInputs → ProductPlanningContext → ProductConceptDraft
```

- 공통 schema와 버전 규칙이 정해지면 입력 adapter에서 wire payload를 현재 내부 모델로 매핑합니다.
- 출력 adapter에서 내부 초안과 상태·Evidence·제한을 합의된 `ProductConcept` envelope에 매핑합니다.
- 합의 계약 파일은 같은 PR 묶음으로 모든 에이전트 저장소에 반영하고, 이 저장소의 로컬 모델을 기준 스키마로 승격하지 않습니다.
- 생성 모델이 승인되면 `generate_concept_draft` 경계 뒤의 generator 구현을 교체하되, provenance 검증과 담당 범위 제한을 유지합니다.
- 승인된 LLM을 붙일 때는 최소 Evidence context만 전달하고, 모델이 반환한 Evidence ID를 입력 allowlist와 대조합니다. 모델이 만든 ID나 출처 정보는 근거로 받아들이지 않습니다.
- prompt/model/provider/version과 생성 설정은 평가 기록에 남기며, 키·민감 원문은 로그에 기록하지 않습니다.
- 로컬 credential은 `.env`의 일반 이름 `LLM_API_KEY`에서 읽고, SDK별 변수명 변환은 제공자 adapter에서 처리합니다. `.env`는 Git ignore 대상이며 실제 키는 커밋하지 않습니다.
- 팀의 언어 표준이 다르면 순수 도메인 동작을 다른 런타임으로 이전하고, wire 계약과 동작 사례로 호환성을 확인합니다.

## 위험 및 제약

- 규칙 기반 초안은 문장 품질과 콘셉트 독창성이 제한적이며, 시장성 평가가 아닙니다.
- 내부 모델은 공통 계약과 일치한다고 보장되지 않습니다.
- Evidence ID 참조 검사는 ID 존재 여부만 확인하며, 자료 권한·최신성·주장과 근거 사이의 의미적 타당성을 판정하지 않습니다.
- 실제 대표 입력과 승인된 기대 결과가 정해지기 전까지 품질 성능 수치를 주장하지 않습니다.

## 재검토 조건

팀이 언어·운영 런타임, 공통 schema, 전송 프로토콜, 생성 모델·평가 기준 또는 실제 입력 연결을 결정하면 이 ADR을 갱신하고 영향받는 adapter와 문서를 조정합니다.
