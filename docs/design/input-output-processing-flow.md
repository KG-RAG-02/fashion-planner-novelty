# Project_06 input/output processing flow

P08 owns orchestration. It obtains Trend and Stock data before it calls P06, then sends the resulting three input objects in one request.

```text
사용자 요청 → P08 Trend 조회 → P08 Stock 조회
→ P08 POST /v1/agents/new-product-agent/runs
→ P06 입력 검증·Evidence/충돌 분석 → 상품 프로필과 초안 작성
→ 같은 상품 프로필로 product/outfit 이미지 생성(실제 provider가 설정된 경우)
→ P06 초안·시각자료 상태·원본 provenance 반환
→ P08이 P07 /reviews 호출
→ P08이 결과를 모아 통합 응답과 기획안 보드 구성
```

## Inputs

| Input | Owner | P06 handling |
|---|---|---|
| `planning_request` 1.0 | P08 request stage | Request text, season/category, constraints and missing fields are analyzed. Unknown values remain unknown. |
| `trend_result` 1.1 | Trend agent, called by P08 | Validated and normalized on an internal copy; original payload/schema/hash provenance stays in `input_evidence`. |
| `inventory_product_result` 1.0 | Stock agent, called by P08 | Product/stock facts, status, units, as-of and evidence are preserved and used as context. P06 does not query inventory itself. |

## Processing and output

1. Validate the `vogue-handoff/0.3` envelope, exact input keys, request IDs, supported schemas, producer identities and statuses.
2. Analyze the user request, eligible Trend evidence and Stock product/inventory context. Preserve input statuses, missing data, conflicts and evidence provenance.
3. Build one sourced `draft.product_profile` and use it for the narrative concept and visual prompts.
4. When a real image provider is explicitly configured, generate product and outfit images and store request-owned content-addressed artifacts. Otherwise return `skipped`; failures are visible and produce a partial result.
5. Return the P06 native result envelope. P08 projects the profile into its own P07 request, calls P07, then composes the integrated response and planning board.

P06 does not receive a P07 review result, call P07, or create a board. Sales/market results are not planning inputs. See [structured product profile](p06-structured-planning-draft.md) and [service runbook](prototype-runbook.md).
