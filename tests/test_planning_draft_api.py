import unittest

from vogue_npp.prototype.server import _build_planning_draft_response


class PlanningDraftApiTests(unittest.TestCase):
    def test_builds_draft_from_all_four_inputs_and_preserves_zero_and_evidence(self):
        payload = {
            "request_id": "draft-1",
            "planning_request": {
                "original_query": "27SS 아우터 제안",
                "season": "27SS",
                "category": "outerwear",
            },
            "trend_result": {
                "status": "ok",
                "candidates": [{
                    "name": "utility",
                    "qualification": "candidate",
                    "season": "27SS",
                    "category": "outerwear",
                    "evidence_ids": ["trend-1"],
                    "attributes": [{
                        "name": "color", "value": "olive",
                        "origin": "evidence_observation", "evidence_ids": ["trend-1"],
                    }],
                }],
            },
            "inventory_product_result": {
                "status": "partial",
                "limitations": ["snapshot partial"],
                "products": [{
                    "style_id": "style-1", "sku_ids": ["sku-1"],
                    "category": "outerwear", "quantity": 0, "unit": "pieces",
                    "inventory_definition": "available_to_sell", "as_of": "2026-11-06",
                    "evidence_ids": ["inventory-1"],
                }],
            },
            "sales_market_result": {
                "request_id": "draft-1", "agent_id": "market-research-agent",
                "status": "partial", "findings": [{"evidence_ids": ["market-1"]}],
                "limitations": ["limited coverage"],
            },
        }

        response = _build_planning_draft_response(payload)

        self.assertEqual(response["status"], "partial")
        self.assertEqual(response["input_statuses"]["inventory_product_result"], "partial")
        self.assertEqual(response["input_statuses"]["sales_market_result"], "partial")
        self.assertEqual(response["draft"]["sales_market_result"], payload["sales_market_result"])
        self.assertIn("trend-1", response["evidence_ids"])
        self.assertIn("market-1", response["evidence_ids"])
        self.assertIn("0 pieces", str(response["draft"]["relation_to_own_products"]))

    def test_missing_sales_result_is_not_provided_not_zero(self):
        response = _build_planning_draft_response({
            "request_id": "draft-2",
            "planning_request": {},
            "trend_result": {"status": "no_results"},
            "inventory_product_result": {"status": "error"},
        })

        self.assertEqual(response["input_statuses"]["sales_market_result"], "not_provided")
        self.assertIsNone(response["draft"]["sales_market_result"])


if __name__ == "__main__":
    unittest.main()
