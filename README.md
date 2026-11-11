# Project_06 · New Product Planning Agent

공통 저장소 레이아웃과 HTTP 책임 경계는 [`docs/repository-boundaries.md`](docs/repository-boundaries.md)를 참고하세요.

이 저장소는 VOGUE의 **새상품 기획 에이전트**만 구현합니다. 기획안 에이전트는 사용자 요청, 트렌드 결과와 근거, 상품·재고 입력, Project_07의 판매·시장 결과를 받아 검토 가능한 상품 콘셉트와 기획 초안을 만듭니다.

```text
사용자 요청 → 트렌드 에이전트 → 상품·재고 에이전트
→ Project_07 판매·시장 에이전트 → Project_06 새상품 기획 에이전트 → MD 최종 판단
```

## 책임 경계

- Project_06은 판매 원장 조회, 판매 집계, 시장 분석, 판매 기반 KPI·기회 계산을 하지 않습니다.
- Project_06은 Project_07 결과를 request ID, status, 근거, 제한사항과 함께 입력으로 받아 기획 맥락에 반영합니다. 결과가 없거나 불완전하면 이를 표시하고 판매 사실을 만들지 않습니다.
- 상품·재고 정량값은 앞선 상품·재고 에이전트 입력입니다. 이 저장소의 기본 구현에는 운영 DB 연결이 없습니다.
- trend batch에 순위나 유사도는 요구하지 않습니다. 카테고리별 트렌드 적합성과 상품 콘셉트 검토는 상품기획 내부 작업입니다.
- 기획 후보 점수는 검토 기준이 설정된 경우에만 계산합니다. 미승인 기준으로 후보를 사실상 우선순위화하지 않습니다.
- 이미지는 명시적으로 요청하고 서버 설정이 활성화된 경우에만 생성합니다.

실제 구현과 프로젝트 간 이관 범위는 [책임 경계·이관 기록](docs/design/agent-3-responsibility-map.md)에 정리했습니다. 상세 구현 제안은 [TrendBatch 기반 상품기획 설계](docs/design/trend-batch-kg-rag-product-planning.md)를, 모델 입력의 현재 프롬프트 인젝션 경계와 한계는 [프롬프트 인젝션 경계 문서](docs/design/prompt-injection-boundary.md)를 참고하세요.

## 실행

```bash
VOGUE_HTTP_MODE=local PYTHONPATH=src python3 -m vogue_npp.prototype.server
```

Project_06은 planning draft API를 제공합니다. UI는 Project_08 소유이며, 이 저장소에서는 브라우저 화면을 제공하지 않습니다. 로컬 실행은 명시적으로 `VOGUE_HTTP_MODE=local`을 지정하고 기본 주소 `http://127.0.0.1:8767`을 사용합니다. 기본 포트는 Project_08 UI(8765), Project_07 HTTP(8766)와 겹치지 않습니다. 공통 handoff 경로는 [`contracts/http-handoff-v0.2.md`](contracts/http-handoff-v0.2.md)에 설명되어 있습니다. 초안 생성 요청에는 판매·시장 에이전트 결과 객체가 필수이며, 분석 결과가 없으면 `status: "no_results"`로 전달해야 합니다.

Docker Compose는 `service` 모드로 TLS와 Bearer 인증을 사용합니다. 실행 전에 `VOGUE_TLS_CERT_HOST_PATH`, `VOGUE_TLS_KEY_HOST_PATH`, `VOGUE_TLS_CA_HOST_PATH`, `VOGUE_AGENT_SERVICE_BEARER_TOKEN`을 shell 환경에 설정한 뒤 `docker compose up --build`를 실행하세요. 인증서·키·token은 저장소에 넣지 않습니다. Compose 포트는 host loopback의 `127.0.0.1:8767`에만 공개됩니다.

이미지 생성 요청은 API가 항상 수행합니다. 실제 외부 이미지 생성을 사용하려면 `.env` 또는 실행 환경에 `VOGUE_IMAGE_GENERATION_ENABLED=true`와 `LLM_API_KEY`를 설정해야 합니다. 비밀값이 들어 있는 `.env`는 커밋하지 마세요. 서버 설정이 비활성화되어 있으면 이미지 요청 상태는 반환되지만 provider 호출은 진행하지 않습니다.

모든 기획 요청에서 신제품 시안 이미지와 근거 연결 기획 보드를 요청합니다. 별도 이미지 생성 플래그는 필요하지 않습니다. 신제품 시안이 생성되면 보드는 SVG 결정적 렌더러가 텍스트와 Evidence ID를 배치해 만듭니다.

