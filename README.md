# VOGUE New Product Planning Agent

VOGUE 프로젝트의 3번 **New Product Planning Agent**를 구현하는 저장소입니다.

## 범위

- 현재 작업: 요청, 근거 기반 트렌드 결과, 자사 상품·현재 재고 결과를 바탕으로 검토 가능한 신상품 콘셉트를 제안합니다.
- 입력 계약: `PlanningRequest`, `TrendResult`, `InventoryProductResult`
- 출력 계약: `ProductConcept`
- 경쟁상품 조사와 판매량 분석은 현재 MVP 범위에서 제외합니다.
- 원가·마진, 생산·조달, 고객 피드백 분석은 이 에이전트에서 구현하지 않습니다.

## 저장소 경계

이 저장소는 3번 **New Product Planning Agent**만 담당합니다. 4번 **Product Feasibility Agent**는 추후 별도 신규 저장소에서 진행하기로 합의했습니다. 두 에이전트 간 연동은 공통 계약으로 맞추며, 4번 에이전트 코드를 이 저장소에 추가하지 않습니다.

## 기술 선택

초기 구현은 표준 라이브러리만 쓰는 Python 도메인 코어와 결정적 규칙 기반 콘셉트 초안 생성기를 임시 기본값으로 사용합니다. 공통 wire schema, API 프로토콜, 생성 모델, 데이터 소스와 운영 런타임은 확정하지 않았습니다. 선택 근거와 통합 시 변경 경계는 [임시 구현 기본값 ADR](docs/decisions/adr-0001-provisional-implementation-defaults.md)에 기록했습니다.

## RAG·LLM 경계와 설정

VOGUE 전체 흐름은 RAG 기반 LLM 에이전트 시스템입니다. 이 저장소의 3번 에이전트는 1번 Query & Trend Agent가 검색해 전달한 `TrendResult` Evidence와 2번 에이전트의 자사 상품·재고 결과를 사용합니다. 트렌드/상품 인덱스와 원천 데이터 조회는 소유하지 않습니다. 현재 `ConceptGenerator` 포트에는 결정적 규칙 기반 구현체를 연결했고, 승인된 제공자·모델·보안 조건이 정해진 뒤 Evidence-grounded LLM 구현체를 추가할 수 있습니다.

로컬 API 키 파일은 `.env`이며 현재 `LLM_API_KEY` 값은 비어 있습니다. `.env`는 Git에서 제외됩니다. 복제한 팀원이 참고할 수 있는 [`.env.example`](.env.example)도 제공합니다. `requirements.txt`에는 `.env`를 읽기 위한 `python-dotenv`만 넣었으며, 모델 제공자가 결정되기 전까지 LLM SDK는 설치하지 않습니다. 설정을 읽는 [load_settings](src/vogue_npp/settings.py)는 키를 출력하거나 네트워크 요청을 보내지 않습니다.

## 프로젝트 문서

- [Project Overview](https://app.notion.com/p/40d3269b1acd809c98c5dc5de4f61d24)
- [Project Workflow](https://app.notion.com/p/40f3269b1acd81378143f35b599ef9a0)
- [저장소 분리 협업 가이드](https://app.notion.com/p/40e3269b1acd81489fecc1052e033b54)

## 설계 상태

구현 경계와 계약 공백은 [New Product Planning Agent 설계 제안](docs/design/new-product-planning-agent.md)에 정리했습니다. `src/vogue_npp`에는 입력 정합성 검사, 기획 기회 비교, 내부 콘셉트 초안 생성과 출처 안전 검사가 있습니다. 현재 generator는 입력으로 받은 사용자 조건과 Evidence를 정리하는 검토용 뼈대이며, 운영용 LLM 생성기나 외부 API가 아닙니다.

Notion 요구사항을 기준으로 한 다음 구현 순서와 통합 경계는 [향후 작업 설계](docs/design/implementation-roadmap.md)에 정리했습니다.

## 호출 형태

아래는 도메인 함수의 호출 형태를 보여주는 축약 예시입니다. `...`는 사전에 정규화한 입력 객체를 뜻하며 실행 가능한 코드는 아래 합성 데모입니다. 실제 공통 wire payload 어댑터는 계약 합의 후 추가합니다.

```python
from vogue_npp import PlanningInputs, build_planning_context, generate_concept_draft

inputs = PlanningInputs(request=..., trend=..., inventory=...)  # normalized internal models
context = build_planning_context(inputs)
draft, validation_issues = generate_concept_draft(context)
```

`draft`는 내부 검토 모델이며 입력별 상태, 충돌, Evidence ID와 제한사항을 보존합니다. 이를 공통 `ProductConcept` 응답으로 직렬화하는 코드는 아직 없습니다.

합성 입력으로 전체 흐름을 출력하는 예제는 다음과 같이 실행합니다. 예제 안의 상품·트렌드 ID와 재고 값은 모두 가상이며 실제 데이터로 사용하면 안 됩니다.

```bash
python3 -m pip install -r requirements.txt
PYTHONPATH=src python3 examples/synthetic_demo.py
```

초안 품질 시나리오와 아직 측정하지 않은 항목은 [초안 생성 평가 계획](docs/design/generator-evaluation-plan.md)에 적었습니다.
