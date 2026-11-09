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
        self.assertEqual(response["input_evidence"]["planning_request"]["payload"], payload["planning_request"])
        self.assertEqual(response["input_evidence"]["trend_result"]["evidence_ids"], ["trend-1"])
        self.assertEqual(response["input_evidence"]["inventory_product_result"]["evidence_ids"], ["inventory-1"])
        self.assertEqual(response["input_evidence"]["sales_market_result"]["evidence_ids"], ["market-1"])

    def test_missing_sales_result_is_not_provided_not_zero(self):
        response = _build_planning_draft_response({
            "request_id": "draft-2",
            "planning_request": {},
            "trend_result": {"request_id": "draft-2", "status": "no_results"},
            "inventory_product_result": {"request_id": "draft-2", "status": "error"},
        })

        self.assertEqual(response["input_statuses"]["sales_market_result"], "not_provided")
        self.assertIsNone(response["draft"]["sales_market_result"])
        self.assertIsNone(response["input_evidence"]["sales_market_result"]["payload"])

    def test_accepts_notions_v1_nested_inputs_and_preserves_market_handoff(self):
        payload = {
            "planning_request": {
                "schema_version": "1.0", "request_id": "notion-1", "query": "27SS 아우터",
                "context": {
                    "season": {"value": "27SS", "source": "user", "raw": "27SS"},
                    "category": {"value": "outerwear", "source": "user", "raw": "아우터"},
                    "target_customer": {"value": "도심 통근자", "source": "user"},
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
        self.assertEqual(response["draft"]["target_customer"]["value"], "도심 통근자")
        self.assertEqual(response["draft"]["target_customer"]["kind"], "user_requested")

    def test_rejects_mismatched_upstream_request_id(self):
        payload = {"request_id": "r1", "planning_request": {"request_id": "r1"},
                   "trend_result": {"request_id": "r2"}, "inventory_product_result": {"request_id": "r1"}}
        with self.assertRaisesRegex(ValueError, "request_id"):
            _build_planning_draft_response(payload)

    def test_normalizes_trend_agent_and_stock_agent_outputs(self):
        trend_output = {
            "request_id": "repo-output-1", "status": "ok",
            "applied_filters": {"season": "27SS", "categories": ["아우터"]},
            "trends": [{
                "style": {
                    "id": "trend-style-1", "name": "Urban Utility",
                    "seasons": ["27SS"], "definition": "도시형 기능성",
                    "description": [{"text": "경량 레이어링과 절제된 배색", "evidence_ids": ["trend-E1"]}],
                    "focus_core": ["경량 소재"], "focus_supporting": ["컬러 블록"],
                    "focus_evidence_ids": ["trend-E1"],
                },
                "items": [{
                    "id": "trend-item-1", "name": "Light Anorak",
                    "category_major": "아우터", "category_minor": "점퍼",
                    "colors": ["올리브", "차콜"], "materials": ["나일론"],
                    "patterns": [], "details": [{"type": "실루엣", "name": "박시"}],
                    "fit": "루즈", "evidence_ids": ["trend-E2"],
                }],
            }],
            "evidence": [{"evidence_id": "trend-E1"}, {"evidence_id": "trend-E2"}],
            "limitations": ["샘플 상품 기반"],
        }
        stock_output = {
            "schema_version": "1.0", "request_id": "repo-output-1",
            "agent_id": "stock-agent", "status": "partial", "summary": "상품 1건",
            "products": [{
                "style_id": "ST-2041", "sku_ids": ["SKU-1"], "category": "점퍼",
                "season": "27SS", "attributes": {"color": "올리브", "material": "나일론"},
                "inventory": {"quantity": 2480, "unit": "장", "as_of": "2026-11-08",
                               "definition": "가용 재고", "data_nature": "sample"},
                "rank": 1, "matched_trend_color": "올리브", "reason": "경량 점퍼 재고",
                "image": {"url": "https://example.test/stock.jpg"},
                "trend_id": "trend-style-1", "trend_name": "Urban Utility",
                "evidence_ids": ["stock-E1"],
            }],
            "findings": [{"text": "조회 대상 재고", "evidence_ids": ["stock-E2"]}],
            "evidence": [{"evidence_id": "stock-E1"}, {"evidence_id": "stock-E2"}],
            "limitations": ["합성 테스트 데이터"], "errors": [],
        }
        response = _build_planning_draft_response({
            "planning_request": {"schema_version": "1.0", "request_id": "repo-output-1",
                                 "query": "27SS 아우터 기획", "season": "27SS", "category": "아우터"},
            "trend_result": trend_output, "inventory_product_result": stock_output,
        })
        draft_text = str(response["draft"])
        self.assertIn("Urban Utility", draft_text)
        self.assertIn("경량 레이어링과 절제된 배색", draft_text)
        self.assertIn("올리브", draft_text)
        self.assertIn("2480 장", draft_text)
        self.assertTrue({"trend-E1", "trend-E2", "stock-E1", "stock-E2"}.issubset(response["evidence_ids"]))
        self.assertEqual(response["input_evidence"]["trend_result"]["payload"], trend_output)
        self.assertEqual(response["input_evidence"]["inventory_product_result"]["payload"], stock_output)


if __name__ == "__main__":
    unittest.main()