착장 생성은 선택된 재고 상품의 `article_id` 또는 숫자형 `sku_ids[]`에서 ID를 확인하고, Project_06의 읽기 전용 R2 adapter가 `R2_IMAGE_PREFIX/<앞 3자리>/<article_id>.jpg` 한 장씩 가져올 수 있습니다. stock-agent와 같은 bucket/read-only credential을 `R2_ACCOUNT_ID`, `R2_ENDPOINT`, `R2_BUCKET`, `R2_IMAGE_PREFIX`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` 환경변수로 설정합니다. 로컬 파일 캐시는 `VOGUE_R2_IMAGE_CACHE_DIR`(기본 `data/local/r2_product_images`)에 선택한 이미지만 둡니다. 신제품 단독 이미지 생성에는 재고 이미지가 전달되지 않고 착장 합성 단계에서만 참조됩니다. `VOGUE_R2_IMAGE_ALLOW_PROVIDER_UPLOAD`는 기본 `true`이며 `false`로 설정하면 R2 이미지를 외부 이미지 provider에 전송하지 않습니다. Kaggle 데이터 이용 조건상 허용된 환경에서만 켜세요. 기존 허용 host를 통한 `products[].image.url` 입력도 지원합니다. handoff field와 사용 경계는 [`contracts/http-handoff-v0.2.md`](contracts/http-handoff-v0.2.md)에 기록되어 있습니다.

구조화 텍스트 기획은 버전 관리된 system prompt와 OpenAI Responses API의 strict JSON Schema 출력을 사용합니다. `.env`에 `LLM_API_KEY`(또는 `OPENAI_API_KEY`)를 설정하고 `VOGUE_TEXT_GENERATION_ENABLED=true`로 켜면 `VOGUE_TEXT_GENERATION_MODEL`(기본 `gpt-6-astra`)로 호출합니다. API 요청은 도구를 비활성화하고 응답 저장을 끄며, 반환 JSON은 로컬에서 요청 ID·Evidence ID·draft 규칙으로 다시 검증합니다. API 호출이나 검증이 실패하면 규칙 기반 초안으로 fallback합니다. 텍스트 생성은 `.env.example`에서 기본 비활성화되어 있습니다.

프롬프트 설계, 외부 API 데이터 경계, 실제 합성 입력 smoke 결과는 [텍스트 기획 Responses API 연결 설계](docs/design/text-planning-openai-integration.md)를 참고하세요.

## 테스트

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## 합성 상품기획 workbench

사내 카탈로그·기획 문서가 확보되기 전 개발·검증에 사용할 완전 합성 데이터와 로컬 탐색 CLI를 제공합니다. 이는 실제 회사 자료나 시장 사실이 아닙니다. `VOGUE_SYNTHETIC_PLANNING_RAG_ENABLED=true`이면 `/api/planning-draft`는 기본적으로 versioned R2 DuckDB의 `synthetic_*` 테이블을 읽기 전용으로 검색합니다. R2 DB 캐시는 ETag별 `data/local/r2_planning_db`에 둡니다. `VOGUE_SYNTHETIC_PLANNING_RAG_SOURCE=local`을 지정하면 JSON fixture를 사용할 수 있습니다.

활성 R2 source에서는 요청 카테고리와 맞는 H&M Kaggle 상품 사진을 최대 3장 가져와, 허용 설정이 켜진 경우 시각 분석을 수행합니다. 관찰은 합성 내부 근거와 분리된 `hm_visual_references` 응답으로 반환되며 제품 소재·가격·수요를 추정하지 않습니다. 상세 설정과 검증 상태는 [R2 cloud planning RAG 설계](docs/design/r2-cloud-planning-rag.md)를 참고하세요.

```bash
python3 scripts/generate_synthetic_planning_workbench.py --seed 20261110
PYTHONPATH=src python3 -m vogue_npp.synthetic_planning_workbench list
PYTHONPATH=src python3 -m vogue_npp.synthetic_planning_workbench quality
PYTHONPATH=src python3 -m vogue_npp.synthetic_planning_workbench draft SYN-REQ-PLANNING-001
```

검색·비교·Evidence 추적·기획 초안 생성·데이터 품질 진단 명령과 실제 자료 전환 제한은 [합성 상품기획 workbench 안내](docs/design/synthetic-planning-workbench.md)를 참고하세요.

## 코드 구조

- `domain/context.py`, `domain/concept.py`, `domain/generator.py`: 입력 정합성, evidence 보존, 상품 콘셉트 초안
- `domain/trend_batch.py`, `domain/trend_evaluator.py`: 트렌드 배치 검증과 Trend × Category 평가
- `domain/candidates.py`, `workflows/trend_planning.py`: 상품기획 후보·기획 브리프·점수 설정·다양성 선택
- `domain/retrieval.py`, `workflows/planning_retrieval.py`: 목적·source allowlist 기반 기획 검색, Query Plan 추적, Evidence 권한 필터
- `sources/r2_synthetic_workbench.py`, `sources/synthetic_workbench_retriever.py`: R2 DuckDB 버전 캐시와 synthetic Evidence 검색
- `sources/r2_product_images.py`, `sources/hm_visual_references.py`: 선택 H&M 사진의 R2 수신과 제한된 시각 분석
- `sources/synthetic_corpus_retriever.py`, `sources/hybrid_retriever.py`: fixture corpus 검색 및 backend-neutral RRF 병합기. 실제 BM25/vector 인덱스 adapter는 미구성
- `workflows/image_generation.py`: opt-in 시안 생성
- `prototype/server.py`: Project_08 및 API 클라이언트용 HTTP adapter. `/api/planning-draft`는 내부 입력 모델에 맞춘 API이며 공용 wire contract가 아닙니다.

Trend/stock 호환 adapter는 원본 JSON 전체를 응답의 `input_evidence.*.payload`에 그대로 보존합니다. trend-analysis-agent 출력에 없는 producer ID/schema version은 adapter 추정·fallback으로 표시하고, 실제 입력에 있는 메타데이터와 혼동하지 않습니다. stock-agent의 `trend_results[].product_index`는 원래 `products[]` 인덱스 공간에서 해석하며 null 슬롯도 유지합니다. Per-trend Evidence, 제한사항, 오류, 누락 데이터와 매핑 상태를 응답에 표시합니다. 재현 가능한 다중 트렌드 합성 계약 fixture와 검증은 `tests/fixtures/upstream/stock-agent-multi-result.synthetic.json` 및 `tests/test_planning_draft_api.py`에 있습니다. 합성 데이터이며 운영 사실이 아닙니다.

Project_07 판매·시장 결과는 전체 payload를 불투명 handoff로 보존합니다. 판매·시장 지표를 재집계하거나 상세 schema를 임의로 확정하지 않습니다. 프로젝트 간 상세 계약, orchestrator 및 transport 연결은 별도 팀 합의가 필요합니다.

기획 RAG는 현재 허가된 내부 가이드·taxonomy·과거 기획 사례와 입력에 포함된 비판매 Evidence를 위한 검색 경계만 연결합니다. 기본 설정은 `not_configured`이며, 판매·시장 원천 검색과 분석은 Project_07 소유입니다. 상세 범위는 [기획 전용 KG/RAG 설계](docs/design/planning-rag-design.md)를 참고하세요.

다음 단계의 hybrid retrieval, 권한·인덱스 운영 및 평가 계획은 [RAG 고도화 설계안](docs/design/planning-rag-evolution-plan.md)에 정리했습니다. 이 문서는 제안이며 운영 인덱스 연결을 활성화하지 않습니다.

합성 사내 카탈로그·가이드 RAG를 실제 신상품 초안 흐름에 연결하기 위한 데이터 생성, 검색, 근거 추적, 이미지 경계, 평가 작업 순서는 [합성 카탈로그 RAG 기반 기획 계획](docs/design/synthetic-catalog-rag-planning-roadmap.md)에 정리했습니다. 사용할 수 있는 실물 자료는 H&M Kaggle 상품 사진뿐이지만, competition rules의 비상업적·학술 연구 범위와 데이터 접근 제한 때문에 본 계획의 기본 합성/RAG 경로에는 포함하지 않습니다.

검색 흐름 검증용 합성 corpus는 `data/fixtures/planning_rag/synthetic_corpus.json`에 있습니다. `SyntheticCorpusRetriever`는 해당 합성 corpus를 대상으로만 명시적으로 생성해 쓰는 로컬 데모 adapter이며 기본 초안 경로에는 연결되지 않습니다. 실제 회사 문서나 승인된 정책·시장 사실이 아니며 운영 근거로 사용할 수 없습니다. 테스트 실행:

```bash
PYTHONPATH=src python3 -m unittest tests.test_planning_rag_synthetic_fixture -v
```

운영 자료 연결 전에는 자료 소유자 승인, 목적별 사용 권한, 보존·삭제 정책, 접근 감사, 인덱스 버전 및 정식 cross-project 계약을 합의해야 합니다.

## Project_07로 이동한 판매 기능

판매 도메인 모델, H&M 과거 거래 데이터 처리·품질·집계 adapter, 합성 판매·재고 분석과 관련 테스트는 Project_07 저장소가 소유합니다. 2026-11-09 이 작업공간의 H&M Kaggle 원본 ZIP과 처리 산출물 디렉터리도 Project_07의 `data/raw/` 및 `data/processed/`로 이동했습니다. 이 파일은 Git에 추적되지 않으며, 이동은 Kaggle 이용 권한을 확인하거나 승인하지 않습니다. 로컬 DB와 `.env`는 이동하지 않았습니다. 운영 판매 원장이나 시장자료 API는 아직 연결되지 않았습니다.
