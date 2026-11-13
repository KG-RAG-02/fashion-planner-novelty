# Project_06 · New Product Planning Agent

공통 저장소 레이아웃과 HTTP 책임 경계는 [`docs/repository-boundaries.md`](docs/repository-boundaries.md)를 참고하세요.

이 저장소는 VOGUE의 **새상품 기획 에이전트**만 구현합니다. 기획 에이전트는 사용자 요청, 트렌드 결과와 근거, 상품·재고 입력으로 PlanningDraft와 신제품 이미지를 만듭니다. 판매·시장 결과 객체는 입력에서 제외합니다.

```text
사용자 요청 → 트렌드 에이전트 → 상품·재고 에이전트
→ Project_06 새상품 기획 에이전트 → Project_07 초안 사후 검증 → MD 최종 판단
```

## 책임 경계

- Project_06은 판매 원장 조회, 판매 집계, 시장 분석, 판매 기반 KPI·기회 계산을 하지 않습니다.
- canonical `/runs`와 `/api/planning-draft`는 `planning_request`, `trend_result`, `inventory_product_result`만 사용합니다. 판매·시장성은 초안/이미지 입력에 포함하지 않습니다.
- 상품·재고 정량값은 앞선 상품·재고 에이전트 입력입니다. 이 저장소의 기본 구현에는 운영 DB 연결이 없습니다.
- trend batch에 순위나 유사도는 요구하지 않습니다. 카테고리별 트렌드 적합성과 상품 콘셉트 검토는 상품기획 내부 작업입니다.
- 기획 후보 점수는 검토 기준이 설정된 경우에만 계산합니다. 미승인 기준으로 후보를 사실상 우선순위화하지 않습니다.
- API 통합 흐름은 신제품 이미지만 생성합니다. 실제 provider 호출은 서버 설정에 따릅니다.

실제 구현과 프로젝트 간 이관 범위는 [책임 경계·이관 기록](docs/design/agent-3-responsibility-map.md)에 정리했습니다. 상세 구현 제안은 [TrendBatch 기반 상품기획 설계](docs/design/trend-batch-kg-rag-product-planning.md)를, 모델 입력의 현재 프롬프트 인젝션 경계와 한계는 [프롬프트 인젝션 경계 문서](docs/design/prompt-injection-boundary.md)를 참고하세요.

P06 초안의 상품 필드를 출처와 함께 구조화하고 Project_07 review 입력으로 변환하는 구현과 검증 규칙은 [구조화 상품 초안 설계](docs/design/p06-structured-planning-draft.md)를 참고하세요. 이 내부 구현은 공통 wire contract 승인을 의미하지 않습니다.

## 실행

```bash
VOGUE_HTTP_MODE=local PYTHONPATH=src python3 -m vogue_npp.prototype.server
```

Project_06은 planning draft API를 제공합니다. UI는 Project_08 소유이며, 이 저장소에서는 브라우저 화면을 제공하지 않습니다. 로컬 실행은 명시적으로 `VOGUE_HTTP_MODE=local`을 지정하고 기본 주소 `http://127.0.0.1:8767`을 사용합니다. 기본 포트는 Project_08 UI(8765), Project_07 HTTP(8766)와 겹치지 않습니다. 현재 handoff 계약은 [`contracts/http-handoff-v0.3.md`](contracts/http-handoff-v0.3.md)입니다. 입력은 PlanningRequest, Trend, Stock 세 가지입니다. 별도 Sales Market review proxy endpoint는 선택적인 사후 검토 기능이며 신제품 이미지 생성 경로와 분리되어 있습니다.

P06은 planning 초안과 신제품 이미지를 생성하는 API(`/api/planning-draft`, `/v1/agents/new-product-agent/runs`) 및 별도 P07 review bridge(`/v1/agents/new-product-agent/sales-market-reviews`)만 제공합니다. 기존 자체 brief/variant/evaluation 작업대는 제거했습니다. P07 bridge는 전체 P06 응답에서 확인된 `category`, `product_type`, `gender`, `season`, `material`만 보내고 P07 응답 envelope를 보존합니다. `proposed_price`, `currency`, `costing`, 이미지 데이터와 Evidence 내부 메타데이터는 전달하지 않습니다. 기본 P07 URL은 `http://127.0.0.1:8766`이며 `VOGUE_SALES_MARKET_AGENT_URL`로 바꿀 수 있습니다. `VOGUE_SALES_MARKET_AGENT_BEARER_TOKEN`이 지정되면 P07 전달에 사용하고, 없으면 기존 공통 service token을 사용합니다.

Docker Compose는 `service` 모드로 TLS와 Bearer 인증을 사용합니다. 실행 전에 `VOGUE_TLS_CERT_HOST_PATH`, `VOGUE_TLS_KEY_HOST_PATH`, `VOGUE_TLS_CA_HOST_PATH`, `VOGUE_AGENT_SERVICE_BEARER_TOKEN`을 shell 환경에 설정한 뒤 `docker compose up --build`를 실행하세요. 인증서·키·token은 저장소에 넣지 않습니다. Compose 포트는 host loopback의 `127.0.0.1:8767`에만 공개됩니다.

이미지 생성 요청은 API가 항상 수행합니다. 실제 외부 이미지 생성을 사용하려면 `.env` 또는 실행 환경에 `VOGUE_IMAGE_GENERATION_ENABLED=true`와 `LLM_API_KEY`를 설정해야 합니다. 비밀값이 들어 있는 `.env`는 커밋하지 마세요. 서버 설정이 비활성화되어 있으면 이미지 요청 상태는 반환되지만 provider 호출은 진행하지 않습니다.

