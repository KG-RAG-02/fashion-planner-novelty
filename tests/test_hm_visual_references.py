import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vogue_npp.sources.hm_visual_references import OpenAIHMImageAnalyzer, analyze_hm_visual_references


class FakeCatalog:
    def find_hm_catalog_candidates(self, category, *, limit=12):
        self.category = category
        return [{"article_id": "0999991001", "prod_name": "Strap top", "kf_area": "상의"}]


class FakeImageStore:
    def load(self, article_id):
        self.article_id = article_id
        return b"\xff\xd8\xffimage", "image/jpeg"


class FakeAnalyzer:
    model = "fake-vision"
    calls = 0

    def analyze(self, image_bytes, *, article_id, catalog_context):
        self.calls += 1
        self.seen = (image_bytes, article_id, catalog_context)
        return {
            "visual_summary": "상의 사진의 색과 형태",
            "visible_features": ["민소매 상의"], "visible_colors": ["검정"],
            "silhouette": "슬림", "visible_details": [], "not_assessable": ["소재 조성"],
            "analysis_model": self.model, "analysis_method": "fake",
        }


class HmVisualReferenceTests(unittest.TestCase):
    def test_r2_photo_analysis_is_category_scoped_and_cached(self):
        catalog, image_store, analyzer = FakeCatalog(), FakeImageStore(), FakeAnalyzer()
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "VOGUE_HM_KAGGLE_IMAGE_ALLOW_PROVIDER_UPLOAD": "true",
            "VOGUE_R2_IMAGE_ALLOW_PROVIDER_UPLOAD": "true",
            "VOGUE_HM_IMAGE_ANALYSIS_ENABLED": "true",
        }, clear=True):
            first = analyze_hm_visual_references(
                catalog, category="tops", api_key="test-key", image_store=image_store,
                analyzer=analyzer, cache_dir=Path(directory),
            )
            second = analyze_hm_visual_references(
                catalog, category="tops", api_key="test-key", image_store=image_store,
                analyzer=analyzer, cache_dir=Path(directory),
            )
        self.assertEqual(catalog.category, "tops")
        self.assertEqual(image_store.article_id, "0999991001")
        self.assertEqual(first["status"], "ok")
        self.assertEqual(first["data_nature"], "external_reference")
        self.assertEqual(first["references"][0]["article_id"], "0999991001")
        self.assertEqual(first["references"][0]["image_url"], "/api/hm-reference-images/0999991001.jpg")
        self.assertEqual(second["references"][0]["analysis_status"], "cached")
        self.assertEqual(analyzer.calls, 1)
        self.assertIn("image_sha256", first["references"][0])

    def test_external_provider_block_prevents_image_download_and_analysis(self):
        catalog, image_store, analyzer = FakeCatalog(), FakeImageStore(), FakeAnalyzer()
        with patch.dict(os.environ, {
            "VOGUE_HM_KAGGLE_IMAGE_ALLOW_PROVIDER_UPLOAD": "false",
            "VOGUE_R2_IMAGE_ALLOW_PROVIDER_UPLOAD": "true",
        }, clear=True):
            result = analyze_hm_visual_references(
                catalog, category="tops", api_key="test-key", image_store=image_store, analyzer=analyzer,
            )
        self.assertEqual(result["status"], "analysis_blocked")
        self.assertEqual(image_store.__dict__, {})
        self.assertEqual(analyzer.calls, 0)

    def test_responses_api_image_request_parses_visual_only_json(self):
        payload = {"output": [{"content": [{"type": "output_text", "text": json.dumps({
            "visual_summary": "light jacket", "visible_features": ["hood"], "visible_colors": ["sage"],
            "silhouette": "relaxed", "visible_details": ["zip front"], "not_assessable": ["fiber composition"],
        })}]}]}

        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, *_args):
                return False
            def read(self):
                return json.dumps(payload).encode("utf-8")

        with patch("urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
            result = OpenAIHMImageAnalyzer("test-key", model="test-model").analyze(
                b"jpeg-bytes", article_id="0999991001", catalog_context={"kf_area": "상의"},
            )
        request = urlopen.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(body["model"], "test-model")
        self.assertEqual(body["input"][0]["content"][1]["type"], "input_image")
        self.assertIn("data:image/jpeg;base64,", body["input"][0]["content"][1]["image_url"])
        self.assertEqual(result["visible_features"], ["hood"])
        self.assertIn("fiber composition", result["not_assessable"])


if __name__ == "__main__":
    unittest.main()
