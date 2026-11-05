# VOGUE New Product Planning Agent

VOGUE 프로젝트의 3번 **New Product Planning Agent**를 구현하는 저장소입니다.

## 범위

- 현재 작업: 상품·판매 자료와 트렌드·고객 의견·재고 근거를 활용해 MD/디자이너가 검토하고 수정할 수 있는 신상품 브리프와 이미지 시안 흐름을 프로토타입으로 구현합니다.
- 로컬 UI의 기회 분석·문서·재고·고객 의견 자료는 모두 가상 fixture이며 Kaggle 데이터 또는 실제 회사 데이터와 혼합하지 않습니다.
- H&M Kaggle 파이프라인은 실제로 내려받은 상품 마스터와 거래 이력을 로컬 처리하고, 결과를 합성 데모와 분리된 **H&M 데이터** 화면에 표시합니다.
- 내부 입력 모델: 필수 `SalesAnalysisResult`, `TrendResult`, `PlanningRequest`, `InventoryProductResult`
- 내부 출력: `ProductConceptDraft`; 공통 `ProductConcept` adapter는 계약 합의 후 연결
- H&M 내부 상품·판매 실적 분석을 포함합니다. 경쟁상품 조사는 현재 범위에서 제외합니다.
- 원가·마진, 생산·조달, 고객 피드백 분석은 이 에이전트에서 구현하지 않습니다.

## 저장소 경계

이 저장소는 3번 **New Product Planning Agent**만 담당합니다. 4번 **Product Feasibility Agent**는 추후 별도 신규 저장소에서 진행하기로 합의했습니다. 두 에이전트 간 연동은 공통 계약으로 맞추며, 4번 에이전트 코드를 이 저장소에 추가하지 않습니다.

## 기술 선택

초기 구현은 표준 라이브러리만 쓰는 Python 도메인 코어와 결정적 규칙 기반 콘셉트 초안 생성기를 기준선으로 사용합니다. 목표는 전달받은 자료와 Evidence를 근거로 LLM이 상품 콘셉트를 생성하고, 여러 생성 엔진을 같은 컨텍스트에서 비교해 품질을 개선하는 것입니다. 공통 wire schema, API 프로토콜, 허용 생성 모델, 데이터 전송 범위와 운영 런타임은 확정하지 않았습니다. 선택 근거와 통합 시 변경 경계는 [임시 구현 기본값 ADR](docs/decisions/adr-0001-provisional-implementation-defaults.md)에 기록했습니다.

## RAG·LLM 경계와 설정

VOGUE 전체 흐름은 RAG 기반 LLM 에이전트 시스템입니다. 이 저장소의 3번 에이전트는 1번 Query & Trend Agent의 `TrendResult`, 2번 에이전트의 상품·재고 결과, 그리고 H&M Kaggle 파일에서 만든 버전·기간이 명시된 상품/판매 Evidence를 사용합니다. Kaggle 데이터는 로컬 배치 처리로 수집하며 실시간 운영 API로 취급하지 않습니다. 현재 `ConceptGenerator` 포트에는 결정적 기준선이 연결되어 있습니다. 향후 같은 정규화 입력과 Evidence를 여러 허용 엔진에 제공하고, 근거성·요청 준수·MD 유용성 등을 별도로 평가합니다.

로컬 API 키 파일은 `.env`이며 현재 `LLM_API_KEY` 값은 비어 있습니다. `.env`는 Git에서 제외됩니다. 복제한 팀원이 참고할 수 있는 [`.env.example`](.env.example)도 제공합니다. 여러 엔진 연결 시 사용할 환경 변수 별칭과 설정은 엔진 선택 후 정하며, 실제 키를 Git에 올리지 않습니다. `requirements.txt`에는 `.env`를 읽기 위한 `python-dotenv`만 넣었으며, 모델 제공자가 결정되기 전까지 LLM SDK는 설치하지 않습니다. 설정을 읽는 [load_settings](src/vogue_npp/settings.py)는 키를 출력하거나 네트워크 요청을 보내지 않습니다.

## 프로젝트 문서

