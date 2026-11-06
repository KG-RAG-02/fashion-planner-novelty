# VOGUE Project_06 Planning Agent

VOGUE **Project_06 기획안 에이전트(Planning Agent)**를 구현하는 저장소입니다. 상품 기회·콘셉트 생성과 근거 통합 `PlanningDraft` 작성, MD 검토 지원을 한 에이전트 책임으로 정렬 중입니다. 콘셉트는 기획안 내부 구성요소이며 별도 새 상품 생성 에이전트를 운영 단계로 두지 않습니다.

## 범위

- 현재 역할: `PlanningRequest`, `TrendResult`, `InventoryProductResult`, Project_07 판매·시장 결과를 입력으로 받아 Evidence 기반 상품 기회·콘셉트와 검토용 기획안 초안을 작성합니다.
- 목표 순서: 사용자 쿼리 → 쿼리·트렌드 에이전트 → 자사 상품·재고 에이전트 → Project_07 판매·시장 데이터 에이전트 → Project_06 기획안 에이전트 → MD 최종 판단.
- 로컬 UI의 기회 분석·문서·재고·고객 의견 자료는 모두 가상 fixture이며 Kaggle 데이터 또는 실제 회사 데이터와 혼합하지 않습니다. 이 합성 판매 분석 UI는 레거시 이관 검토 후에도 담당자 합의 전 유지합니다.
- 기존 H&M Kaggle 파이프라인은 실제로 내려받은 공개 상품 마스터와 과거 거래 이력을 로컬 처리하고, 결과를 합성 데모와 분리된 **H&M 데이터** 화면에 표시합니다. 이는 Project_06 운영 데이터 연결이 아닙니다. 판매 분석 책임은 Project_07로 조율할 이관 후보로 문서화했으며 합의 전 삭제·이동하지 않습니다.
- 핵심 내부 입력 모델: `PlanningRequest`, `TrendResult`, `InventoryProductResult`; Project_07 결과 입력은 담당자 합의 전 제안입니다.
- 내부 출력: `ProductConceptDraft`는 현재 호환 내부 모델. 목표 출력 `PlanningDraft`와 공통 adapter는 계약 합의 후 연결
- Project_06은 판매 원천을 조회하거나 판매·시장 분석을 소유하지 않습니다. 기존 H&M 분석 코드·UI·fixture는 보존 중이며 현 사용처/이관 후보를 [책임 맵](docs/design/agent-3-responsibility-map.md)에 기록했습니다.
- Project_06은 가격·원가·수량·발주·최종 채택을 확정하지 않습니다. MD가 최종 판단합니다.
- 원가·마진, 생산·조달, 고객 피드백 분석은 이 에이전트에서 구현하지 않습니다.

## 저장소 경계

이 저장소는 Project_06 **Planning Agent**를 담당합니다. Project_07은 **Sales & Market Data Agent** 역할이며 저장소명은 `market-research-agent`입니다. Project_07의 결과가 먼저 전달된 후 Project_06이 초안을 만듭니다. Project_07의 구현 범위, 자료원, 계약 필드와 이관 범위는 담당자 합의 전입니다.

## 기술 선택

초기 구현은 표준 라이브러리만 쓰는 Python 도메인 코어와 결정적 규칙 기반 콘셉트 초안 생성기를 기준선으로 사용합니다. 목표는 전달받은 자료와 Evidence를 근거로 LLM이 상품 콘셉트를 생성하고, 여러 생성 엔진을 같은 컨텍스트에서 비교해 품질을 개선하는 것입니다. 공통 wire schema, API 프로토콜, 허용 생성 모델, 데이터 전송 범위와 운영 런타임은 확정하지 않았습니다. 선택 근거와 통합 시 변경 경계는 [임시 구현 기본값 ADR](docs/decisions/adr-0001-provisional-implementation-defaults.md)에 기록했습니다.

## RAG·LLM 경계와 설정

VOGUE 전체 흐름은 RAG 기반 LLM 에이전트 시스템입니다. 이 저장소의 3번 에이전트는 1번 Query & Trend Agent의 `TrendResult`와 2번 에이전트의 상품·재고 결과를 핵심 입력으로 사용합니다. H&M Kaggle 과거 판매 분석은 선택형 로컬 확장으로 제공하며, 공통 에이전트 입력 계약이나 운영 데이터 연결이 아닙니다. Kaggle 데이터는 로컬 배치 처리로 수집하며 실시간 운영 API로 취급하지 않습니다. 현재 `ConceptGenerator` 포트에는 결정적 기준선이 연결되어 있습니다. 향후 같은 정규화 입력과 Evidence를 여러 허용 엔진에 제공하고, 근거성·요청 준수·MD 유용성 등을 별도로 평가합니다.

