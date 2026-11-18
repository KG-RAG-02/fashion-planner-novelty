"""The outfit image pairs the new product with one stock item (VOGUE decision 2026-11-17)."""

from __future__ import annotations

import base64
import json
import unittest
from unittest.mock import patch

from fashion_planner_novelty.domain.context import (
    AgentResult,
    AttributeSignal,
    InventoryProduct,
    InventoryProductResult,
    InventoryTrendResult,
    PlanningInputs,
    PlanningRequest,
    TrendCandidate,
    TrendResult,
    build_planning_context,
)
from fashion_planner_novelty.domain.outfit_companion import OUTFIT_COMPANION_RULE, OutfitCompanion, select_outfit_companion
from fashion_planner_novelty.domain.trend_basis import select_primary_trend
from fashion_planner_novelty.prototype.server import _companion_photo
from fashion_planner_novelty.workflows import image_generation
from fashion_planner_novelty.workflows.draft_artifacts import OpenAIDraftImageProvider
from fashion_planner_novelty.workflows.image_generation import ImageGenerationRequest, ImageProviderError, OpenAIImageEditProvider

RID, SCHEMA = "outfit-companion-1", "1.0"


def signal(name, value, *ids):
    return AttributeSignal(name, value, "evidence_observation", tuple(ids))


def trend(name, style, *attributes, ids):
    return TrendCandidate(name=name, qualification="trend_analysis_result", season="2026FW", category="재킷",
                          attributes=tuple(attributes), evidence_ids=tuple(ids), source_style_id=style)


COWBOY = trend("카우보이 스타일", "990101-s0", signal("detail", "프린지", "cow:1"), signal("color", "브라운", "cow:2"),
               ids=("cow:0",))
DIRTY = trend("더티코어", "990105-s0", signal("color", "블랙", "dirt:1"), ids=("dirt:0",))


def product(index, style_id, category, **attributes):
    evidence = f"stock:{style_id}:{index}"
    return InventoryProduct(
        style_id=style_id, sku_ids=(), category=category, evidence_ids=(evidence,), source_product_index=index,
        attributes=tuple(signal(name, value, evidence) for name, values in attributes.items()
                         for value in (values if isinstance(values, tuple) else (values,))),
    )


def slot(index, style_id, product_index, *, rank=1, status="ok", mapping_status="linked"):
    return InventoryTrendResult(trend_result_index=index, style_id=style_id, style_name=None, status=status,
                                product_index=product_index, mapping_status=mapping_status,
                                trend_input_match="matched", rank=rank)


PANTS = product(1, "0764600", "팬츠", color="베이지", fit="와이드", material=("면", "코듀로이"))
DRESS = product(0, "0838846", "드레스", color="블랙")
SHIRT = product(2, "0711111", "상의", color="화이트")


def context_of(products, slots, *, query="2026FW 남성 재킷 기획"):
    candidates = (DIRTY, COWBOY)
    trend_ids = tuple(sorted({eid for c in candidates for eid in (*c.evidence_ids,
                                                                    *(e for s in c.attributes for e in s.evidence_ids))}))
    stock_ids = tuple(sorted({eid for p in products for eid in p.evidence_ids}))
    return build_planning_context(PlanningInputs(
        PlanningRequest(AgentResult("user-request", RID, SCHEMA, "ok"), original_query=query, season="2026FW",
                        category="재킷", field_origins={"season": "user", "category": "user"}),
        TrendResult(AgentResult("trend-analysis-agent", RID, SCHEMA, "ok", evidence_ids=trend_ids),
                    candidates=candidates),
        InventoryProductResult(AgentResult("stock-agent", RID, SCHEMA, "ok", evidence_ids=stock_ids),
                               products=tuple(products), trend_results=tuple(slots)),
    ))


def companion_of(context):
    return select_outfit_companion(context, select_primary_trend(context))


