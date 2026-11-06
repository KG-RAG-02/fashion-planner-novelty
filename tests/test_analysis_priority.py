from __future__ import annotations

import unittest

from vogue_npp import (
    AgentResult,
    AttributeSignal,
    InventoryProduct,
    PlanningInputs,
    PlanningRequest,
    SalesAnalysisResult,
    SalesObservation,
    TrendCandidate,
    analyze_opportunities,
    build_planning_context,
    generate_concept_draft,
)
from vogue_npp.domain.context import InventoryProductResult, TrendResult


class AnalysisPriorityTests(unittest.TestCase):
    def test_sales_missing_statuses_and_real_zero_remain_distinct(self):
        request_id = "sales-state-test"
        request = PlanningRequest(
            AgentResult("query-agent", request_id, "internal-v1", "ok"),
            category="tops",
        )
        trend = TrendResult(AgentResult("trend-agent", request_id, "internal-v1", "ok"))
        inventory = InventoryProductResult(
            AgentResult("inventory-agent", request_id, "internal-v1", "no_results")
        )

        absent = build_planning_context(PlanningInputs(request, trend, inventory=inventory))
        self.assertEqual(absent.input_statuses["sales_analysis_result"], "not_provided")
        self.assertFalse(absent.sales.observations)
        self.assertIsNone(absent.sales_market_result)
        absent_draft, absent_issues = generate_concept_draft(absent)
        self.assertFalse(any("구매 기록" in (item.statement.value or "") for item in absent_draft.opportunity_findings))
        self.assertFalse(absent_issues)

        for status in ("partial", "no_results", "error"):
            sales = SalesAnalysisResult(
                AgentResult("project-07-proposed", request_id, "internal-v1", status,
                            limitations=(f"{status} limitation",)),
                observations=(),
                source="unconnected-source",
                unit="units",
                metric_definitions=("observed sales units",),
            )
            context = build_planning_context(
                PlanningInputs(request, trend, inventory=inventory, sales=sales)
            )
            draft, issues = generate_concept_draft(context)
            self.assertEqual(context.input_statuses["sales_analysis_result"], status)
            self.assertIs(draft.sales_market_result, sales)
            self.assertIn(f"{status} limitation", draft.limitations)
            self.assertFalse(any("구매 기록" in (item.statement.value or "") for item in draft.opportunity_findings))
            self.assertFalse(issues)

        actual_zero = SalesAnalysisResult(
            AgentResult("project-07-proposed", request_id, "internal-v1", "ok"),
            observations=(SalesObservation(
                category="tops", purchase_rows=0, period_start="2026-01-01",
                period_end="2026-01-31", source_id="source-1", evidence_ids=("sales:zero",),
            ),),
        )
        zero_context = build_planning_context(
            PlanningInputs(request, trend, inventory=inventory, sales=actual_zero)
        )
        zero_draft, zero_issues = generate_concept_draft(zero_context)
        observation = next(item for item in zero_draft.opportunity_findings if "구매 기록" in (item.statement.value or ""))
        self.assertIn("0 purchase_rows", observation.statement.value)
        self.assertEqual(observation.statement.evidence_ids, ("sales:zero",))
        self.assertIs(zero_draft.sales_market_result, actual_zero)
        self.assertFalse(zero_issues)

    def test_findings_follow_trend_then_sales_then_inventory_with_query_as_scope(self):
        request_id = "priority-test"
        request = PlanningRequest(
            result=AgentResult("query-trend-agent", request_id, "internal-v1", "ok"),
            season="2027SS",
            category="women_knit",
            requested_attributes=(
                AttributeSignal("color", "pink", "user_requested"),
            ),
            field_origins={"season": "user", "category": "user"},
        )
        trend = TrendResult(
            result=AgentResult("query-trend-agent", request_id, "internal-v1", "ok"),
            candidates=(
                TrendCandidate(
                    name="절제된 맥시멀리스트",
                    qualification="candidate",
                    season="2027SS",
                    category="women_knit",
                    attributes=(
                        AttributeSignal(
                            "color", "deep burgundy", "evidence_observation", ("trend:E-1",)
                        ),
                    ),
                    evidence_ids=("trend:E-1",),
                ),
            ),
        )
        sales = SalesAnalysisResult(
            result=AgentResult("local-sales-analysis", request_id, "internal-v1", "ok"),
            observations=(
                SalesObservation(
                    category="women_knit",
                    purchase_rows=24,
                    period_start="2025-01-01",
                    period_end="2025-03-31",
                    source_id="hm-sales",
                    evidence_ids=("sales:E-1",),
                    product_code="ARTICLE-1",
                    season="2027SS",
                    attributes=(
                        AttributeSignal(
                            "color", "deep burgundy", "evidence_observation", ("sales:E-2",)
                        ),
                    ),
                ),
            ),
        )
        inventory = InventoryProductResult(
            result=AgentResult("own-product-inventory-agent", request_id, "internal-v1", "ok"),
            products=(
                InventoryProduct(
                    style_id="STYLE-1",
                    sku_ids=("SKU-1",),
                    season="2027SS",
                    category="women_knit",
                    attributes=(
                        AttributeSignal(
                            "color", "deep burgundy", "evidence_observation", ("inventory:E-1",)
                        ),
                    ),
                    quantity=4,
                    unit="pieces",
                    inventory_definition="available_to_sell",
                    as_of="2026-11-01",
                    evidence_ids=("inventory:E-1",),
                ),
            ),
        )
        context = build_planning_context(
            PlanningInputs(request=request, trend=trend, sales=sales, inventory=inventory)
        )

        analysis = analyze_opportunities(context)
        finding_text = [finding.statement.value or "" for finding in analysis.findings]
        trend_index = next(i for i, text in enumerate(finding_text) if "트렌드 후보" in text)
        sales_index = next(i for i, text in enumerate(finding_text) if "구매 기록" in text)
        inventory_index = next(i for i, text in enumerate(finding_text) if "자사 상품 STYLE-1" in text)

        self.assertLess(trend_index, sales_index)
        self.assertLess(sales_index, inventory_index)
        self.assertTrue(any("요청의 color 값과 트렌드 후보" in q for q in analysis.questions))
        self.assertIn("trend:E-1", analysis.findings[trend_index].statement.evidence_ids)


if __name__ == "__main__":
    unittest.main()
