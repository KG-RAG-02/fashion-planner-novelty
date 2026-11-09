from __future__ import annotations

import unittest

from vogue_npp import (
    AgentResult,
    AttributeSignal,
    InventoryProduct,
    PlanningInputs,
    PlanningRequest,
    TrendCandidate,
    analyze_opportunities,
    build_planning_context,
    generate_concept_draft,
)
from vogue_npp.domain.context import InventoryProductResult, TrendResult
from vogue_npp.domain.context import InputConsistencyError


class AnalysisPriorityTests(unittest.TestCase):
    def test_project07_sales_market_payload_is_consumed_as_opaque_handoff(self):
        request_id = "project-07-handoff"
        request = PlanningRequest(AgentResult("query-agent", request_id, "internal-v1", "ok"))
        trend = TrendResult(AgentResult("trend-agent", request_id, "internal-v1", "no_results"))
        inventory = InventoryProductResult(AgentResult("inventory-agent", request_id, "internal-v1", "partial"))
        payload = {
            "schema_version": "1.1-proposal",
            "request_id": request_id,
            "agent_id": "market-research-agent",
            "status": "partial",
            "summary": "Sales observations with explicit limits.",
            "findings": [],
            "evidence": [{"evidence_id": "p07:E-1"}],
            "limitations": ["Channel coverage is incomplete."],
            "errors": [],
            "sales_data": {
                "status": "partial",
                "observations": [{
                    "observation_id": "obs-1",
                    "metric_name": "units_sold",
                    "value": 0,
                    "unit": "units",
                    "evidence_ids": ["p07:E-1"],
                }],
                "limitations": ["One channel unavailable."],
                "errors": [],
                "follow_up_questions": [],
            },
            "market_data": {
                "status": "partial", "observations": [{"evidence_ids": ["market:E-1"]}],
                "limitations": ["Market data is incomplete."],
                "errors": ["One market endpoint failed."],
                "missing_data": [{"field": "market_size", "reason": "source_not_configured", "message": "No market-size source."}],
            },
            "unit_economics": {
                "status": "no_results", "calculations": [{"input_evidence_ids": ["cost:E-1"], "evidence_ids": ["calc:E-1"]}],
                "limitations": ["No approved formula."], "errors": [],
                "missing_data": [{"field": "unit_margin", "reason": "source_not_configured", "message": "Formula pending."}],
            },
        }
        context = build_planning_context(PlanningInputs(
            request, trend, inventory=inventory, sales_market_result=payload
        ))
        draft, issues = generate_concept_draft(context)
        self.assertEqual(context.input_statuses["sales_market_result"], "partial")
        self.assertIn("p07:E-1", context.evidence_ids)
        self.assertIn("market:E-1", context.evidence_ids)
        self.assertIn("cost:E-1", context.evidence_ids)
        self.assertIn("calc:E-1", context.evidence_ids)
        self.assertIn("Market data is incomplete.", draft.limitations)
        self.assertTrue(any("No market-size source." in item for item in draft.limitations))
        self.assertIn("No approved formula.", draft.limitations)
        self.assertIn("Channel coverage is incomplete.", draft.limitations)
        self.assertIs(draft.sales_market_result, payload)
        self.assertFalse(issues)

    def test_project07_payload_must_match_request_id(self):
        request_id = "expected-request"
        request = PlanningRequest(AgentResult("query-agent", request_id, "internal-v1", "ok"))
        trend = TrendResult(AgentResult("trend-agent", request_id, "internal-v1", "ok"))
        inventory = InventoryProductResult(AgentResult("inventory-agent", request_id, "internal-v1", "ok"))
        with self.assertRaises(InputConsistencyError):
            build_planning_context(PlanningInputs(
                request, trend, inventory=inventory,
                sales_market_result={"request_id": "other-request", "status": "ok"},
            ))



if __name__ == "__main__":
    unittest.main()