- [Project Overview](https://app.notion.com/p/40d3269b1acd809c98c5dc5de4f61d24)
- [Project Workflow](https://app.notion.com/p/40f3269b1acd81378143f35b599ef9a0)
- [저장소 분리 협업 가이드](https://app.notion.com/p/40e3269b1acd81489fecc1052e033b54)

Agent 3의 데이터 출처·Evidence 경계는 [데이터·Evidence 계획](docs/design/data-source-and-evidence-plan.md)에, Kaggle 원본의 수집·정제·집계 설계는 [H&M Kaggle 처리 계획](docs/design/hm-kaggle-data-pipeline.md)에 정리했습니다. 원본과 파생 데이터는 `data/` 아래에 저장하고 Git에서 제외합니다.

네 입력의 중요도 순서(판매 분석 → 트렌드 → 사용자 쿼리 → 자사 상품·재고), 내부 모델 매핑과 실패 동작은 [입력·출력 처리 흐름](docs/design/input-output-processing-flow.md)을 참고하세요. 네 입력은 모두 필수이며, `InventoryProductResult`에서 재고 필드가 부분적으로 비면 상태와 제한을 보존합니다. 외부 공통 계약 어댑터는 합의 후 연결합니다.

가공된 H&M Style 판매 요약은 `load_hm_sales_analysis()`로 `SalesAnalysisResult`에 매핑할 수 있습니다. Kaggle 상품 분류를 요청 카테고리로 연결하는 `source_category_map`과 `category_mapping_version`은 프로젝트 taxonomy와 대조해 호출자가 명시해야 하며, 데이터에 없는 시즌이나 채널 의미를 자동 추정하지 않습니다.

현재 처리 산출물의 데이터 품질과 Style 대표 분류의 유형별 편차는 아래 명령으로 재현할 수 있습니다. 결과 JSON에는 스키마·결측·중복·article 연결 상태, 판매 집계 행 수, 카탈로그 분류 충돌 및 Article 기준과 Style 대표 분류 기준의 유형별 차이가 기록됩니다.

```bash
PYTHONPATH=src python3 -m vogue_npp.sources.hm.hm_quality
```

기본 결과는 `data/processed/hm-personalized-fashion-recommendations/hm_quality_report.json`에 생성됩니다. 상품유형별 정확한 판매 집계는 `article_id`로 주간 판매 집계와 카탈로그를 연결한 기준을 사용해야 합니다. `style_sales_summary.csv`의 대표 분류는 스타일 내 상품유형이 복수인 경우 유형별 판매 분모로 사용할 수 없습니다.

다운로드한 H&M competition ZIP 또는 압축 해제한 CSV를 `data/raw/hm-personalized-fashion-recommendations/`에 두고 아래 명령을 실행하면 상품 마스터·주간 구매 집계·Style/카테고리/색상/채널 분석까지 수행합니다. ZIP은 이미지 파일을 풀지 않고 필요한 CSV만 순차 처리합니다. 파이프라인은 표준 라이브러리로 동작하고 고객 식별자를 파생 파일에 쓰지 않습니다.

```bash
PYTHONPATH=src python3 -m vogue_npp.sources.hm.hm_data
```

이 명령은 처리·기본 분석에 더해 131개 상품유형의 Article 기준 시즌성·연도별 추세·색상·상대 원천 가격대·채널·스타일 집중도와 근거 연결 기획 후보도 생성합니다. 기존 처리 결과만 다시 분석하려면 다음 명령을 실행할 수 있습니다.

```bash
PYTHONPATH=src python3 -m vogue_npp.sources.hm.hm_planning_analysis
```

결과 `hm_planning_analysis.json`은 UI의 **상품유형 전체 분석**에 제공됩니다. MD가 후보 선택 근거를 저장하거나 선택 후보의 결정적 브리프 초안을 생성하면 합성 데모 브리프와 분리된 `hm_planning_reviews`/`hm_planning_briefs` 테이블에 보존됩니다. 브리프는 Evidence 사실, MD 가설, unknown을 구분하고 이미지 생성 입력 JSON을 만듭니다. 실제 LLM·이미지 생성 API 호출은 하지 않습니다. 판매 월은 월요일 시작 주의 시작월이며, 실제 MD 시즌으로 추정하지 않습니다. 연도별 변화는 불완전한 연도와 상품 노출 기간을 보정하지 않은 서술 통계입니다. 상대 가격 구간은 원천 수치 분위 구간으로, 통화나 판매가 제안이 아닙니다. 기획 후보는 과거 판매 규모를 탐색하는 용도입니다.

결과는 Git에서 제외되는 `data/processed/hm-personalized-fashion-recommendations/` 아래 상품 카탈로그, 주간 거래 집계, Style·상품군·색상·채널·월별 분석 CSV, `hm_analysis.json`, `manifest.json`으로 생성됩니다. 완료된 실제 파일 점검과 제한은 [H&M Kaggle 처리 계획](docs/design/hm-kaggle-data-pipeline.md)에 기록했습니다. 분석 산출물은 아래 웹 앱의 **H&M 데이터** 섹션에 합성 데모와 분리해 표시합니다.

## MD용 로컬 프로토타입 실행

별도의 설치 없이 저장소 루트에서 실행하세요.

```bash
PYTHONPATH=src python3 -m vogue_npp.prototype.server
```

브라우저에서 [http://127.0.0.1:8765](http://127.0.0.1:8765)을 열면 카테고리·시즌 선택, 수치 기반 기회 탐색, 문서 검색과 근거 확인, 브리프 편집/버전 관리, 이미지 시안 비교, MD/디자이너 평가 이력을 한 흐름으로 시연할 수 있습니다. 생성 모델로 만든 실제 의류 콘셉트 사진 1개가 포함되며, 추가 시안은 API 키 없이 로컬 SVG 목업으로 생성됩니다. 서버는 이 컴퓨터 내부 주소에만 바인딩합니다. 중지하려면 실행 터미널에서 `Ctrl+C`를 누르세요.

브라우저 결과와 데이터 흐름·fixture 스키마·지표 산식·제한사항은 [프로토타입 실행·설계 안내](docs/design/prototype-runbook.md)에 문서화했습니다. 화면의 브리프·시안·평가는 로컬 Git 제외 SQLite 파일 `data/local/prototype.sqlite3`에 기록됩니다. 실제 Kaggle의 과거 상품·거래 분석은 별도 섹션에서 조회하며, 합성 재고/리뷰/트렌드 또는 기획 브리프와 자동 병합하지 않습니다. 포함된 ImageGen 사진은 프로젝트에 고정된 콘셉트 예시이며 앱에서 외부 이미지 API를 실시간 호출하지 않습니다.

### Docker로 실행

Docker Compose를 설치한 뒤 저장소 루트에서 실행합니다.

```bash
docker compose up --build -d
```

브라우저에서 [http://127.0.0.1:8765](http://127.0.0.1:8765)을 엽니다. 중지하려면 `docker compose down`을 실행하세요. 브리프·시안·검토 기록은 Compose named volume에 보존되고, H&M 처리 결과는 호스트의 `data/processed/hm-personalized-fashion-recommendations/`에서 읽기 전용으로 마운트됩니다. Kaggle 원본·가공 파일과 `.env`는 이미지에 복사되지 않습니다. H&M 데이터가 아직 없더라도 앱은 실행되며 해당 화면에 분석 산출물 부재를 표시합니다.

## 설계 상태

### 실제 데이터 상품기획 흐름 상태

로컬 프로토타입은 H&M 과거 Article 거래 근거 조회, 후보 선택/반대근거 저장, Evidence와 가설을 구분하는 버전형 기획 브리프, 브리프별 사람 검토 기록까지 지원합니다. 브리프 생성은 결정적 템플릿이며 실제 H&M의 승인된 내부 RAG, 트렌드·재고·원가·고객 데이터, 사용자 인증, LLM/이미지 공급자 연결은 아직 없습니다. 따라서 운영용 상품기획 시스템 완료 상태가 아닙니다. 다음 제품화 단계의 데이터 권한, 로그인/역할, 보존·삭제, 모델 공급자/비용, 이미지 권리, 배포 및 모니터링은 [H&M 데이터 흐름 문서](docs/design/hm-kaggle-data-pipeline.md)의 미완료 경계를 기준으로 결정해야 합니다.

에이전트 입력·출력 계약과 향후 통합 경계는 [New Product Planning Agent 설계 제안](docs/design/new-product-planning-agent.md)에 정리했습니다. 도메인 코어는 기존 입력 정합성 검사, 기획 기회 비교, 내부 콘셉트 초안 생성과 출처 안전 검사를 유지합니다. 별도 로컬 웹 프로토타입은 가상 자료에서만 브리프·평가 흐름을 시연하며, 공통 에이전트 API나 운영용 LLM 생성기로 간주하지 않습니다.

Notion 요구사항을 기준으로 한 다음 구현 순서와 통합 경계는 [향후 작업 설계](docs/design/implementation-roadmap.md)에 정리했습니다.

### 폴더 구조

경계 설명과 canonical 명령은 [프로젝트 구조 가이드](docs/design/project-structure.md)를 참고하세요.

```text
project_06/
├── data/                         # 원본·가공 산출물·로컬 상태 (대용량/개인 상태는 Git 제외)
│   ├── raw/hm-personalized-fashion-recommendations/
│   ├── processed/hm-personalized-fashion-recommendations/
│   └── local/
├── docs/
│   ├── design/                   # 시스템 및 데이터 흐름 설계
│   └── decisions/                # 구현 결정 기록
├── examples/                     # 실행 가능한 합성 데모와 fixture
├── src/vogue_npp/
│   ├── domain/                   # 입력 계약, 분석, 콘셉트, 생성 규칙
│   ├── sources/hm/               # H&M 원천 처리·품질 점검·분석·adapter
│   ├── workflows/                # 상품기획 브리프 및 의사결정 흐름
│   ├── prototype/                # 로컬 웹 서버, UI 지원 API, 저장소, 검색
│   ├── settings.py               # 공통 실행 설정
│   └── __init__.py               # 외부에서 사용할 도메인 API 공개
├── tests/                        # 회귀 및 데이터 경계 검증
└── web/prototype/                # 로컬 프로토타입 UI와 정적 이미지
```

새 코드는 `domain`, `sources.hm`, `workflows`, `prototype`의 경계를 따릅니다. 패키지 루트는 공개 API와 공통 설정만 제공합니다. 모든 모듈 및 실행 경로는 한 곳에만 두고, README와 데이터 파이프라인 문서의 실행 명령은 canonical package 경로를 사용합니다.

### 주요 코드 위치

- `src/vogue_npp/domain/`: 정규화 입력 계약, 근거 기반 분석, 내부 콘셉트 모델과 생성기
- `src/vogue_npp/sources/hm/`: Kaggle 로컬 데이터 처리·품질 감사·상품유형 분석·판매 adapter
- `src/vogue_npp/workflows/`: 후보 검토에서 버전형 기획 브리프까지의 업무 흐름
- `src/vogue_npp/prototype/`: HTTP 서버, API, fixture, SQLite 저장 및 근거 검색
- `web/prototype/`: 로컬 UI. API 서버와 분리된 화면 자산

## 호출 형태

아래는 도메인 함수의 호출 형태를 보여주는 축약 예시입니다. `...`는 사전에 정규화한 입력 객체를 뜻하며 실행 가능한 코드는 아래 합성 데모입니다. 실제 공통 wire payload 어댑터는 계약 합의 후 추가합니다.

```python
from vogue_npp import PlanningInputs, build_planning_context, generate_concept_draft

inputs = PlanningInputs(request=..., trend=..., sales=..., inventory=...)  # all four normalized inputs
context = build_planning_context(inputs)
draft, validation_issues = generate_concept_draft(context)
```

`draft`는 내부 검토 모델이며 입력별 상태, 충돌, Evidence ID와 제한사항을 보존합니다. 이를 공통 `ProductConcept` 응답으로 직렬화하는 코드는 아직 없습니다.

합성 입력으로 전체 흐름을 출력하는 예제는 다음과 같이 실행합니다. 예제 안의 상품·트렌드 ID와 재고 값은 모두 가상이며 실제 데이터로 사용하면 안 됩니다.

```bash
python3 -m pip install -r requirements.txt
PYTHONPATH=src python3 examples/synthetic_demo.py
```

복수 엔진 비교 방식, 근거성·요청 준수·MD 유용성 지표와 아직 측정하지 않은 항목은 [근거 기반 생성 및 엔진 비교 평가 계획](docs/design/generator-evaluation-plan.md)에 적었습니다.
