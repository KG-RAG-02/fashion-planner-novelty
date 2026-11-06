from __future__ import annotations

import unittest

from vogue_npp import (
    AgentResult,
    AttributeSignal,
    InventoryProduct,
    PlanningInputs,
    PlanningRequest,
    TrendCandidate,
    build_planning_context,
    generate_concept_draft,
)
from vogue_npp.domain.context import InventoryProductResult, TrendResult


class TrendNameInputTests(unittest.TestCase):
    def _context(
        self, *, trend_status: str = "ok", with_pattern: bool = True,
    ):
        request_id = "trend-name-test"
        agent_id = "query-trend-agent"
        trend_evidence = "query-trend:E-001"
        pattern_evidence = "query-trend:E-002"
        attributes = (
            (
                AttributeSignal(
                    name="color",
                    value="deep burgundy",
                    origin="evidence_observation",
                    evidence_ids=(trend_evidence,),
                ),
                AttributeSignal(
                    name="pattern",
                    value="oversized floral",
                    origin="evidence_observation",
                    evidence_ids=(pattern_evidence,),
                ),
            )
            if with_pattern
            else ()
        )
        request = PlanningRequest(
            result=AgentResult(agent_id, request_id, "internal-prototype-0", "ok"),
            original_query="2027SS 여성 니트 콘셉트",
            season="2027SS",
            category="women_knit",
            field_origins={"season": "user", "category": "user"},
        )
        trend = TrendResult(
            result=AgentResult(
                agent_id,
                request_id,
                "internal-prototype-0",
                trend_status,
                evidence_ids=(trend_evidence, pattern_evidence),
            ),
            candidates=(
                TrendCandidate(
                    name="절제된 맥시멀리스트",
                    qualification="candidate",
                    season="2027SS",
                    category="women_knit",
                    attributes=attributes,
                    evidence_ids=(trend_evidence,),
                ),
            ),
        )
        inventory = InventoryProductResult(
            result=AgentResult(
                "own-product-inventory-agent",
                request_id,
                "internal-prototype-0",
                "no_results",
            ),
            products=(),
        )
        return build_planning_context(PlanningInputs(request, trend, inventory))

    def test_named_trend_and_supported_direction_are_in_review_draft(self) -> None:
        draft, issues = generate_concept_draft(self._context())
        self.assertFalse(issues)
        self.assertIn("절제된 맥시멀리스트", draft.opportunity.value)
        self.assertIn("절제된 맥시멀리스트", draft.product_definition.value)
        self.assertIn("oversized floral", draft.product_definition.value)
        self.assertIn("디자인 방향 가설", draft.product_definition.value)
        self.assertIn("절제된 베이스", draft.product_definition.value)
        self.assertEqual(draft.product_definition.kind, "proposal")
        self.assertIn("query-trend:E-001", draft.product_definition.evidence_ids)
        self.assertIn("query-trend:E-002", draft.product_definition.evidence_ids)
        attributes = {(item.name, item.value): item for item in draft.attributes}
        self.assertEqual(
            attributes[("color", "deep burgundy")].evidence_ids,
            ("query-trend:E-001",),
        )
        self.assertEqual(
            attributes[("pattern", "oversized floral")].evidence_ids,
            ("query-trend:E-002",),
        )
        self.assertNotIn(("material", "silk"), attributes)
        self.assertNotIn(("fit", "slim"), attributes)

    def test_missing_pattern_evidence_does_not_invent_design_element(self) -> None:
        draft, _ = generate_concept_draft(self._context(with_pattern=False))
        self.assertIn("절제된 맥시멀리스트", draft.product_definition.value)
        self.assertIn("구체적인 강조 요소는 입력 근거에 없어", draft.product_definition.value)
        self.assertNotIn("oversized floral", draft.product_definition.value)

    def test_unusable_trend_status_does_not_leak_candidate_name(self) -> None:
        draft, _ = generate_concept_draft(self._context(trend_status="error"))
        self.assertNotIn("절제된 맥시멀리스트", draft.opportunity.value)
        self.assertNotIn("절제된 맥시멀리스트", draft.product_definition.value)
        self.assertTrue(
            any("trend_result 상태가 'error'" in question for question in draft.questions_for_validation)
        )

    def test_sales_market_handoff_is_optional_and_not_fabricated(self) -> None:
        context = self._context()
        draft, issues = generate_concept_draft(context)
        self.assertEqual(context.input_statuses["sales_market_result"], "not_provided")
        self.assertIsNone(draft.sales_market_result)
        self.assertFalse(issues)
        self.assertTrue(any("Project_07 판매·시장 결과가 제공되지 않아" in question for question in draft.questions_for_validation))


if __name__ == "__main__":
    unittest.main()
