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

실제 구현과 프로젝트 간 이관 범위는 [책임 경계·이관 기록](docs/design/agent-3-responsibility-map.md)에 정리했습니다. 상세 구현 제안은 [TrendBatch 기반 상품기획 설계](docs/design/trend-batch-kg-rag-product-planning.md)를 참고하세요.

## 실행

```bash
PYTHONPATH=src python3 -m vogue_npp.prototype.server
```

로컬 UI: `http://127.0.0.1:8765`

선택형 이미지 생성을 켜려면 `.env` 또는 실행 환경에 `VOGUE_IMAGE_GENERATION_ENABLED=true`와 `OPENAI_API_KEY`를 설정합니다. UI에서 생성 확인을 체크해야 외부 이미지 요청이 발생합니다. 비밀값이 들어 있는 `.env`는 커밋하지 마세요.

## 테스트

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## 코드 구조

- `domain/context.py`, `domain/concept.py`, `domain/generator.py`: 입력 정합성, evidence 보존, 상품 콘셉트 초안
- `domain/trend_batch.py`, `domain/trend_evaluator.py`: 트렌드 배치 검증과 Trend × Category 평가
- `domain/candidates.py`, `workflows/trend_planning.py`: 상품기획 후보·기획 브리프·점수 설정·다양성 선택
- `domain/retrieval.py`, `workflows/planning_retrieval.py`: 목적·source allowlist 기반 기획 자료 검색 흐름과 Evidence 권한 필터. 실제 인덱스 연결은 미구성
- `workflows/image_generation.py`: opt-in 시안 생성
- `prototype/`: 네 upstream 입력을 받아 기획서 초안을 표시하고 Markdown으로 내려받는 로컬 UI. `/api/planning-draft`는 내부 입력 모델에 맞춘 로컬 adapter이며 공용 wire contract가 아닙니다.

기획 RAG는 현재 허가된 내부 가이드·taxonomy·과거 기획 사례와 입력에 포함된 비판매 Evidence를 위한 검색 경계만 연결합니다. 기본 설정은 `not_configured`이며, 판매·시장 원천 검색과 분석은 Project_07 소유입니다. 상세 범위는 [기획 전용 KG/RAG 설계](docs/design/planning-rag-design.md)를 참고하세요.

## Project_07로 이동한 판매 기능

판매 도메인 모델, H&M 과거 거래 데이터 처리·품질·집계 adapter, 합성 판매·재고 분석과 관련 테스트는 Project_07 저장소가 소유합니다. 2026-11-09 이 작업공간의 H&M Kaggle 원본 ZIP과 처리 산출물 디렉터리도 Project_07의 `data/raw/` 및 `data/processed/`로 이동했습니다. 이 파일은 Git에 추적되지 않으며, 이동은 Kaggle 이용 권한을 확인하거나 승인하지 않습니다. 로컬 DB와 `.env`는 이동하지 않았습니다. 운영 판매 원장이나 시장자료 API는 아직 연결되지 않았습니다.
