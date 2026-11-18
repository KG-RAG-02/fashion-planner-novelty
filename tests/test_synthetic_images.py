"""오프라인 합성 이미지 제공자(NOVELTY_DRAFT_IMAGE_PROVIDER=synthetic).

PNG가 표준 형식이고 'SYNTHETIC' 글자가 실제로 그려지는지, 같은 입력이면 어느 환경에서나 같은 바이트인지,
응답 계약·저장·원장이 OpenAI 경로와 같은지 확인한다.
"""
import hashlib
import os
import re
import sqlite3
import struct
import tempfile
import unittest
import urllib.error
import zlib
from pathlib import Path
from unittest.mock import patch

from fashion_planner_novelty.server import app as server_app
from fashion_planner_novelty.server.app import _build_handoff_run
from fashion_planner_novelty.workflows.draft_artifacts import DraftArtifactStore, OpenAIDraftImageProvider
from fashion_planner_novelty.workflows.image_generation import ImageProviderError
from fashion_planner_novelty.workflows.synthetic_images import (
    IMAGE_SIZE, LABEL_SCALE, LABEL_TOP, TITLE_SCALE, TITLE_TOP, SyntheticDraftImageProvider, text_mask, text_origin,
)
from test_handoff_runs import request

PRODUCT = {"category": "아우터", "color": "olive", "material": "nylon", "season": "2027SS"}
COMPANION = {"specification": {"category": "팬츠", "color": "navy"}, "role": "lower_body",
             "image": None, "media_type": None}
# 고정 입력의 상품 PNG 해시. 렌더링이나 인코딩이 바뀌면 이 값도 의도적으로 바꿔야 한다.
GOLDEN_PRODUCT_SHA256 = "ca533bf5de992d287354c8597825aa394ccaa41b2accd593a8c021f479e1672b"


def chunks(png: bytes) -> list[tuple[bytes, bytes]]:
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    found, offset = [], 8
    while offset < len(png):
        (length,) = struct.unpack(">I", png[offset:offset + 4])
        kind, data = png[offset + 4:offset + 8], png[offset + 8:offset + 8 + length]
        (crc,) = struct.unpack(">I", png[offset + 8 + length:offset + 12 + length])
        assert crc == zlib.crc32(kind + data), kind
        found.append((kind, data))
        offset += 12 + length
    return found


def pixels(png: bytes) -> list[bytes]:
    """팔레트 색인 행 목록(필터 바이트 제외)."""
    parts = dict(chunks(png))
    raw = zlib.decompress(parts[b"IDAT"])
    stride = IMAGE_SIZE + 1
    rows = [raw[y * stride:(y + 1) * stride] for y in range(IMAGE_SIZE)]
    assert all(row[0] == 0 for row in rows)
    return [row[1:] for row in rows]


def palette(png: bytes) -> list[tuple[int, int, int]]:
    data = dict(chunks(png))[b"PLTE"]
    return [tuple(data[i:i + 3]) for i in range(0, len(data), 3)]


class SyntheticImageTests(unittest.TestCase):
    def setUp(self):
        self.provider = SyntheticDraftImageProvider()
        self.product = self.provider.generate("product", PRODUCT, "rid-1")

    def outfit(self, reference=None, companion=COMPANION, product=PRODUCT):
        return self.provider.generate("outfit", product, "rid-1", reference_image=reference or self.product,
                                      companion=companion)

    def test_a_valid_palette_png(self):
        parts = chunks(self.product)
        self.assertEqual([kind for kind, _ in parts], [b"IHDR", b"PLTE", b"tEXt", b"IDAT", b"IEND"])
        width, height, depth, color_type = struct.unpack(">IIBB", parts[0][1][:10])
        self.assertEqual((width, height, depth, color_type), (IMAGE_SIZE, IMAGE_SIZE, 8, 3))
        self.assertEqual(len(pixels(self.product)), IMAGE_SIZE)
        self.assertIn(b"SYNTHETIC placeholder", dict(parts)[b"tEXt"])
        self.assertLess(len(self.product), 1_000_000)

    def test_the_word_synthetic_and_the_kind_are_drawn(self):
        for png, label in ((self.product, "PRODUCT"), (self.outfit(), "OUTFIT")):
            rows, colors = pixels(png), palette(png)
            for text, top, scale in (("SYNTHETIC", TITLE_TOP, TITLE_SCALE), (label, LABEL_TOP, LABEL_SCALE)):
                left = text_origin(text, scale)
                for r, line in enumerate(text_mask(text)):
                    for c, cell in enumerate(line):
                        x, y = left + c * scale + scale // 2, top + r * scale + scale // 2
                        ink = colors[rows[y][x]] == (20, 20, 20)
                        with self.subTest(text=text, row=r, column=c):
                            self.assertEqual(ink, cell == "#")

    def test_the_same_input_gives_the_same_bytes_everywhere(self):
        again = SyntheticDraftImageProvider().generate("product", dict(reversed(PRODUCT.items())), "other-request")
        self.assertEqual(again, self.product)  # 요청 ID나 키 순서와 무관
        self.assertEqual(hashlib.sha256(self.product).hexdigest(), GOLDEN_PRODUCT_SHA256)

    def test_the_colors_follow_the_inputs(self):
        self.assertNotEqual(self.provider.generate("product", {**PRODUCT, "color": "red"}, "rid-1"), self.product)
        outfit = self.outfit()
        self.assertNotEqual(self.outfit(reference=b"another product image"), outfit)
        self.assertNotEqual(self.outfit(companion={**COMPANION, "role": "upper_body"}), outfit)
        self.assertNotEqual(self.outfit(companion=None), outfit)
        # 착장의 새 상품 칸은 상품 이미지의 상품 칸과 같은 색이다.
        product_colors, outfit_colors = palette(self.product), palette(outfit)
        self.assertEqual(product_colors[2], outfit_colors[2])

    def test_an_outfit_needs_the_product_image(self):
        with self.assertRaises(ImageProviderError) as raised:
            self.provider.generate("outfit", PRODUCT, "rid-1", reference_image=None)
        self.assertEqual(raised.exception.code, "OUTFIT_REFERENCE_UNAVAILABLE")
        with self.assertRaises(ValueError):
            self.provider.generate("board", PRODUCT, "rid-1")


