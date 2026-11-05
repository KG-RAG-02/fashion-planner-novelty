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

언어, 프레임워크, API 프로토콜, 모델, 데이터 소스 등은 아직 확정하지 않았습니다. 저장소의 후속 설계에서 대안과 근거를 기록한 뒤 결정합니다.

## 프로젝트 문서

- [Project Overview](https://app.notion.com/p/40d3269b1acd809c98c5dc5de4f61d24)
- [Project Workflow](https://app.notion.com/p/40f3269b1acd81378143f35b599ef9a0)
- [저장소 분리 협업 가이드](https://app.notion.com/p/40e3269b1acd81489fecc1052e033b54)
