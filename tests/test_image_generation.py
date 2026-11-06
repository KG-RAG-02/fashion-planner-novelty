from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vogue_npp import (
    AgentResult,
    AttributeSignal,
    GeneratedImage,
    PlanningInputs,
    PlanningRequest,
    TrendCandidate,
    build_planning_context,
    run_concept_to_image,
)
from vogue_npp.domain.context import InventoryProductResult, TrendResult
from vogue_npp.workflows.image_generation import OpenAIImageProvider


class FakeImageProvider:
    provider_name = "fake-image-provider"
    model = "fake-model-v1"

    def __init__(self, image_bytes: bytes = b"fake-png") -> None:
        self.image_bytes = image_bytes
        self.calls = 0

    def generate(self, request):
        self.calls += 1
        self.request = request
        return GeneratedImage(self.image_bytes, "image/png", self.provider_name, self.model)


def make_context(
    *, inventory_category: str | None = None, trend_evidence: bool = True,
    original_query: str = "27FW 아웃도어 콘셉트", inventory_note: str | None = None,
    inventory_quantity: int | None = None, inventory_evidence: bool = False,
):
    request_id = "image-test-001"
    schema = "internal-prototype-0"
    request = PlanningRequest(
        result=AgentResult("user-request", request_id, schema, "ok"),
        original_query=original_query,
        season="2027FW",
        category="outdoor",
        requested_attributes=(AttributeSignal("color", "forest green", "user_requested"),),
        field_origins={"season": "user", "category": "user"},
    )
    evidence_ids = ("query-trend:E-1",) if trend_evidence else ()
    trend = TrendResult(
        result=AgentResult("query-trend-agent", request_id, schema, "partial", evidence_ids=evidence_ids),
        candidates=(TrendCandidate(
            name="절제된 맥시멀리즘",
            qualification="candidate",
            season="2027FW",
            category="outdoor",
            attributes=(AttributeSignal("pattern", "oversized floral", "evidence_observation", evidence_ids),) if trend_evidence else (),
            evidence_ids=evidence_ids,
        ),),
    )
    inventory = InventoryProductResult(
        result=AgentResult("inventory-agent", request_id, schema, "partial"),
        products=(),
    )
    if inventory_category or inventory_note:
        from vogue_npp.domain.context import InventoryProduct
        inventory = InventoryProductResult(
            result=inventory.result,
            products=(InventoryProduct(
                "JEAN-STYLE-1" if inventory_evidence else None,
                ("JEAN-SKU-1",) if inventory_evidence else (),
                category=inventory_category,
                note=inventory_note,
                note_origin="user" if inventory_note else "unknown",
                product_role="lower_body" if inventory_category else None,
                quantity=inventory_quantity,
                unit="pieces" if inventory_quantity is not None else None,
                inventory_definition="available_to_sell" if inventory_evidence else None,
                as_of="2026-11-06" if inventory_evidence else None,
                evidence_ids=("inventory:E-1",) if inventory_evidence else (),
                attributes=(AttributeSignal("color", "dark indigo", "evidence_observation", ("inventory:E-2",)),) if inventory_evidence else (),
            ),),
        )
    return build_planning_context(PlanningInputs(request, trend, inventory))


