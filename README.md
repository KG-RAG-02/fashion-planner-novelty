# Project_06 · New Product Planning Agent

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

Project_06은 planning draft API를 제공합니다. UI는 Project_08 소유이며, 이 저장소에서는 브라우저 화면을 제공하지 않습니다. 로컬 실행은 명시적으로 `VOGUE_HTTP_MODE=local`을 지정하고 기본 주소 `http://127.0.0.1:8765`를 사용합니다. 공통 handoff 경로는 [`docs/design/http-handoff-v0.1.md`](docs/design/http-handoff-v0.1.md)에 설명되어 있습니다.

선택형 이미지 생성을 API 요청에 포함하려면 `.env` 또는 실행 환경에 `VOGUE_IMAGE_GENERATION_ENABLED=true`와 `OPENAI_API_KEY`를 설정합니다. 요청에 `generate_image: true`를 명시해야 외부 이미지 요청이 발생합니다. 비밀값이 들어 있는 `.env`는 커밋하지 마세요.

구조화 텍스트 기획 프롬프트는 `VOGUE_TEXT_GENERATION_ENABLED`로 요청할 수 있지만 현재 승인된 텍스트 모델 제공자가 연결되지 않았습니다. 이 설정만 켜면 외부 호출 없이 규칙 기반 초안과 `TEXT_GENERATION_UNAVAILABLE` 상태를 반환합니다.

## 테스트

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## 합성 상품기획 workbench

사내 카탈로그·기획 문서가 확보되기 전 개발·검증에 사용할 완전 합성 데이터와 로컬 탐색 CLI를 제공합니다. 이는 실제 회사 자료나 시장 사실이 아니며 기본 API/RAG에 자동 연결되지 않습니다.

```bash
python3 tools/generate_synthetic_planning_workbench.py --seed 20261110
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
- `sources/synthetic_corpus_retriever.py`, `sources/hybrid_retriever.py`: 명시 호출형 합성 corpus 검색 및 backend-neutral RRF 병합기. 실제 BM25/vector 인덱스 adapter는 미구성
- `workflows/image_generation.py`: opt-in 시안 생성
- `prototype/server.py`: Project_08 및 API 클라이언트용 HTTP adapter. `/api/planning-draft`는 내부 입력 모델에 맞춘 API이며 공용 wire contract가 아닙니다.

Trend/stock 호환 adapter는 원본 JSON 전체를 응답의 `input_evidence.*.payload`에 그대로 보존합니다. trend-analysis-agent 출력에 없는 producer ID/schema version은 adapter 추정·fallback으로 표시하고, 실제 입력에 있는 메타데이터와 혼동하지 않습니다. stock-agent의 `trend_results[].product_index`는 원래 `products[]` 인덱스 공간에서 해석하며 null 슬롯도 유지합니다. Per-trend Evidence, 제한사항, 오류, 누락 데이터와 매핑 상태를 응답에 표시합니다. 재현 가능한 다중 트렌드 합성 계약 fixture와 검증은 `tests/fixtures/upstream/stock-agent-multi-result.synthetic.json` 및 `tests/test_planning_draft_api.py`에 있습니다. 합성 데이터이며 운영 사실이 아닙니다.

Project_07 판매·시장 결과는 전체 payload를 불투명 handoff로 보존합니다. 판매·시장 지표를 재집계하거나 상세 schema를 임의로 확정하지 않습니다. 프로젝트 간 상세 계약, orchestrator 및 transport 연결은 별도 팀 합의가 필요합니다.

기획 RAG는 현재 허가된 내부 가이드·taxonomy·과거 기획 사례와 입력에 포함된 비판매 Evidence를 위한 검색 경계만 연결합니다. 기본 설정은 `not_configured`이며, 판매·시장 원천 검색과 분석은 Project_07 소유입니다. 상세 범위는 [기획 전용 KG/RAG 설계](docs/design/planning-rag-design.md)를 참고하세요.

다음 단계의 hybrid retrieval, 권한·인덱스 운영 및 평가 계획은 [RAG 고도화 설계안](docs/design/planning-rag-evolution-plan.md)에 정리했습니다. 이 문서는 제안이며 운영 인덱스 연결을 활성화하지 않습니다.

검색 흐름 검증용 합성 corpus는 `data/fixtures/planning_rag/synthetic_corpus.json`에 있습니다. `SyntheticCorpusRetriever`는 해당 합성 corpus를 대상으로만 명시적으로 생성해 쓰는 로컬 데모 adapter이며 기본 초안 경로에는 연결되지 않습니다. 실제 회사 문서나 승인된 정책·시장 사실이 아니며 운영 근거로 사용할 수 없습니다. 테스트 실행:

```bash
PYTHONPATH=src python3 -m unittest tests.test_planning_rag_synthetic_fixture -v
```

운영 자료 연결 전에는 자료 소유자 승인, 목적별 사용 권한, 보존·삭제 정책, 접근 감사, 인덱스 버전 및 정식 cross-project 계약을 합의해야 합니다.

## Project_07로 이동한 판매 기능

판매 도메인 모델, H&M 과거 거래 데이터 처리·품질·집계 adapter, 합성 판매·재고 분석과 관련 테스트는 Project_07 저장소가 소유합니다. 2026-11-09 이 작업공간의 H&M Kaggle 원본 ZIP과 처리 산출물 디렉터리도 Project_07의 `data/raw/` 및 `data/processed/`로 이동했습니다. 이 파일은 Git에 추적되지 않으며, 이동은 Kaggle 이용 권한을 확인하거나 승인하지 않습니다. 로컬 DB와 `.env`는 이동하지 않았습니다. 운영 판매 원장이나 시장자료 API는 아직 연결되지 않았습니다.