로컬 API 키 파일은 `.env`이며 현재 `LLM_API_KEY` 값은 비어 있습니다. `.env`는 Git에서 제외됩니다. 복제한 팀원이 참고할 수 있는 [`.env.example`](.env.example)도 제공합니다. 여러 엔진 연결 시 사용할 환경 변수 별칭과 설정은 엔진 선택 후 정하며, 실제 키를 Git에 올리지 않습니다. `requirements.txt`에는 `.env`를 읽기 위한 `python-dotenv`만 넣었으며, 모델 제공자가 결정되기 전까지 LLM SDK는 설치하지 않습니다. 설정을 읽는 [load_settings](src/vogue_npp/settings.py)는 키를 출력하거나 네트워크 요청을 보내지 않습니다.

## 프로젝트 문서

- [Project Overview](https://app.notion.com/p/40d3269b1acd809c98c5dc5de4f61d24)
- [Project Workflow](https://app.notion.com/p/40f3269b1acd81378143f35b599ef9a0)
- [저장소 분리 협업 가이드](https://app.notion.com/p/40e3269b1acd81489fecc1052e033b54)
- [Agent 3 책임 경계 및 현재 구현 대조](docs/design/agent-3-responsibility-map.md)

Agent 3의 데이터 출처·Evidence 경계는 [데이터·Evidence 계획](docs/design/data-source-and-evidence-plan.md)에, Kaggle 원본의 수집·정제·집계 설계는 [H&M Kaggle 처리 계획](docs/design/hm-kaggle-data-pipeline.md)에 정리했습니다. 원본과 파생 데이터는 `data/` 아래에 저장하고 Git에서 제외합니다.

세 핵심 입력의 내부 매핑과 실패 동작은 [입력·출력 처리 흐름](docs/design/input-output-processing-flow.md)을 참고하세요. 선택형 H&M 과거 판매 확장이 제공되면 추가 관찰로 검토하되, 미제공 시에도 핵심 입력만으로 초안을 만들고 판매 근거를 사용하지 않았음을 표시합니다. 입력 간 충돌은 임의로 해소하지 않습니다. 버전 지정된 상·하의 역할 분류 규칙으로 코디 관계가 명확한 경우에는 서로 다른 카테고리를 충돌 대신 별도 코디 맥락으로 기록합니다. `InventoryProductResult`의 재고 필드가 부분적으로 비면 상태와 제한을 보존합니다. 외부 공통 계약 어댑터는 합의 후 연결합니다.

기존 H&M Style 판매 요약은 `load_hm_sales_analysis()`로 내부 `SalesAnalysisResult`에 매핑할 수 있습니다. 이는 현재 Project_06의 legacy compatibility 경로이며 판매 분석 소유권을 뜻하지 않습니다. Project_07 handoff가 연결되면 이관 후보로 검토합니다. Kaggle 상품 분류를 요청 카테고리로 연결하는 map/version은 호출자가 명시해야 하며, 데이터에 없는 시즌이나 채널 의미를 자동 추정하지 않습니다.

### 콘셉트 초안에서 이미지 시안 생성

정규화 입력으로 만든 콘셉트 초안을 검토용 이미지 프롬프트로 연결하려면 `run_concept_to_image(context, ...)`를 사용합니다. 기본 실행은 프롬프트만 구성하고 외부 요청은 보내지 않습니다. 실제 OpenAI 이미지 생성을 사용하려면 로컬 `.env`에 `OPENAI_API_KEY`를 설정하고 `VOGUE_IMAGE_GENERATION_ENABLED=true`로 활성화한 뒤, 호출 시 `confirm_image_generation=True`를 명시해야 합니다. 생성 이미지는 `data/local/generated_images/`에 request ID·프롬프트 해시와 연결해 저장하며, 이 경로는 Git에서 제외됩니다.

```python
from vogue_npp import OpenAIImageProvider, load_settings, run_concept_to_image

settings = load_settings()
provider = (
    OpenAIImageProvider(api_key=settings.image_generation_api_key)
    if settings.image_generation_api_key else None
)
result = run_concept_to_image(
    context,
    provider=provider,
    image_generation_enabled=settings.image_generation_enabled,
    confirm_image_generation=True,  # 이 호출에서 실제 이미지 생성을 요청
)
print(result.image.status, result.image.image_path)
```

모델은 현재 `gpt-image-2.5-sunburst`이며 한 번에 이미지 1장을 생성합니다. 모델은 `OpenAIImageProvider(model=...)`로 지정할 수 있습니다. 공통 의류 디자이너 지침은 `IMAGE_DESIGNER_SYSTEM_PROMPT`에 보관하고, 각 `ImageGenerationRequest.system_prompt`에 포함합니다. Images API는 별도 system role 필드를 받지 않으므로 provider가 이 지침과 요청별 디자인 브리프를 구분 표기해 하나의 prompt로 전달합니다. 변경 시 `PROMPT_VERSION`도 갱신합니다. 생성 결과는 검토용 제안 시안이고 소재·핏·생산 가능성 또는 수요를 확인하지 않습니다. 트렌드 Evidence가 없으면 해당 트렌드명을 이미지 지시로 쓰지 않으며, 해소되지 않은 범주 충돌이 있으면 외부 호출을 막습니다. 상·하의 보완 관계가 역할 분류 규칙으로 확인되면 요청 상품과 재고 상품을 구분한 코디 제안으로 프롬프트에 전달합니다. Kaggle 원자료나 고객 단위 데이터는 이미지 API에 보내지 않고, 조립된 프롬프트에 들어가는 정규화된 속성도 Evidence·사용자 조건·가설로 구분해야 합니다.

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

결과 `hm_planning_analysis.json`은 UI의 **상품유형 전체 분석**에 제공됩니다. MD가 후보 선택 근거를 저장하거나 선택 후보의 결정적 브리프 초안을 생성하면 합성 데모 브리프와 분리된 `hm_planning_reviews`/`hm_planning_briefs` 테이블에 보존됩니다. 브리프는 Evidence 사실, MD 가설, unknown을 구분하고 이미지 생성 입력 JSON을 만듭니다. 해당 브라우저 흐름은 외부 이미지 API를 자동 호출하지 않습니다. 도메인 입력에서 프롬프트 구성과 선택적 OpenAI 이미지 생성을 실행하는 별도 workflow는 아래 설명을 참고하세요. 판매 월은 월요일 시작 주의 시작월이며, 실제 MD 시즌으로 추정하지 않습니다. 연도별 변화는 불완전한 연도와 상품 노출 기간을 보정하지 않은 서술 통계입니다. 상대 가격 구간은 원천 수치 분위 구간으로, 통화나 판매가 제안이 아닙니다. 기획 후보는 과거 판매 규모를 탐색하는 용도입니다.

결과는 Git에서 제외되는 `data/processed/hm-personalized-fashion-recommendations/` 아래 상품 카탈로그, 주간 거래 집계, Style·상품군·색상·채널·월별 분석 CSV, `hm_analysis.json`, `manifest.json`으로 생성됩니다. 완료된 실제 파일 점검과 제한은 [H&M Kaggle 처리 계획](docs/design/hm-kaggle-data-pipeline.md)에 기록했습니다. 분석 산출물은 아래 웹 앱의 **H&M 데이터** 섹션에 합성 데모와 분리해 표시합니다.

## MD용 로컬 프로토타입 실행

별도의 설치 없이 저장소 루트에서 실행하세요.

```bash
PYTHONPATH=src python3 -m vogue_npp.prototype.server
```

브라우저에서 [http://127.0.0.1:8765](http://127.0.0.1:8765)을 열면 카테고리·시즌 선택, 수치 기반 기회 탐색, 문서 검색과 근거 확인, 브리프 편집/버전 관리, 이미지 시안 비교, MD/디자이너 평가 이력을 한 흐름으로 시연할 수 있습니다. 06 이미지 시안에는 예시 입력을 수정해 실제 OpenAI 이미지 API를 요청하는 별도 폼이 있습니다. 이를 사용하려면 `.env`에 `OPENAI_API_KEY`를 설정하고 `VOGUE_IMAGE_GENERATION_ENABLED=true PYTHONPATH=src python3 -m vogue_npp.prototype.server`로 실행한 뒤, 화면에서 외부 전송 확인란을 체크합니다. 실제 생성 결과는 기존 시안 카드 목록의 첫 카드로 저장되며 평가와 Evidence 확인이 가능합니다. 다른 시안 비교는 API 키 없이 로컬 SVG 목업으로 생성됩니다. 서버는 이 컴퓨터 내부 주소에만 바인딩합니다. 중지하려면 실행 터미널에서 `Ctrl+C`를 누르세요.

브라우저 결과와 데이터 흐름·fixture 스키마·지표 산식·제한사항은 [프로토타입 실행·설계 안내](docs/design/prototype-runbook.md)에 문서화했습니다. 화면의 브리프·시안·평가는 로컬 Git 제외 SQLite 파일 `data/local/prototype.sqlite3`에 기록됩니다. 실제 Kaggle의 과거 상품·거래 분석은 별도 섹션에서 조회하며, 합성 재고/리뷰/트렌드 또는 기획 브리프와 자동 병합하지 않습니다. 기존 고정 ImageGen 사진과 UI 예시 폼에서 생성한 이미지는 구분해 시안 카드에 표시합니다. UI 브리프 편집 흐름은 도메인 입력 폼과 자동 병합되지 않습니다.

상품기획·운영 자료의 가용성 조사, 합성 fixture, 응답 계약과 로컬 조회 화면은 [상품기획·운영 데이터 계약](docs/design/planning-operations-data-contract.md)에 정리했습니다. `03 기획·운영 데이터` 메뉴에서는 합성 라인 플랜·마크다운 시나리오·KPI 정의·상품 상세·캠페인과 연결 상태를 볼 수 있습니다. 미연결 KPI/캠페인 결과는 null로 남기며, 실제 Kaggle 상품 카탈로그 조회는 관측 데이터로 별도 표시합니다.

주요 조회 API는 `/api/data-status`, `/api/planning/line-plans`, `/api/planning/markdown-reviews`, `/api/planning/kpi-definitions`, `/api/planning/campaigns`, `/api/products`, `/api/products/{id}`입니다. 현재는 로컬 읽기 전용이며 실제 PLM/PIM/ERP·분석 계정 연결은 포함하지 않습니다.

상품기획 데이터 후보와 생성 순서는 [합성 상품기획 데이터 맵](docs/design/synthetic-merch-data-map.md)을 따릅니다. 교차 도메인 목데이터는 `examples/fixtures/synthetic_merch_scenario.json`이며 Style–Article–SKU, 12주 판매·재고, markdown, KPI, 캠페인, 피드백을 별도 `SYN-*` 키로 연결합니다. seed와 생성 규칙을 고정해 다음 명령으로 재생성하고 통합 분석을 출력할 수 있습니다.

```bash
PYTHONPATH=src python3 -m vogue_npp.prototype.synthetic_scenario
```

`GET /api/synthetic-scenario`는 상품군·가격 tier·주간/채널별 집계, KPI, markdown 비교 및 캠페인/피드백 요약을 반환합니다. 모두 합성 결과이며 실제 H&M Kaggle 분석과는 독립입니다. `data/raw/fashion-cloud-api-v2.json`은 Fashion Cloud API 명세일 뿐 실제 상품 데이터나 인증이 아닙니다. 승인 및 호출 요청 전까지 외부 API는 호출하지 않습니다.

### Docker로 실행

Docker Compose를 설치한 뒤 저장소 루트에서 실행합니다.

```bash
docker compose up --build -d
```

브라우저에서 [http://127.0.0.1:8765](http://127.0.0.1:8765)을 엽니다. 중지하려면 `docker compose down`을 실행하세요. 브리프·시안·검토 기록은 Compose named volume에 보존되고, H&M 처리 결과는 호스트의 `data/processed/hm-personalized-fashion-recommendations/`에서 읽기 전용으로 마운트됩니다. Kaggle 원본·가공 파일과 `.env`는 이미지에 복사되지 않습니다. H&M 데이터가 아직 없더라도 앱은 실행되며 해당 화면에 분석 산출물 부재를 표시합니다.

## 설계 상태

### 실제 데이터 상품기획 흐름 상태

로컬 프로토타입은 H&M 과거 Article 거래 근거 조회, 후보 선택/반대근거 저장, Evidence와 가설을 구분하는 버전형 기획 브리프, 브리프별 사람 검토 기록까지 지원합니다. 신규 도메인 workflow는 정규화된 입력으로 프롬프트를 구성하고, 설정과 호출별 확인을 거쳐 OpenAI 이미지 API를 선택 호출할 수 있습니다. 웹 프로토타입의 H&M 브리프 편집 흐름과는 아직 자동 연결되지 않았습니다. 실제 H&M의 승인된 내부 RAG, 트렌드·재고·원가·고객 데이터, 사용자 인증, 운영 배포와 모니터링은 구현되지 않아 운영용 상품기획 시스템 완료 상태가 아닙니다. 외부 전송 전 데이터 권한, 보존·삭제, 모델 비용 및 이미지 권리를 검토해야 합니다.

에이전트 입력·출력 계약과 향후 통합 경계는 [Planning Agent 설계 제안](docs/design/new-product-planning-agent.md)에 정리했습니다. 도메인 코어는 기회 비교, 내부 콘셉트 초안, 출처 안전 검사를 수행합니다. 별도 로컬 웹 프로토타입의 합성/과거 판매 분석은 공통 API나 운영 데이터로 간주하지 않습니다.

Project_07과 협의할 결과는 현재 `SalesMarketDataResult (proposed)` 의미 초안입니다. 제안 결과는 상태, summary/findings, 판매 관측 및/또는 시장 결과, Evidence(출처·locator·기간/as-of·지역·채널·상품 매핑), 단위·통화·지표 정의·산식 참조, 제한·결측·오류·후속 질문을 담을 수 있습니다. 이름과 필드는 합의 전이며 운영 계약이 아닙니다. 판매량 0, 조건 자료 없음, 조회 실패/timeout, 권한 부족, ID 매핑 실패, 기간·채널·단위·통화 정의 불일치는 서로 다른 상태로 처리합니다.

현재 Project_07 판매·시장 데이터의 adapter, 사내 원장/API/DB 연결은 없습니다. 실제 연결 가능한 자료원도 확인되지 않았습니다. 자료원·기간·정의·단위가 없는 값은 추정하지 않으며, 판매 관측을 미래 수요·고객 선호·시장 성장으로 바꾸지 않습니다.

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

inputs = PlanningInputs(request=..., trend=..., inventory=...)  # three core normalized inputs
# Optional local extension: PlanningInputs(request=..., trend=..., inventory=..., sales=...)
context = build_planning_context(inputs)
draft, validation_issues = generate_concept_draft(context)
```

`draft`는 내부 검토 모델이며 입력별 상태, 충돌, Evidence ID와 제한사항을 보존합니다. 이를 공통 `ProductConcept` 응답으로 직렬화하는 코드는 아직 없습니다.

합성 입력으로 전체 흐름을 출력하는 예제는 다음과 같이 실행합니다. 예제 안의 상품·트렌드 ID와 재고 값은 모두 가상이며 실제 데이터로 사용하면 안 됩니다.

```bash
python3 -m pip install -r requirements.txt
PYTHONPATH=src python3 examples/synthetic_demo.py
```

이 예제는 콘셉트 초안과 이미지 프롬프트를 함께 출력합니다. 실제 이미지 생성은 `.env`에서 `OPENAI_API_KEY`와 `VOGUE_IMAGE_GENERATION_ENABLED=true`를 설정하고 아래처럼 명시 요청한 경우에만 수행되며, 비용이 발생할 수 있습니다.

```bash
PYTHONPATH=src python3 examples/synthetic_demo.py --generate-image
```

복수 엔진 비교 방식, 근거성·요청 준수·MD 유용성 지표와 아직 측정하지 않은 항목은 [근거 기반 생성 및 엔진 비교 평가 계획](docs/design/generator-evaluation-plan.md)에 적었습니다.

GraphRAG 트렌드 배치 입력(순위·유사도 없음)과 Trend × Category 평가, 기존/신규 후보, KG-RAG adapter, 점수화·포트폴리오 선정을 위한 **내부 계약과 use case 기준선**은 [GraphRAG TrendBatch 기반 상품기획 설계](docs/design/trend-batch-kg-rag-product-planning.md)를 참고하세요. 코드에는 의존성 없는 TrendBatch validator, 보수적 Trend Evaluator, 상품/판매/재고 및 KG/RAG repository ports, 후보 생성기, 설정형 scorer/selector와 use case가 있습니다. Pydantic/HTTP 운영 API, 원문 resolver, 운영 SQL/KG/vector 연결과 승인된 scoring 설정은 아직 연결되지 않았습니다. 기본 구성은 데이터를 조회하지 않았거나 점수 기준이 없음을 명시하며 TOP 5를 억지로 만들지 않습니다.
