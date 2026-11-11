from __future__ import annotations

import unittest
import json
from unittest.mock import patch

from vogue_npp.domain.retrieval import RetrievalQuery
from vogue_npp.prototype.server import _build_planning_draft_response
from vogue_npp.sources.synthetic_workbench_retriever import SyntheticWorkbenchRetriever


class SyntheticWorkbenchRetrieverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.retriever = SyntheticWorkbenchRetriever()

    def query(self, **kwargs):
        values = {
            "request_id": "retrieval-test-1",
            "purpose": "catalog_comparison",
            "season": "27SS",
            "category_ids": ("outerwear",),
            "product_roles": ("upper_body",),
            "allowed_source_types": ("catalog_record", "product_specification"),
            "allow_synthetic": True,
            "dataset_id": self.retriever.dataset_id,
            "limit": 20,
        }
        values.update(kwargs)
        return RetrievalQuery(**values)

    def test_explicit_dataset_and_synthetic_flag_are_required(self):
        missing_flag = self.retriever.retrieve(self.query(allow_synthetic=False))
        wrong_dataset = self.retriever.retrieve(self.query(dataset_id="SYNTHETIC-WRONG"))
        self.assertEqual(missing_flag.status, "no_results")
        self.assertEqual(wrong_dataset.status, "no_results")
        self.assertFalse(missing_flag.evidence)

    def test_catalog_attribute_hit_returns_linked_attribute_evidence_and_metadata(self):
        result = self.retriever.retrieve(self.query(attribute_terms=("sage",), exact_terms=("sage",)))
        self.assertEqual(result.status, "ok")
        color_ref = next(item for item in result.evidence if item.evidence_id == "SYN-EV-ATTR-001-COLOR")
        self.assertEqual(color_ref.permission_status, "synthetic_only")
        self.assertTrue(color_ref.is_synthetic)
        self.assertEqual(color_ref.dataset_id, self.retriever.dataset_id)
        self.assertEqual(color_ref.locator, "catalog/attributes/color")
        self.assertEqual(len(color_ref.content_hash), 64)
        self.assertIn("합성", result.limitations[0])
        self.assertEqual({item.evidence_id for item in result.evidence}, {"SYN-EV-ATTR-001-COLOR"})

    def test_alias_scope_and_lifecycle_permission_evidence_filters_apply(self):
        result = self.retriever.retrieve(self.query(
            category_ids=("아우터",), attribute_terms=("가상",),
            exact_terms=("가상",), allowed_source_types=("guideline",),
            purpose="planning_reference",
        ))
        self.assertEqual(result.status, "ok")
        ids = {item.evidence_id for item in result.evidence}
        self.assertIn("SYN-EV-GUIDE-001", ids)
        self.assertNotIn("SYN-EV-GUIDE-DRAFT-001", ids)
        self.assertNotIn("SYN-EV-GUIDE-EXPIRED-001", ids)
        self.assertTrue(all(item.permission_status == "synthetic_only" for item in result.evidence))

    def test_precedent_and_assortment_have_separate_purposes(self):
        precedent = self.retriever.retrieve(self.query(
            purpose="precedent", allowed_source_types=("precedent",),
            attribute_terms=("통기성",), exact_terms=("outerwear",),
        ))
        assortment = self.retriever.retrieve(self.query(
            purpose="assortment_relation", allowed_source_types=("assortment_relation",),
            attribute_terms=("코디",), exact_terms=("outerwear",),
        ))
        self.assertIn("SYN-EV-PRECEDENT-001", {item.evidence_id for item in precedent.evidence})
        assortment_ids = {item.evidence_id for item in assortment.evidence}
        self.assertIn("SYN-EV-ASSORTMENT-001", assortment_ids)
        self.assertTrue(any(item_id.startswith("SYN-EV-ASSORTMENT-MATRIX-") for item_id in assortment_ids))

    def test_exact_evidence_lookup_never_broadens_to_other_ids(self):
        result = self.retriever.retrieve(self.query(
            purpose="evidence_lookup", evidence_ids=("SYN-EV-ATTR-001-COLOR",),
            allowed_source_types=("catalog_record",), attribute_terms=(), exact_terms=(),
        ))
        self.assertEqual([item.evidence_id for item in result.evidence], ["SYN-EV-ATTR-001-COLOR"])

    def test_api_uses_workbench_only_when_explicitly_enabled_and_marks_result(self):
        payload = {
            "request_id": "synthetic-api-test",
            "planning_request": {
                "request_id": "synthetic-api-test", "schema_version": "1.0", "status": "ok",
                "season": "27SS", "category": "outerwear", "product_role": "upper_body",
                "requested_attributes": [{"name": "color", "value": "sage", "source": "user"}],
            },
            "trend_result": {"request_id": "synthetic-api-test", "schema_version": "1.0", "status": "no_results"},
            "inventory_product_result": {"request_id": "synthetic-api-test", "schema_version": "1.0", "status": "no_results"},
        }
        with patch.dict("os.environ", {"VOGUE_SYNTHETIC_PLANNING_RAG_ENABLED": "false"}, clear=True):
            disabled = _build_planning_draft_response(payload)
        self.assertFalse(disabled["planning_knowledge"]["synthetic"])
        with patch.dict("os.environ", {
            "VOGUE_SYNTHETIC_PLANNING_RAG_ENABLED": "true",
            "VOGUE_SYNTHETIC_PLANNING_RAG_SOURCE": "local",
        }, clear=True):
            enabled = _build_planning_draft_response(payload)
        self.assertTrue(enabled["planning_knowledge"]["synthetic"])
        self.assertEqual(enabled["planning_knowledge"]["synthetic_dataset_ids"], [self.retriever.dataset_id])
        self.assertTrue(all(item["is_synthetic"] for item in enabled["draft"]["planning_references"]))
        self.assertTrue(all(item["permission_status"] == "synthetic_only" for item in enabled["draft"]["planning_references"]))
        self.assertTrue(any(item["claim_type"] == "synthetic_observation" for item in enabled["planning_analysis"]["observations"]))
        self.assertTrue(all(item["evidence_ids"] for item in enabled["planning_analysis"]["observations"]))
        catalog_trace = next(item["query_trace"] for item in enabled["planning_knowledge"]["by_purpose"]
                             if item["purpose"] == "catalog_comparison")
        self.assertTrue(catalog_trace["allow_synthetic"])
        self.assertEqual(catalog_trace["dataset_id"], self.retriever.dataset_id)

    def test_r2_unavailable_keeps_draft_and_reports_source_error(self):
        from unittest.mock import patch
        from vogue_npp.prototype.server import _build_planning_draft_response

        payload = {
            "request_id": "r2-error-draft",
            "planning_request": {"request_id": "r2-error-draft", "schema_version": "1.0", "status": "ok", "season": "27SS", "category": "outerwear"},
            "trend_result": {"request_id": "r2-error-draft", "schema_version": "1.0", "status": "no_results"},
            "inventory_product_result": {"request_id": "r2-error-draft", "schema_version": "1.0", "status": "no_results"},
        }
        with patch.dict("os.environ", {
            "VOGUE_SYNTHETIC_PLANNING_RAG_ENABLED": "true",
            "VOGUE_SYNTHETIC_PLANNING_RAG_SOURCE": "r2",
        }, clear=True), patch(
            "vogue_npp.sources.r2_synthetic_workbench.R2SyntheticWorkbenchRetriever",
            side_effect=RuntimeError("secret-like provider detail"),
        ):
            response = _build_planning_draft_response(payload)
        self.assertEqual(response["planning_knowledge_source"]["status"], "unavailable")
        self.assertEqual(response["planning_knowledge_source"]["source"], "r2")
        self.assertTrue(response["draft"])
        self.assertNotIn("secret-like provider detail", json.dumps(response, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
