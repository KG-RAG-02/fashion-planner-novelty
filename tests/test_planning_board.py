from __future__ import annotations

import base64
import tempfile
import unittest
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

from vogue_npp.domain.context import (
    AgentResult, AttributeSignal, InventoryProduct, InventoryProductResult,
    PlanningInputs, PlanningRequest, TrendCandidate, TrendResult, build_planning_context,
)
from vogue_npp.domain.generator import RuleBasedConceptGenerator
from vogue_npp.workflows.planning_board import build_planning_board, render_planning_board_svg


class PlanningBoardTests(unittest.TestCase):
    def make_board(self):
        request_id = "board-test-1"
        request = PlanningRequest(
            AgentResult("request-agent", request_id, "1.0", "ok", ("REQ-E1",)),
            original_query="27FW 아웃도어 상의 기획",
            season="2027FW", category="outdoor", product_role="upper_body",
            requested_attributes=(AttributeSignal("color", "olive", "user_requested", ("REQ-E1",)),),
            field_origins={"season": "user", "category": "user"},
        )
        trend = TrendResult(
            AgentResult("trend-agent", request_id, "1.0", "partial", ("TREND-E1",)),
            (TrendCandidate(
                "Utility", "candidate", season="2027FW", category="outdoor",
                attributes=(AttributeSignal("material", "nylon", "evidence_observation", ("TREND-E1",)),),
                evidence_ids=("TREND-E1",),
            ),),
        )
        inventory = InventoryProductResult(
            AgentResult("stock-agent", request_id, "1.0", "partial", ("STOCK-E1",)),
            (InventoryProduct("JEAN-1", (), category="denim", product_role="lower_body",
                              quantity=5, unit="pieces", as_of="2026-11-10",
                              evidence_ids=("STOCK-E1",)),),
        )
        context = build_planning_context(PlanningInputs(request, trend, inventory))
        draft, _ = RuleBasedConceptGenerator().generate(context)
        return build_planning_board(context, draft)

    def test_board_contains_only_request_trend_and_inventory_sections(self):
        board = self.make_board()
        trend = next(section for section in board.sections if section.section_id == "trend")
        self.assertTrue(any("TREND-E1" in claim.evidence_ids for claim in trend.claims))
        self.assertNotIn("sales_market", {section.section_id for section in board.sections})
        self.assertNotIn("references", {section.section_id for section in board.sections})

    def test_svg_renderer_places_exact_evidence_labels_and_embeds_product_visual(self):
        board = self.make_board()
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "product.png"
            image.write_bytes(b"fake-png")
            svg = render_planning_board_svg(board, image).decode("utf-8")
        self.assertIn("TREND-E1", svg)
        self.assertIn("REQ-E1", svg)
        self.assertIn(base64.b64encode(b"fake-png").decode("ascii"), svg)
        self.assertIn("MD 검토용 초안 · 자동 승인 아님", svg)
        self.assertNotIn("판매·시장", svg)
        ET.fromstring(svg)

if __name__ == "__main__":
    unittest.main()
