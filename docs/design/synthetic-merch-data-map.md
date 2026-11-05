# 합성 상품기획·운영 데이터 맵

- 상태: 후보 재정리 완료 · 단계별 시나리오 확장 진행 중
- 원칙: `data/raw`는 외부 원본/명세 입력 위치, 합성 실험 fixture는 `examples/fixtures`에 둔다. H&M Kaggle 관측 원천은 별도 `data/raw/hm-personalized-fashion-recommendations/` 및 파생 경로에 유지한다.
- Fashion Cloud: `data/raw/fashion-cloud-api-v2.json`은 OpenAPI 2.0.0 명세 파일이다. 인증 토큰/응답 데이터가 아니며, 외부 호출은 승인과 명시적 요청 전까지 수행하지 않는다.

## 후보와 우선순위

| 우선 | 데이터 영역 | 의사결정 | 최소 키·필드 | 합성 분석 | 선행 조건 |
|---:|---|---|---|---|---|
| 1 | 시즌 라인 플랜·구색 | 시즌/상품군별 스타일 수와 가격대 배분 초안 검토 | season, market, product_group, style count, assortment share, price tier, version/status | 계획 비중 합계, 상품군·가격대 계획 구성 | 독립 시나리오 기준선 |
| 2 | 상품 마스터·옵션 | Style/색상 Article/사이즈 SKU 관계와 범위 점검 | style_id, article_id, sku_id, color, size, season, market | 계층 무결성, 변형 수, 속성 완성도 | 1 |
| 3 | 상품 상세 속성 | 소재·관리·핏·치수 정보의 준비도 확인 | article/style, composition, care, fit, size system/measurements, source/version | 소재 합계, 사이즈/속성 누락 | 2 |
| 4 | 판매·가격 이력 | 시즌 진행 중 구성 및 가격 구간 비교 | sku/article, week, channel, units, selling/list price, currency | 주간 추세, 평균 실현가, 가격대/채널별 구성 | 2 |
| 5 | 재고 흐름 | 품절과 판매 가능성 맥락 검토 | sku, as_of/week, opening, receipts, sales, adjustments, closing, status | 재고 항등식, 커버, 품절 구간 | 2, 4 |
| 6 | 마크다운 이벤트·리뷰 | 가격 변경 전후 결과를 기술적으로 검토 | event/style/article, valid period, list/selling price, comparison window | 가격차, 전후 판매/재고 변화; 인과효과 아님 | 4, 5 |
| 7 | KPI 사전·목표·측정 | 계획 대비 실적 검토 및 계산 가능성 판단 | definition/version, numerator/denominator, unit/grain, target, actual, scope | sell-through, markdown rate 등 | 1, 4, 5, 6 |
| 8 | 캠페인·프로모션 결과 | 채널/상품별 프로모션 반응 확인 | campaign/promotion, item, channel, views/clicks/purchase/revenue/spend, attribution | CTR, conversion, ROAS 시연 | 2, 4, KPI 정의 |
| 9 | 고객 조사/피드백 | 명시된 응답 주제의 표본 요약 | response_id, item, date, channel, theme, rating/text, sample scope | 표본·주제 빈도; 대표성/인과성 아님 | 별도 생성, 2 |
| 10 | 출처·버전·품질 | 모든 수치의 추적과 신뢰 경계 표시 | source_id/status/version/as_of/period/seed/rules/limitations | 검증 실패·결측·계산 불가 목록 | 모든 영역 |

## 생성 순서와 완료 기준

1. 이 후보 맵: 필요성·키·의존성·위험 확정.
2. 라인 플랜: 계획 레코드, 계획 구성 분석, 합계/가격 tier 검증.
3. 상품 옵션: Style–Article–SKU 계층 및 참조 무결성.
4. 판매·가격: 고정 seed 주간 자료와 시즌 집계.
5. 재고: 주간 재고 원장, 기초+입고-판매±조정=기말 검사.
6. 마크다운: 이벤트와 전후 비교; 단순 비교로 인과 해석 금지.
7. KPI: 사전과 생성 자료에서 재계산한 실제값을 별도 합성 상태로 기록.
8. 상품 속성: 조성·관리·치수와 completeness 검사.
9. 캠페인/피드백: 분모/귀속·표본 규칙을 명시한 가상 결과.
10. 통합 분석: 계획-판매-재고-가격/KPI를 synthetic scenario 안에서 연결하고 브리프 입력을 제시.

단계마다 fixture/schema, 검증, 해당 분석, API/UI, 테스트를 하나의 리뷰 가능한 단위로 남긴다. 모든 fixture와 결과는 `data_status: synthetic`, 별도 `SYN-*` 키, generator version/seed, 생성 규칙과 제한을 보존한다. 외부 API 호출 및 Kaggle 관측과의 합산은 금지한다.

## 설계 경계

- 현재 Kaggle H&M 데이터: 실제 관측 과거 판매/상품 분류. 시즌 계획, SKU 재고, 가격 이벤트, 반품, 캠페인, 고객 설문을 제공하지 않는다.
- 합성 시나리오: 구조·계산·화면 검증 전용. 판매 패턴은 생성 규칙의 결과이며 시장 사실이 아니다.
- Fashion Cloud 명세: 외부 API 계약 설명일 뿐 데이터 자체가 아니다. API 계정 권한 승인, 데이터 이용 조건, 토큰 관리가 확인되기 전에는 호출하지 않는다.
- 계획값, 목표, 실측값, 제안은 각각 분리한다. 합성 측정값도 실제 관측 성과로 표현하지 않는다.