class SyntheticHandoffTests(unittest.TestCase):
    def setUp(self):
        guard = patch("urllib.request.urlopen",
                      side_effect=urllib.error.URLError(OSError("network is disabled in tests")))
        self.urlopen = guard.start()
        self.addCleanup(guard.stop)

    def run_synthetic(self, directory, value=None):
        with patch.dict(os.environ, {"NOVELTY_DRAFT_ARTIFACT_DIR": directory,
                                     "NOVELTY_DRAFT_IMAGE_PROVIDER": "synthetic"}), \
             patch.object(OpenAIDraftImageProvider, "generate") as paid:
            response = _build_handoff_run(value or request())
        self.assertFalse(paid.called)
        return response

    def test_the_visuals_follow_the_openai_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            response = self.run_synthetic(directory)
            result = response["result"]
            visuals = result["draft"]["visuals"]
            store = DraftArtifactStore(directory)
            for kind in ("product", "outfit"):
                visual = visuals[kind]
                with self.subTest(kind=kind):
                    self.assertEqual((visual["status"], visual["provider_calls"], visual["model"]),
                                     ("generated", 0, "synthetic"))
                    self.assertEqual(visual["prompt_version"], OpenAIDraftImageProvider.prompt_version)
                    self.assertEqual(visual["prompt_sha256"], OpenAIDraftImageProvider.prompt_sha256)
                    artifact = visual["artifact"]
                    self.assertRegex(artifact["uri"], r"^artifact://novelty/images/[0-9a-f]{64}\.png$")
                    self.assertEqual(artifact["media_type"], "image/png")
                    stored = Path(directory, "images", f"{artifact['sha256']}.png").read_bytes()
                    self.assertEqual((hashlib.sha256(stored).hexdigest(), len(stored)),
                                     (artifact["sha256"], artifact["size_bytes"]))
                    self.assertTrue(store.owns(response["request_id"], kind, artifact))
            self.assertEqual(visuals["outfit"]["reference_image_sha256"], visuals["product"]["artifact"]["sha256"])
            self.assertEqual((result["image"], result["outfit_image"]), (visuals["product"], visuals["outfit"]))
            metadata = result["generation_metadata"]
            self.assertEqual((metadata["image_provider"], metadata["image_model"]), ("synthetic", "synthetic"))
            self.assertTrue(any("SYNTHETIC" in item for item in result["limitations"]))
            self.assertFalse(any(issue["path"].startswith("draft.visuals") for issue in result["validation_issues"]))
        self.assertFalse(self.urlopen.called)

    def test_the_response_ledger_replays_without_a_paid_work_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            first = self.run_synthetic(directory)
            self.assertEqual(self.run_synthetic(directory), first)
            with sqlite3.connect(Path(directory, "ownership.sqlite3")) as conn:
                claims = conn.execute("SELECT COUNT(*) FROM image_run").fetchone()[0]
                issued = conn.execute("SELECT kind FROM issued ORDER BY kind").fetchall()
            self.assertEqual(claims, 0)
            self.assertEqual(issued, [("outfit",), ("product",)])

    def test_the_paid_image_capacity_slot_does_not_block_synthetic_images(self):
        self.assertTrue(server_app.IMAGE_REQUEST_SLOT.acquire(blocking=False))
        try:
            with tempfile.TemporaryDirectory() as directory:
                visuals = self.run_synthetic(directory)["result"]["draft"]["visuals"]
        finally:
            server_app.IMAGE_REQUEST_SLOT.release()
        self.assertTrue(all(item["status"] == "generated" for item in visuals.values()))

    def test_an_unresolved_category_still_skips_both_images(self):
        value = request()
        value["input"]["planning_request"].pop("category")
        value["input"]["planning_request"].pop("season")
        with tempfile.TemporaryDirectory() as directory:
            visuals = self.run_synthetic(directory, value)["result"]["draft"]["visuals"]
            self.assertEqual(list(Path(directory, "images").iterdir()), [])
        self.assertTrue(all((item["status"], item["error_code"]) == ("skipped", "PRODUCT_CATEGORY_UNRESOLVED")
                            for item in visuals.values()))


if __name__ == "__main__":
    unittest.main()