class SelectionTests(unittest.TestCase):
    def test_the_primary_trends_stock_slot_gives_the_companion(self):
        context = context_of((DRESS, PANTS), (slot(0, "990105-s0", 0), slot(1, "990101-s0", 1)))
        self.assertEqual(select_primary_trend(context).name, "카우보이 스타일")
        companion = companion_of(context)
        self.assertEqual((companion.product_index, companion.style_id, companion.trend_style_id, companion.rank),
                         (1, "0764600", "990101-s0", 1))
        self.assertEqual((companion.role, companion.selection_rule), ("lower_body", OUTFIT_COMPANION_RULE))
        self.assertEqual(companion.specification(), {
            "stock_product_id": "0764600", "category": "팬츠", "color": "베이지", "fit": "와이드",
            "material": ["면", "코듀로이"],
        })

    def test_best_rank_first(self):
        other = product(3, "0714927", "청바지", color="블랙")
        context = context_of((DRESS, PANTS, SHIRT, other),
                             (slot(0, "990101-s0", 3, rank=2), slot(1, "990101-s0", 1, rank=1)))
        self.assertEqual(companion_of(context).style_id, "0764600")

    def test_an_item_in_the_new_products_role_is_skipped(self):
        context = context_of((DRESS, PANTS, SHIRT),
                             (slot(0, "990101-s0", 2, rank=1), slot(1, "990101-s0", 1, rank=2)))
        self.assertEqual(companion_of(context).style_id, "0764600")  # the shirt (a top) cannot go with a jacket
        self.assertIsNone(companion_of(context_of((DRESS, PANTS, SHIRT), (slot(0, "990101-s0", 2),))))

    def test_an_item_without_a_known_role_is_kept(self):
        companion = companion_of(context_of((DRESS, PANTS), (slot(0, "990101-s0", 0),)))
        self.assertEqual((companion.style_id, companion.role), ("0838846", None))  # a jacket over a dress

    def test_other_trends_slots_unlinked_or_failed_slots_give_none(self):
        for slots in (
            (slot(0, "990105-s0", 1),),
            (slot(0, "990101-s0", 1, mapping_status="no_product"),),
            (slot(0, "990101-s0", 1, status="error"),),
            (),
        ):
            with self.subTest(slots=slots):
                self.assertIsNone(companion_of(context_of((DRESS, PANTS), slots)))


def companion(image=b"stock-jpeg", role="lower_body"):
    return {"specification": {"stock_product_id": "0764600", "category": "팬츠", "color": "베이지"},
            "role": role, "image": image, "media_type": "image/jpeg"}


class OutfitPromptTests(unittest.TestCase):
    def generate(self, **kwargs):
        provider = OpenAIDraftImageProvider("test-key", "gpt-image-test")
        with patch.object(OpenAIImageEditProvider, "edit", autospec=True) as edit:
            edit.return_value.image_bytes = b"outfit"
            self.assertEqual(provider.generate("outfit", {"category": "재킷"}, "rid", reference_image=b"product",
                                               **kwargs), b"outfit")
        (_self, request, reference), options = edit.call_args
        self.assertEqual(reference, b"product")
        return request.prompt, options["extra_images"]

    def test_the_stock_photo_is_input_image_2(self):
        prompt, extra_images = self.generate(companion=companion())
        self.assertEqual(extra_images, ((b"stock-jpeg", "image/jpeg"),))
        self.assertIn("Input image 2 is the photograph of an existing stock item", prompt)
        self.assertIn("wearing this exact new garment together with the exact existing stock item shown in "
                      "input image 2 as the bottom", prompt)
        self.assertIn('STOCK ITEM (input image 2):\n{"category":"팬츠","color":"베이지","stock_product_id":"0764600"}',
                      prompt)

    def test_without_a_photo_the_stock_item_is_described(self):
        prompt, extra_images = self.generate(companion=companion(image=None, role=None))
        self.assertEqual(extra_images, ())
        self.assertNotIn("Input image 2", prompt)
        self.assertIn("together with the existing stock item described in the STOCK ITEM JSON below, styled", prompt)
        self.assertIn("STOCK ITEM (no photograph):", prompt)

    def test_without_a_companion_the_outfit_shows_the_new_product_alone(self):
        prompt, extra_images = self.generate()
        self.assertEqual(extra_images, ())
        self.assertNotIn("STOCK ITEM", prompt)
        self.assertIn("show this exact garment worn by a model", prompt)

    def test_the_product_prompt_ignores_the_companion(self):
        provider = OpenAIDraftImageProvider("test-key", "gpt-image-test")
        with patch.object(image_generation.OpenAIImageProvider, "generate", autospec=True) as generate:
            generate.return_value.image_bytes = b"product"
            provider.generate("product", {"category": "재킷"}, "rid")
        self.assertNotIn("STOCK ITEM", generate.call_args.args[1].prompt)


