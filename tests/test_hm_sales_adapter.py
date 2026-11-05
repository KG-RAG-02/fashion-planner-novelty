from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from vogue_npp.hm_sales_adapter import load_hm_sales_analysis
from vogue_npp.prototype.retrieval import get_evidence


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/processed/hm-personalized-fashion-recommendations"


class HmSalesAdapterTests(unittest.TestCase):
    def test_article_type_total_matches_planning_analysis(self) -> None:
        result = load_hm_sales_analysis(
            request_id="test-request",
            schema_version="internal-1",
            requested_category="Trousers",
            source_category_map={"Trousers": "Trousers"},
            category_mapping_version="test-map-1",
            processed_dir=DATA,
        )
        self.assertEqual(result.result.status, "ok")
        self.assertEqual(sum(item.purchase_rows for item in result.observations), 4_217_017)
        self.assertTrue(all(item.evidence_ids for item in result.observations))

    def test_category_evidence_resolves_with_source_period_and_version(self) -> None:
        from vogue_npp.hm_planning_analysis import analyze

        analysis = analyze(DATA)
        trousers = next(item for item in analysis["product_types"] if item["product_type_name"] == "Trousers")
        evidence = get_evidence(trousers["evidence_id"])
        self.assertEqual(evidence["kind"], "hm_article_level_category_sales")
        self.assertEqual(evidence["record"]["purchase_rows"], 4_217_017)
        self.assertEqual(evidence["source"]["period"]["start"], "2018-09-20")
        self.assertEqual(evidence["analysis_version"], analysis["analysis_version"])

    def test_observation_limit_is_explicitly_partial(self) -> None:
        result = load_hm_sales_analysis(
            request_id="test-request",
            schema_version="internal-1",
            requested_category="Upper",
            source_category_map={"Garment Upper body": "Upper"},
            category_mapping_version="test-map-1",
            processed_dir=DATA,
            observation_limit=1,
        )
        self.assertEqual(len(result.observations), 1)
        self.assertTrue(any("do not represent the full mapped category total" in item for item in result.result.limitations))

    def test_missing_mapping_returns_no_results_without_guessing(self) -> None:
        result = load_hm_sales_analysis(
            request_id="test-request",
            schema_version="internal-1",
            requested_category="Unknown taxonomy",
            source_category_map={},
            category_mapping_version="test-map-1",
            processed_dir=DATA,
        )
        self.assertEqual(result.result.status, "no_results")
        self.assertFalse(result.observations)


if __name__ == "__main__":
    unittest.main()
