# Project_06 새상품 기획 / Project_07 판매·시장 책임 경계

- 기준일: 2026-11-06
- 변경 상태: 코드 소유권을 Notion의 순차 workflow에 맞춤

## 확정된 workflow

```text
사용자 쿼리 → 트렌드 에이전트 → 상품·재고 에이전트
→ Project_07 판매·시장 에이전트 → Project_06 새상품 기획 에이전트 → MD 최종 판단
```

Project_06과 Project_07은 순차 handoff입니다. Project_07은 판매·시장 데이터를 수집·정규화·분석해 근거와 함께 반환합니다. Project_06은 전달 결과를 이용해 새상품 콘셉트와 기획안을 작성합니다. 상품 채택, 가격, 수량, 발주와 최종안은 MD 판단입니다.

## 저장소별 코드 책임

| 저장소 | 현재 소유 책임 | 구현 경계 |
|---|---|---|
| `project_06` | 새상품 기획 | `PlanningRequest`, `TrendResult`, 상품·재고 결과, Project_07 결과를 받아 근거·가설·미확정을 보존한 상품 콘셉트/기획 초안을 생성. 판매 원장 연결·집계·시장 분석 없음 |
| `project_07` | 판매·시장 분석 | sales domain result, H&M 과거자료 처리·품질·집계 adapter, 판매/시장 finding, 합성 판매 분석 fixture와 테스트. 운영 원장·외부 시장 API 연결은 아직 없음 |

Project_06의 `sales_market_result`는 판매 분석 기능이 아니라 Project_07 결과를 보존하는 handoff 경계입니다. 판매 점수, 매출, 판매 추세 및 KPI를 재계산하지 않습니다. 재고 값 역시 판매량으로 해석하지 않습니다.

## 코드 이동 내역

Project_07로 이동한 코드(프로젝트 경로 기준):

- `domain/sales.py`: `SalesObservation`, `SalesDataResult`, comparable peer percentile helper
- `sources/hm_historical/`: H&M 처리·품질·분석·sales adapter, 기존 운영·합성 시나리오 demo, evidence retrieval helper
- `examples/fixtures/`: 이전 합성 prototype, planning operations, cross-domain scenario fixture
- `tests/hm_historical/`: sales adapter/domain, 합성 시나리오와 operations fixture 테스트
- 관련 H&M 데이터 pipeline 및 planning/operations 설계 문서

Project_06에서는 판매 관련 source, 분석, sales query/repository port, 판매 중심 review workflow/API/UI와 테스트를 제거했습니다. Project_08이 로컬 UI를 소유합니다. Project_06은 planning draft API와 선택형 이미지 생성 기능을 제공하며, 브라우저 화면과 정적 리소스는 제공하지 않습니다. 예전 demo fixture는 판매/재고 점수를 제거하고 점수 없는 기획 검토 예시로 바꿨습니다.

## 데이터·운영 연결 제한

- 2026-11-09 이 작업공간의 H&M Kaggle 원본 ZIP과 처리 데이터 디렉터리를 Project_07의 `data/raw/` 및 `data/processed/`로 이동했습니다. 파일은 Git 비추적 상태이며 이동 자체는 이용 권한을 승인하지 않습니다.
- Project_07의 H&M adapter는 historical public data용 실험 adapter입니다. 사내 판매 원장이나 시장 사실의 대체물이 아닙니다.
- synthetic records는 Project_07의 테스트·설명용이며 운영 결과에 섞지 않습니다.
- 사내 PostgreSQL, KG/vector DB, 외부 시장자료, 인증 API 및 Project_06/07 간 운영 API는 연결되지 않았습니다.
- 공용 handoff의 세부 wire schema와 버전은 팀 합의 전입니다. Project_06은 내부 결과 모델/매핑 범위에 한정합니다.

## 검증 방법

각 저장소에서 독립적으로 실행합니다.

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Project_07의 adapter 테스트는 임시 디렉터리에 fixture CSV/manifest를 생성해 원본 Kaggle 파일 없이 실행합니다. 원본 `data/`는 검증 의존성으로 사용하지 않습니다.