모든 기획 요청은 구조화 상품 프로필을 기준으로 신제품 시안 이미지를 생성합니다. 기획안 보드 이미지는 P08에서 생성하며 P06 응답에는 포함하지 않습니다.

P06 신제품 단독 이미지 생성에는 재고 이미지가 전달되지 않습니다. H&M 사진 시각 참고를 사용하도록 설정한 경우 해당 분석은 신제품 생성 프롬프트와 분리해 처리합니다. Handoff 입력 경계는 [`contracts/http-handoff-v0.3.md`](contracts/http-handoff-v0.3.md)에 기록되어 있습니다.

구조화 텍스트 기획은 버전 관리된 system prompt와 OpenAI Responses API의 strict JSON Schema 출력을 사용합니다. `.env`에 `LLM_API_KEY`(또는 `OPENAI_API_KEY`)를 설정하고 `VOGUE_TEXT_GENERATION_ENABLED=true`로 켜면 `VOGUE_TEXT_GENERATION_MODEL`(기본 `gpt-6-astra`)로 호출합니다. API 요청은 도구를 비활성화하고 응답 저장을 끄며, 반환 JSON은 로컬에서 요청 ID·Evidence ID·draft 규칙으로 다시 검증합니다. API 호출이나 검증이 실패하면 규칙 기반 초안으로 fallback합니다. 텍스트 생성은 `.env.example`에서 기본 비활성화되어 있습니다.

프롬프트 설계, 외부 API 데이터 경계, 실제 합성 입력 smoke 결과는 [텍스트 기획 Responses API 연결 설계](docs/design/text-planning-openai-integration.md)를 참고하세요.

## 테스트

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## 기획 입력과 참고 자료

서비스 기획 경로는 사용자 요청, 트렌드 결과, 재고 결과만 입력으로 받습니다. 판매·시장 결과와 합성 카탈로그·내부 규정은 초안 및 신제품 이미지 생성에 사용하지 않습니다. 재고 사실은 상품 분석에 필요한 범위에서만 반영하며, 재고 이미지를 신제품 이미지 생성에 전달하지 않습니다.

H&M 사진 참고 분석은 선택 기능이며 외부 시각 참고로 구분됩니다. 회사 규정이나 판매 사실의 근거로 쓰지 않습니다. 합성 workbench/RAG 개발 도구와 데이터는 제품 기획 runtime에서 검색하지 않습니다.

## 코드 구조

- `domain/context.py`, `domain/concept.py`, `domain/generator.py`: 입력 정합성, evidence 보존, 상품 콘셉트 초안
- `domain/trend_batch.py`, `domain/trend_evaluator.py`: 트렌드 배치 검증과 Trend × Category 평가
- `domain/candidates.py`, `workflows/trend_planning.py`: 상품기획 후보·기획 브리프·점수 설정·다양성 선택
- `sources/r2_hm_catalog.py`: H&M 상품 메타데이터의 R2 조회
- `sources/r2_product_images.py`, `sources/hm_visual_references.py`: 선택 H&M 사진의 R2 수신과 제한된 시각 분석
- `workflows/image_generation.py`: 신제품 콘셉트 이미지 생성
- `prototype/server.py`: Project_08 및 API 클라이언트용 HTTP adapter. `/api/planning-draft`는 내부 입력 모델에 맞춘 API이며 공용 wire contract가 아닙니다.

Trend/stock 호환 adapter는 원본 JSON 전체를 응답의 `input_evidence.*.payload`에 그대로 보존합니다. trend-analysis-agent 출력에 없는 producer ID/schema version은 adapter 추정/fallback으로 표시하고, 실제 입력에 있는 메타데이터와 혼동하지 않습니다. stock-agent의 `trend_results[].product_index`는 원래 `products[]` 인덱스 공간에서 해석하며 null 슬롯도 유지합니다. Per-trend Evidence, 제한사항, 오류, 누락 데이터와 매핑 상태를 응답에 표시합니다. 계약 테스트용 합성 upstream fixture는 `tests/fixtures/upstream/stock-agent-multi-result.synthetic.json`에 있습니다.

Project_07 판매·시장 결과 객체는 현재 PlanningDraft 입력 계약에 포함하지 않습니다. 별도의 review bridge는 초안 생성이 끝난 뒤 P07에 검토를 요청합니다.



합성 카탈로그·내부 규정 생성기, RAG retriever, R2 게시기와 평가 도구는 제거했습니다. H&M 사진 참고는 별도 선택 분석이며 [R2 H&M visual reference 안내](docs/design/r2-cloud-planning-rag.md)에 설명합니다.

## Project_07로 이동한 판매 기능

판매 도메인 모델, H&M 과거 거래 데이터 처리·품질·집계 adapter, 합성 판매·재고 분석과 관련 테스트는 Project_07 저장소가 소유합니다. 2026-11-09 이 작업공간의 H&M Kaggle 원본 ZIP과 처리 산출물 디렉터리도 Project_07의 `data/raw/` 및 `data/processed/`로 이동했습니다. 이 파일은 Git에 추적되지 않으며, 이동은 Kaggle 이용 권한을 확인하거나 승인하지 않습니다. 로컬 DB와 `.env`는 이동하지 않았습니다. 운영 판매 원장이나 시장자료 API는 아직 연결되지 않았습니다.