class EditRequestTests(unittest.TestCase):
    def request(self):
        return ImageGenerationRequest(request_id="rid:outfit", season=None, category="재킷", prompt="p",
                                      prompt_version="v", prompt_sha256="0" * 64, evidence_ids=(),
                                      proposal_fields=(), limitations=(), conflicts=())

    def test_reference_images_are_sent_in_order(self):
        captured = {}

        def post(endpoint, api_key, body, timeout):
            captured.update(body)
            return {"data": [{"b64_json": base64.b64encode(b"out").decode("ascii")}]}

        with patch.object(image_generation, "_post_images_api", side_effect=post):
            OpenAIImageEditProvider(api_key="k").edit(self.request(), b"one", extra_images=((b"two", "image/jpeg"),))
        self.assertEqual(captured["images"], [
            {"image_url": "data:image/png;base64," + base64.b64encode(b"one").decode("ascii")},
            {"image_url": "data:image/jpeg;base64," + base64.b64encode(b"two").decode("ascii")},
        ])

    def test_an_unusable_extra_image_is_refused_before_any_call(self):
        with patch.object(image_generation, "_post_images_api") as post:
            for extra, code in (((b"two", "image/gif"),), "IMAGE_API_REFERENCE_FORMAT_UNSUPPORTED"), \
                               (((b"", "image/jpeg"),), "IMAGE_API_REFERENCE_MISSING"):
                with self.subTest(code=code), self.assertRaises(ImageProviderError) as raised:
                    OpenAIImageEditProvider(api_key="k").edit(self.request(), b"one", extra_images=extra)
                self.assertEqual(raised.exception.code, code)
        post.assert_not_called()


class CompanionPhotoTests(unittest.TestCase):
    COMPANION = OutfitCompanion(product_index=0, style_id="0764600", category="팬츠", attributes=(),
                                trend_style_id="990101-s0", rank=1, role="lower_body")

    @staticmethod
    def image(data=b"jpeg-bytes", media_type="image/jpeg"):
        return {"data": base64.b64encode(data).decode("ascii"), "media_type": media_type, "encoding": "base64"}

    def test_its_own_photo_first_then_the_first_photo_of_the_same_product(self):
        own = {"products": [{"style_id": "0764600", "image": self.image(b"own")},
                            {"style_id": "0764600", "image": self.image(b"other")}]}
        self.assertEqual(_companion_photo(own, self.COMPANION), (b"own", "image/jpeg"))
        deduplicated = {"products": [{"style_id": "0764600", "image": None},
                                     {"style_id": "0838846", "image": self.image(b"dress")},
                                     {"style_id": "0764600", "image": self.image(b"first-copy")}]}
        self.assertEqual(_companion_photo(deduplicated, self.COMPANION), (b"first-copy", "image/jpeg"))

    def test_unusable_or_missing_photos_give_none(self):
        bad_base64 = dict(self.image(), data="not base64!")
        for payload in (
            {"products": [{"style_id": "0764600", "image": None}]},
            {"products": [{"style_id": "0764600", "image": self.image(media_type="image/gif")}]},
            {"products": [{"style_id": "0764600", "image": bad_base64}]},
            {"products": [{"style_id": "0764600", "image": {"url": "https://example.invalid/a.jpg"}}]},
            {"products": []},
            None,
        ):
            with self.subTest(payload=json.dumps(payload)[:80]):
                self.assertEqual(_companion_photo(payload, self.COMPANION), (None, None))
        self.assertEqual(_companion_photo({"products": [{"style_id": "0764600", "image": self.image()}]}, None),
                         (None, None))


if __name__ == "__main__":
    unittest.main()
