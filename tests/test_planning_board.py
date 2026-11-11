from __future__ import annotations

import base64
import tempfile
import unittest
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path
from datetime import date

from vogue_npp.domain.context import (
    AgentResult, AttributeSignal, InventoryProduct, InventoryProductResult,
    PlanningInputs, PlanningRequest, TrendCandidate, TrendResult, build_planning_context,
)
from vogue_npp.domain.generator import RuleBasedConceptGenerator
from vogue_npp.domain.retrieval import EvidenceRef, PlanningKnowledgeContext, PurposeRetrieval
from vogue_npp.workflows.planning_board import build_planning_board, render_planning_board_svg


class PlanningBoardTests(unittest.TestCase):
    def make_board(self, sales=None):
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
        context = build_planning_context(PlanningInputs(
            request, trend, inventory,
            sales_market_result=sales,
        ))
        draft, _ = RuleBasedConceptGenerator().generate(context)
        return build_planning_board(context, draft)

    def test_board_links_claims_to_source_and_keeps_sales_opaque(self):
        board = self.make_board({
            "request_id": "board-test-1", "agent_id": "sales-market-agent", "status": "partial",
            "schema_version": "1.0", "findings": [{"text": "opaque finding", "evidence_ids": ["MARKET-E1"]}],
        })
        trend = next(section for section in board.sections if section.section_id == "trend")
        self.assertTrue(any("TREND-E1" in claim.evidence_ids for claim in trend.claims))
        sales = next(section for section in board.sections if section.section_id == "sales_market")
        self.assertEqual(sales.state, "blocked")
        self.assertTrue(any("MARKET-E1" in claim.evidence_ids for claim in sales.claims))
        self.assertFalse(any("opaque finding" in claim.text for claim in sales.claims))

    def test_svg_renderer_places_exact_evidence_labels_and_embeds_product_visual(self):
        board = self.make_board({
            "request_id": "board-test-1", "agent_id": "sales-market-agent", "status": "partial",
            "schema_version": "1.0", "findings": [{"text": "opaque finding", "evidence_ids": ["MARKET-E1"]}],
        })
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "product.png"
            image.write_bytes(b"fake-png")
            svg = render_planning_board_svg(board, image).decode("utf-8")
        self.assertIn("TREND-E1", svg)
        self.assertIn("REQ-E1", svg)
        self.assertIn(base64.b64encode(b"fake-png").decode("ascii"), svg)
        self.assertIn("MD 검토용 초안 · 자동 승인 아님", svg)
        self.assertIn("상세 해석 보류", svg)
        ET.fromstring(svg)

    def test_synthetic_rag_context_is_explicit_on_board(self):
        context = build_planning_context(PlanningInputs(
            PlanningRequest(AgentResult("request-agent", "board-test-1", "1.0", "ok"), season="2027FW", category="outerwear"),
            TrendResult(AgentResult("trend-agent", "board-test-1", "1.0", "no_results")),
            InventoryProductResult(AgentResult("stock-agent", "board-test-1", "1.0", "no_results")),
        ))
        synthetic_ref = EvidenceRef(
            "SYN-EV-BOARD", "SYN-SRC-BOARD", "doc/section", "SYN-STYLE-1: color=sage", date(2026, 11, 11),
            "synthetic_only", True, source_type="catalog_record", source_name="Synthetic catalog",
            permission_status="synthetic_only", permitted_uses=("product_planning",),
            dataset_id="SYNTHETIC-TEST-001", is_synthetic=True,
            synthetic_notice="합성 데이터이며 실제 회사 정책·상품·성과가 아닙니다.",
        )
        enriched = replace(context, planning_knowledge=PlanningKnowledgeContext((
            PurposeRetrieval("catalog_comparison", "ok", evidence=(synthetic_ref,)),
        )))
        draft, _ = RuleBasedConceptGenerator().generate(enriched)
        synthetic_board = build_planning_board(enriched, draft)
        self.assertTrue(synthetic_board.synthetic_context)
        self.assertEqual(synthetic_board.synthetic_dataset_ids, ("SYNTHETIC-TEST-001",))
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "product.png"
            image.write_bytes(b"fake-png")
            svg = render_planning_board_svg(synthetic_board, image).decode("utf-8")
        self.assertIn("합성 데이터 참고", svg)
        self.assertIn("SYN-EV-BOARD", svg)


if __name__ == "__main__":
    unittest.main()
