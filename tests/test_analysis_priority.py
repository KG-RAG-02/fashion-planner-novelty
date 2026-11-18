from __future__ import annotations

import unittest

from fashion_planner_novelty import (
    AgentResult,
    InventoryProductResult,
    PlanningInputs,
    PlanningRequest,
    TrendResult,
    build_planning_context,
    generate_concept_draft,
)


class AnalysisPriorityTests(unittest.TestCase):
    def test_planning_context_uses_only_request_trend_and_inventory(self):
        request_id = "planning-inputs-only"
        context = build_planning_context(PlanningInputs(
            PlanningRequest(AgentResult("query-agent", request_id, "1.0", "ok")),
            TrendResult(AgentResult("trend-agent", request_id, "1.0", "partial")),
            InventoryProductResult(AgentResult("stock-agent", request_id, "1.0", "partial")),
        ))
        draft, issues = generate_concept_draft(context)
        self.assertEqual(set(context.input_statuses), {
            "planning_request", "trend_result", "inventory_product_result",
        })
        self.assertFalse(hasattr(draft, "sales_market_result"))
        self.assertFalse(issues)


if __name__ == "__main__":
    unittest.main()
