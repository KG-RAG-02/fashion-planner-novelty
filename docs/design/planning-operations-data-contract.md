# 상품기획·운영 데이터 계약

- 상태: 로컬 fixture API 및 화면 시연 구현 · 실제 운영 시스템 연결 전
- 기준 자료: H&M Kaggle historical catalog/sales + 별도 합성 planning/operations fixture
- 데이터 경계: 합성 운영 시나리오는 Kaggle 관측 파일이나 분석 보고서에 병합하지 않는다.

## 데이터 가용성

| 영역 | 현재 상태 | 현재 로컬 자료 | 실제 연결에 필요한 자료 |
|---|---|---|---|
| 시즌 라인 플랜·구성 원칙 | `synthetic` | 27SS 가상 style count, 카테고리 비중, 가격 tier 예시 | 승인된 시즌/시장별 line plan 문서 또는 PLM/merch planning export, 버전과 승인 상태 |
| 과거 판매·마크다운 리뷰 | 판매 `observed`, markdown `synthetic` | Kaggle 2018–2020 article·week·channel 거래 집계; 별도 가상 정가/마크다운 기간 | 실제 원가 제외 가격 이벤트·정가 기준, 적용 기간, 판매·재고·반품, markdown review 정의 |
| 가격 목표·KPI | 정의/목표 예시는 `synthetic`, 승인 측정값 `not_connected` | 산식·집계 단위·분모/분자·기간·가상 목표 | 승인된 KPI dictionary, 기준 시즌·시장·채널, 실제 측정 원천과 통화/단위 규칙 |
| 상품 설명·소재·관리·사이즈 | Kaggle 설명 `observed`, 상세 속성 `synthetic` | 실제 `prod_name`, taxonomy, 색상, `detail_desc`; UI 예시의 소재·관리·핏·사이즈 | 승인된 PIM/PLM product/article/SKU, 조성비, care label, size chart, fit note, 적용 시장/시즌 |
| 캠페인·프로모션 결과 | scenario `synthetic`, 실제 결과 `not_connected` | 가상 캠페인과 상품 매핑; 지표는 null | 승인된 analytics/ad 계정, promotion ID·item ID tagging, attribution window, spend 및 outcome |

`observed`, `user_input`, `synthetic`, `not_connected`, `unknown`은 서로 다른 상태다. 판매 구매 행은 주문·순매출·마크다운 효과를 자동으로 뜻하지 않는다. Kaggle price는 통화·정가가 확인되지 않아 가격 목표 계산에 사용하지 않는다.

## Fixture

별도 파일 `examples/fixtures/planning_operations_demo.json`은 다음 데이터 영역을 포함한다.

- `line_plans`: 가상의 27SS 상품군별 스타일 수, assortment share, 가격 tier와 원칙
- `markdown_reviews`: 기존 synthetic demo style과 연결한 정가/할인가/적용일 시나리오. outcome은 null
- `kpi_definitions`: 산식·분자·분모·단위·집계 단위·기간·반품 처리·가상 목표. 측정값은 미연결/null
- `product_details`: 합성 상세 상품의 소재/관리/핏/사이즈 예시. 실제 측정 치수는 null
- `campaigns`: 가상 일정·상품/promotion 연결. 비용·노출·클릭·구매·매출은 미연결/null
- `integrations`: H&M Partner Tech Hub, 내부 PLM/PIM/ERP, Google Analytics/Ads의 연결 상태. 자격 증명이나 endpoint는 설정하지 않음

각 주요 레코드는 `data_status`, `source_id`, `version`, `as_of`, scope 또는 적용 기간, 제한 사항을 가진다. API도 상태와 출처 메타데이터를 보존한다. fixture 검증기는 식별자 참조, 날짜, 가격 tier, 비중 합계 및 연결 전 KPI/캠페인 실측값이 null인지 확인한다.

목데이터는 UI/계약/검증용이다. 예시 가격·목표·캠페인은 H&M 실제 운영 사실이나 벤치마크, 실적, 마크다운 효과를 나타내지 않는다. 합성 필드는 판매 분석·추천 후보·Evidence에 자동 입력되지 않는다.

## 로컬 API

| Method / route | 응답 | 상태/범위 |
|---|---|---|
| `GET /api/data-status` | dataset 및 integration별 상태 목록 | Kaggle observed, fixture synthetic, 미연결 시스템을 나눠 반환 |
| `GET /api/planning/line-plans` | `records[]` | synthetic fixture 전용 |
| `GET /api/planning/markdown-reviews` | `records[]` | synthetic scenario 전용; 관측 결과 없음 |
| `GET /api/planning/kpi-definitions` | `records[]` | synthetic definition/target; actual 측정값 없음 |
| `GET /api/products` | `products[]` | synthetic 확장 상품 상세만 반환 |
| `GET /api/products/{style_id}` | `product` | `LW-*`는 synthetic 상세. Kaggle article ID/product_code는 원천 카탈로그 행만 반환 |
| `GET /api/planning/campaigns` | `records[]` | synthetic schedule; 측정 지표 null |

Dataset collection 응답은 `schema_version`, `data_status`, `source_id`, `version`, `as_of`, `scope`, `limitations`, `records`를 반환한다. 제품 상세 조회는 `observed`와 `synthetic` 결과를 한 상품 레코드에 합치지 않는다. product_code가 여러 article에 연결되면 API는 첫 article을 보여주고 `matched_article_count`를 함께 준다.

이 API들은 로컬 fixture/로컬 가공 CSV만 읽는다. 외부 수집·갱신·쓰기 endpoint는 없다. H&M Partner Tech Hub는 조직 초대를, 내부 상품/가격/재고 데이터는 데이터 소유자와 내부 계약을 필요로 한다. Analytics/Ads 데이터는 승인된 account/property 및 campaign-item tagging이 정해지기 전까지 연결되지 않는다.

## 연결 전에 확정할 최소 계약

- 공통 키: `season_id`, `product_group_id`, `style_id`, `article_id`, `sku_id`, `market`, `channel`, `campaign_id`, `promotion_id`
- 시간: 적용 `valid_from`/`valid_to`, 판매 관측 기간, `as_of`, 데이터 추출 시각
- 값 정의: price/list price/selling price와 markdown event, 통화, tax/return/cancel 처리, KPI의 단위·집계 grain·분모
- 제품 데이터: market/season별 상품 설명 버전, 소재 조성, 관리법, size system·실측표·핏 설명의 출처
- 운영: source owner, 접근 권한, 갱신 cadence, 보존/삭제, API version/quota, 감사 정책

필수 필드가 없거나 분모가 0이면 KPI는 숫자 0이 아니라 `not_calculable`과 누락 필드를 반환해야 한다. 현재 `/api/planning/kpi-definitions`에는 실측값이 없으며, ratio 계산 helper도 이 규칙을 따른다.
