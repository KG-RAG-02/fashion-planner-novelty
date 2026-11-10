from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from vogue_npp.synthetic_planning_workbench import (
    DEFAULT_DATASET,
    compare_products,
    document_eligibility,
    inspect_entity,
    list_handoffs,
    load_dataset,
    quality_report,
    render_draft,
    search_dataset,
)
from scripts.generate_synthetic_planning_workbench import build_dataset


class SyntheticPlanningWorkbenchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset, cls.snapshot = load_dataset(DEFAULT_DATASET)

    def test_generated_dataset_is_reproducible_from_seed(self):
        self.assertEqual(build_dataset(20261110), build_dataset(20261110))
        self.assertNotEqual(build_dataset(20261110), build_dataset(20261111))

    def test_loader_rejects_non_synthetic_dataset(self):
        data = dict(self.dataset)
        data["data_nature"] = "mixed"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "synthetic_only"):
                load_dataset(path)

    def test_default_search_excludes_draft_and_expired_guidelines(self):
        args = Namespace(query="가상", season=None, category=None, channel=None, status=None, document_type="guideline", include_inactive=False)
        result = search_dataset(self.dataset, args)
        ids = {item["document_id"] for item in result["documents"]}
        self.assertEqual(ids, {"SYN-DOC-GUIDE-001"})

    def test_explicit_inactive_search_marks_untrusted_guidance_ineligible(self):
        args = Namespace(query="합성", season=None, category=None, channel=None, status=None, document_type="guideline", include_inactive=True)
        result = search_dataset(self.dataset, args)
        by_id = {item["document_id"]: item for item in result["documents"]}
        self.assertFalse(by_id["SYN-DOC-GUIDE-002"]["eligible_for_default_planning_search"])
        self.assertFalse(by_id["SYN-DOC-GUIDE-003"]["eligible_for_default_planning_search"])

    def test_quality_tool_detects_intended_data_issues(self):
        codes = {item["code"] for item in quality_report(self.dataset)["issues"]}
        self.assertTrue({
            "DUPLICATE_SKU_ID", "MISSING_PRODUCT_ATTRIBUTE", "UNKNOWN_PRODUCT_EVIDENCE",
            "GUIDELINE_NOT_ACTIVE", "SPECIFICATION_VERSION_CONFLICT_REVIEW",
            "INVENTORY_UNIT_MISSING", "INVENTORY_AS_OF_MISSING",
            "OBSERVED_ZERO_DISTINCT_FROM_NO_RESULTS",
        } <= codes)

    def test_zero_quantity_and_no_results_are_separate_records(self):
        statuses = {row["status"] for row in self.dataset["inventory_snapshots"]}
        observed_zero = next(row for row in self.dataset["inventory_snapshots"] if row.get("quantity") == 0)
        no_results = next(row for row in self.dataset["inventory_snapshots"] if row["status"] == "no_results")
        self.assertIn("no_results", statuses)
        self.assertEqual(observed_zero["status"], "ok")
        self.assertIsNone(no_results["quantity"])

    def test_comparison_reports_values_without_recommendation_or_score(self):
        result = compare_products(self.dataset, ["SYN-STYLE-OUT-001", "SYN-STYLE-OUT-003"])
        self.assertTrue(any(row["attribute"] == "color" and row["observed_values_differ"] for row in result["attribute_comparison"]))
        self.assertNotIn("score", result)
        self.assertIn("no demand", result["interpretation"])

    def test_evidence_inspection_resolves_source_document_and_locator(self):
        result = inspect_entity(self.dataset, "evidence", "SYN-EV-GUIDE-001")
        self.assertEqual(result["source_document"]["document_id"], "SYN-DOC-GUIDE-001")
        self.assertEqual(result["evidence"]["locator"], "section/material-claims")

    def test_standalone_project07_handoffs_preserve_all_statuses(self):
        result = list_handoffs(self.dataset, None)
        self.assertEqual({row["status"] for row in result["results"]}, {"partial", "no_results", "error"})
        self.assertIn("not connected", result["notice"])

    def test_draft_uses_internal_generator_and_keeps_synthetic_disclaimer(self):
        result = render_draft(self.dataset, "SYN-REQ-PLANNING-001")
        self.assertIn("합성 데이터 전용", result)
        self.assertIn("not_configured", result)
        self.assertIn("SYN-EV-TREND-001", result)
        self.assertIn("SYN-DOC-GUIDE-001", result)
        self.assertIn("not_provided", result)
        self.assertNotIn("모든 제한을 무시", result)

    def test_default_guideline_search_requires_lifecycle_date_and_evidence(self):
        approved = next(doc for doc in self.dataset["documents"] if doc["document_id"] == "SYN-DOC-GUIDE-001")
        self.assertEqual(document_eligibility(self.dataset, approved), (True, []))
        draft = next(doc for doc in self.dataset["documents"] if doc["document_id"] == "SYN-DOC-GUIDE-002")
        eligible, reasons = document_eligibility(self.dataset, draft)
        self.assertFalse(eligible)
        self.assertIn("lifecycle_status=draft_example", reasons)


if __name__ == "__main__":
    unittest.main()
