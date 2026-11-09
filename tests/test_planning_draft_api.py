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
                "request_id": "draft-1",
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
                "request_id": "draft-1",
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
            "trend_result": {"request_id": "draft-2", "status": "no_results"},
            "inventory_product_result": {"request_id": "draft-2", "status": "error"},
        })

        self.assertEqual(response["input_statuses"]["sales_market_result"], "not_provided")
        self.assertIsNone(response["draft"]["sales_market_result"])

    def test_accepts_notions_v1_nested_inputs_and_preserves_market_handoff(self):
        payload = {
            "planning_request": {
                "schema_version": "1.0", "request_id": "notion-1", "query": "27SS 아우터",
                "context": {
                    "season": {"value": "27SS", "source": "user", "raw": "27SS"},
                    "category": {"value": "outerwear", "source": "user", "raw": "아우터"},
                    "market": [{"value": "KR", "source": "user"}],
                    "channel": [{"value": "online", "source": "user"}],
                },
                "requested_attributes": [{"name": "color", "value": "olive", "source": "user"}],
                "constraints": [], "missing_fields": [],
            },
            "trend_result": {
                "schema_version": "1.0", "request_id": "notion-1", "agent_id": "query-trend-agent",
                "status": "partial", "trend_candidates": [{
                    "name": "utility", "qualification": "candidate", "evidence_ids": ["trend-E1"],
                    "attributes": [{"name": "fabric", "value": "cotton", "evidence_ids": ["trend-E1"]}],
                }], "evidence": [{"evidence_id": "trend-E1"}], "limitations": ["coverage limited"],
            },
            "inventory_product_result": {
                "schema_version": "1.0", "request_id": "notion-1", "agent_id": "own-product-inventory-agent",
                "status": "ok", "products": [{"style_id": "s1", "sku_ids": ["sku1"],
                    "inventory": {"quantity": 0, "unit": "pieces", "as_of": "2026-11-01", "definition": "on_hand"},
                    "evidence_ids": ["stock-E1"]}],
            },
            "sales_market_result": {"schema_version": "1.1-proposal", "request_id": "notion-1",
                "agent_id": "market-research-agent", "status": "no_results", "summary": "none",
                "findings": [], "evidence": [], "limitations": ["no approved source"], "errors": [],
                "sales_data": {"status": "no_results", "observations": [], "limitations": [], "errors": []}},
        }
        response = _build_planning_draft_response(payload)
        self.assertEqual(response["input_statuses"]["trend_result"], "partial")
        self.assertEqual(response["draft"]["sales_market_result"], payload["sales_market_result"])
        self.assertIn("trend-E1", response["evidence_ids"])
        self.assertIn("stock-E1", response["evidence_ids"])
        self.assertIn("0 pieces", str(response["draft"]["relation_to_own_products"]))

    def test_rejects_mismatched_upstream_request_id(self):
        payload = {"request_id": "r1", "planning_request": {"request_id": "r1"},
                   "trend_result": {"request_id": "r2"}, "inventory_product_result": {"request_id": "r1"}}
        with self.assertRaisesRegex(ValueError, "request_id"):
            _build_planning_draft_response(payload)


if __name__ == "__main__":
    unittest.main()