class ImageGenerationWorkflowTests(unittest.TestCase):
    def test_prompt_distinguishes_evidence_user_request_and_proposal(self) -> None:
        result = run_concept_to_image(make_context())
        prompt = result.image.request.prompt
        self.assertEqual(result.image.status, "not_requested")
        self.assertIn("절제된 맥시멀리즘", prompt)
        self.assertIn("oversized floral", prompt)
        self.assertIn("query-trend:E-1", prompt)
        self.assertIn("forest green", prompt)
        self.assertIn("사용자가 지정한 조건", prompt)
        self.assertIn("시각화 제안", prompt)
        self.assertIn("생산 지시가 아닙니다", prompt)

    def test_unverified_trend_is_not_used_as_image_fact(self) -> None:
        result = run_concept_to_image(make_context(trend_evidence=False))
        self.assertNotIn("근거 연결 트렌드명: 절제된 맥시멀리즘", result.image.request.prompt)
        self.assertIn("근거 ID가 없는 트렌드명", " ".join(result.image.request.limitations))
        self.assertNotIn("소재=", result.image.request.prompt)

    def test_category_conflict_blocks_generation_but_retains_prompt(self) -> None:
        provider = FakeImageProvider()
        result = run_concept_to_image(
            make_context(inventory_category="denim"),
            provider=provider,
            image_generation_enabled=True,
            confirm_image_generation=True,
        )
        self.assertEqual(result.image.status, "blocked")
        self.assertTrue(result.image.request.conflicts)
        self.assertEqual(provider.calls, 0)
        self.assertIn("해결되지 않은 입력 충돌", result.image.request.prompt)

    def test_complementary_bottom_stock_is_pairing_context_not_category_conflict(self) -> None:
        context = make_context(
            inventory_category="denim",
            inventory_note="청바지가 많이 남는다",
            original_query="27년 겨울 유행할 아웃도어 상의 제안해줘",
        )
        result = run_concept_to_image(context)
        self.assertFalse(context.conflicts)
        self.assertEqual(len(context.styling_relationships), 1)
        relation = context.styling_relationships[0]
        self.assertEqual((relation.requested_role, relation.inventory_role), ("upper_body", "lower_body"))
        self.assertEqual(relation.rule_version, "outfit-role-pairing-v1")
        self.assertIn("상의", result.draft.product_definition.value or "")
        pairing_claim = next(
            claim for claim in result.draft.relation_to_own_products
            if "코디 기획 제안" in (claim.value or "")
        )
        self.assertEqual(pairing_claim.kind, "interpretation")
        self.assertFalse(pairing_claim.evidence_ids)
        self.assertIn("청바지가 많이 남는다", pairing_claim.value or "")
        self.assertIn("미확인 정보", pairing_claim.value or "")
        self.assertIn("요청 신상품: outdoor 상의", result.image.request.prompt)
        self.assertIn("함께 코디할 재고 맥락: 청바지 (하의)", result.image.request.prompt)
        self.assertIn("재고 소진·매출 효과의 증거가 아님", result.image.request.prompt)
        self.assertNotIn("카테고리 불일치", result.image.request.prompt)

    def test_freeform_jeans_note_maps_to_bottom_role_without_fabricating_category_or_stock(self) -> None:
        context = make_context(
            inventory_note="청바지가 많이 남는다",
            original_query="27년 겨울 아웃도어 상의 제안",
        )
        result = run_concept_to_image(context)
        relation = context.styling_relationships[0]
        self.assertEqual(relation.inventory_role_source, "inventory note keyword mapping")
        product = context.inventory.products[0]
        self.assertIsNone(product.category)
        self.assertIsNone(product.quantity)
        self.assertIsNone(product.as_of)
        self.assertFalse(product.evidence_ids)
        self.assertIn("청바지 (하의)", result.image.request.prompt)
        self.assertIn("수량, 기준일 및 실제 재고 상태를 추정하지 않음", result.image.request.prompt)

    def test_evidenced_companion_stock_facts_stay_separate_from_new_top_attributes(self) -> None:
        context = make_context(
            inventory_category="denim",
            original_query="아웃도어 상의 제안",
            inventory_quantity=84,
            inventory_evidence=True,
        )
        result = run_concept_to_image(context)
        stock_claim = next(
            claim for claim in result.draft.relation_to_own_products
            if "재고 스냅샷" in (claim.value or "")
        )
        self.assertEqual(stock_claim.kind, "evidence_observation")
        self.assertEqual(stock_claim.evidence_ids, ("inventory:E-1",))
        self.assertIn("84 pieces", stock_claim.value or "")
        self.assertIn("2026-11-06", stock_claim.value or "")
        self.assertNotIn(("color", "dark indigo"), {(a.name, a.value) for a in result.draft.attributes})
        self.assertIn("코디 맥락의 재고 상품 속성: color=dark indigo", " ".join(
            claim.value or "" for claim in result.draft.relation_to_own_products
        ))
        self.assertIn("inventory:E-2", result.image.request.evidence_ids)
        self.assertIn("재고 상품의 관찰 속성 (상의 속성이 아님): color=dark indigo", result.image.request.prompt)

    def test_fake_provider_generates_only_after_two_opt_ins_and_persists_link(self) -> None:
        provider = FakeImageProvider()
        pairing_context = make_context(
            inventory_category="denim",
            inventory_note="청바지가 많이 남는다",
            original_query="아웃도어 상의 제안",
        )
        with tempfile.TemporaryDirectory() as tmp:
            not_confirmed = run_concept_to_image(
                pairing_context, provider=provider,
                image_generation_enabled=True, confirm_image_generation=False,
                output_dir=Path(tmp),
            )
            self.assertEqual(not_confirmed.image.status, "ready")
            self.assertEqual(provider.calls, 0)
            result = run_concept_to_image(
                pairing_context, provider=provider,
                image_generation_enabled=True, confirm_image_generation=True,
                output_dir=Path(tmp),
            )
            self.assertEqual(result.image.status, "generated")
            self.assertEqual(provider.calls, 1)
            path = Path(result.image.image_path or "")
            self.assertEqual(path.read_bytes(), b"fake-png")
            self.assertEqual(result.image.request.request_id, result.draft.request_id)
            self.assertEqual(result.image.model, "fake-model-v1")
            self.assertTrue(result.image.review_only)
            self.assertFalse(result.image.request.conflicts)
            self.assertIn("청바지가 많이 남는다", provider.request.prompt)

    def test_openai_adapter_decodes_image_without_real_network_call(self) -> None:
        from vogue_npp.workflows.image_generation import build_image_generation_request
        draft_context = make_context()
        from vogue_npp.domain.generator import RuleBasedConceptGenerator
        draft, _ = RuleBasedConceptGenerator().generate(draft_context)
        image_request = build_image_generation_request(draft_context, draft)
        response = {"data": [{"b64_json": base64.b64encode(b"png-bytes").decode("ascii")}]}

        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self):
                return json.dumps(response).encode("utf-8")

        with patch("urllib.request.urlopen", return_value=FakeResponse()) as open_url:
            generated = OpenAIImageProvider(api_key="secret-test-key").generate(image_request)
        self.assertEqual(generated.image_bytes, b"png-bytes")
        self.assertEqual(generated.model, "gpt-image-2.5-sunburst")
        self.assertNotIn("secret-test-key", repr(OpenAIImageProvider(api_key="secret-test-key")))
        self.assertEqual(open_url.call_count, 1)


if __name__ == "__main__":
    unittest.main()
