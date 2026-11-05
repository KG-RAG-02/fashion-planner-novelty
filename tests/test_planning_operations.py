from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

from vogue_npp.prototype.planning_operations import (
    calculate_ratio_kpi,
    get_product,
    load_fixture,
    validate_fixture,
)
from vogue_npp.prototype.server import PrototypeHandler


class PlanningOperationsTests(unittest.TestCase):
    def test_all_business_collections_declare_synthetic_provenance(self) -> None:
        fixture = load_fixture()
        self.assertEqual(fixture["data_status"], "synthetic")
        for name in ("line_plans", "markdown_reviews", "kpi_definitions", "product_details", "campaigns"):
            for record in fixture[name]:
                self.assertEqual(record["data_status"], "synthetic")
                self.assertTrue(record["source_id"])
                self.assertTrue(record["version"])
                self.assertTrue(record["as_of"])
                self.assertTrue(record["limitations"])

    def test_line_plan_markdown_product_and_campaign_references_are_valid(self) -> None:
        fixture = load_fixture()
        plan = fixture["line_plans"][0]
        self.assertEqual(plan["season_id"], "SYN-27SS")
        self.assertEqual(plan["season_label"], "27SS")
        self.assertEqual(sum(row["target_style_count"] for row in plan["product_groups"]), 20)
        markdown = fixture["markdown_reviews"][0]
        self.assertEqual(markdown["style_id"], "LW-2601")
        self.assertIsNone(markdown["observed_outcome"])
        self.assertEqual(fixture["campaigns"][0]["product_style_ids"], ["LW-2601"])
        self.assertEqual(fixture["campaigns"][0]["metrics"]["item_revenue"], None)

    def test_invalid_markdown_date_or_price_is_rejected(self) -> None:
        fixture = load_fixture()
        fixture["markdown_reviews"][0]["effective_to"] = "2026-01-01"
        with self.assertRaises(ValueError):
            validate_fixture(fixture)

    def test_kpi_is_not_calculable_with_zero_or_missing_denominator(self) -> None:
        zero = calculate_ratio_kpi(4, 0)
        missing = calculate_ratio_kpi(None, None, ["units_sold", "available_units"])
        self.assertEqual(zero["status"], "not_calculable")
        self.assertIsNone(zero["value"])
        self.assertIn("non_zero_denominator", zero["missing_fields"])
        self.assertEqual(missing["status"], "not_calculable")
        self.assertIn("available_units", missing["missing_fields"])
        self.assertEqual(calculate_ratio_kpi(5, 10)["value"], 50.0)

    def test_product_lookup_keeps_synthetic_and_observed_catalog_data_separate(self) -> None:
        synthetic = get_product("LW-2601")
        observed = get_product("0999991001")
        self.assertEqual(synthetic["data_status"], "synthetic")
        self.assertEqual(observed["data_status"], "observed")
        self.assertEqual(observed["product"]["article_id"], "0999991001")
        self.assertTrue(observed["product"]["detail_desc"])
        self.assertIn("size guide", " ".join(observed["limitations"]).lower())


class PlanningOperationsApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.previous_db_path = os.environ.get("VOGUE_DB_PATH")
        os.environ["VOGUE_DB_PATH"] = str(Path(cls.temp_dir.name) / "prototype.sqlite3")
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), PrototypeHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        if cls.previous_db_path is None:
            os.environ.pop("VOGUE_DB_PATH", None)
        else:
            os.environ["VOGUE_DB_PATH"] = cls.previous_db_path
        cls.temp_dir.cleanup()

    def get_json(self, path: str) -> dict:
        with urlopen(self.base_url + path, timeout=5) as response:
            self.assertEqual(response.status, 200)
            return json.loads(response.read())

    def test_data_endpoints_return_explicit_status_and_provenance(self) -> None:
        for route, expected in (
            ("/api/planning/line-plans", "synthetic"),
            ("/api/planning/markdown-reviews", "synthetic"),
            ("/api/planning/kpi-definitions", "synthetic"),
            ("/api/planning/campaigns", "synthetic"),
            ("/api/products", "synthetic"),
        ):
            payload = self.get_json(route)
            self.assertEqual(payload["data_status"], expected)
            self.assertTrue(payload["source_id"])
            self.assertTrue(payload["version"])
            self.assertTrue(payload["as_of"])
            self.assertTrue(payload["limitations"])

        status = self.get_json("/api/data-status")
        states = {row["dataset"]: row["data_status"] for row in status["datasets"]}
        self.assertEqual(states["hm_historical_catalog_and_sales"], "observed")
        self.assertEqual(states["approved_targets_and_kpi_measurements"], "not_connected")
        self.assertEqual(states["campaign_outcomes"], "not_connected")

    def test_product_endpoint_returns_actual_catalog_text_without_synthetic_enrichment(self) -> None:
        payload = self.get_json("/api/products/0999991001")
        self.assertEqual(payload["data_status"], "observed")
        self.assertEqual(payload["source_id"], "KAGGLE-HM-ARTICLES")
        self.assertIn("detail_desc", payload["product"])
        self.assertNotIn("material_composition", payload["product"])


if __name__ == "__main__":
    unittest.main()
