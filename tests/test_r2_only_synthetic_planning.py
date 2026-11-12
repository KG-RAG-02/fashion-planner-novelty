from __future__ import annotations

import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vogue_npp.domain.retrieval import RetrievalQuery
from vogue_npp.prototype.server import _configure_synthetic_retrieval, _synthetic_planning_rag_enabled
from vogue_npp.synthetic_planning_workbench import document_eligibility
from scripts.generate_synthetic_planning_workbench import build_dataset
from scripts.publish_synthetic_planning_rag_to_r2 import merged_corpus_records

ROOT = Path(__file__).resolve().parents[1]


class R2OnlyPlanningTests(unittest.TestCase):
    def test_rag_is_enabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(_synthetic_planning_rag_enabled())

    def test_runtime_rejects_local_fixture_source(self):
        with patch.dict(os.environ, {
            "VOGUE_SYNTHETIC_PLANNING_RAG_ENABLED": "true",
            "VOGUE_SYNTHETIC_PLANNING_RAG_SOURCE": "local",
        }, clear=True):
            retriever, policy, metadata = _configure_synthetic_retrieval()
        self.assertEqual(metadata["status"], "unavailable")
        self.assertEqual(metadata["source"], "local")
        query = RetrievalQuery(purpose="planning_reference", request_id="source-test",
                               allowed_source_types=("guideline",))
        self.assertEqual(retriever.retrieve(query).status, "error")

    def test_local_corpus_is_namespaced_and_mapped_to_synthetic_workbench_contract(self):
        dataset = build_dataset(20261110)
        corpus = {"synthetic": True, "documents": [{
            "document_id": "SYN-BRAND-GUIDE", "evidence_id": "SYN-EV-BRAND-GUIDE-001",
            "source_id": "SYN-BRAND-GUIDE", "source_type": "approved_brand_guideline",
            "title": "브랜드 가이드", "text": "합성 테스트 가이드", "locator": "guide/1",
            "permission_status": "authorized", "permitted_uses": ["product_planning"], "verified": True,
            "published_at": "2026-01-01", "season": "27SS", "category_id": "outerwear",
        }]}
        with tempfile.TemporaryDirectory() as tmp:
            corpus_path = Path(tmp) / "corpus.json"
            corpus_path.write_text(json.dumps(corpus), encoding="utf-8")
            docs, evidence = merged_corpus_records(dataset, corpus_path)
        self.assertEqual(len(docs), 1)
        self.assertEqual(len(evidence), 1)
        guide = next(item for item in docs if item["document_type"] == "guideline")
        guide_evidence = next(item for item in evidence if item["evidence_id"] == guide["evidence_ids"][0])
        self.assertTrue(guide["document_id"].startswith("SYN-CORPUS-"))
        self.assertEqual(guide["permission_status"], "synthetic_only")
        self.assertEqual(guide["data_nature"], "synthetic_test")
        self.assertIn(guide_evidence["evidence_id"], {item["evidence_id"] for item in evidence})
        self.assertTrue(document_eligibility({**dataset, "evidence": [*dataset["evidence"], *evidence]}, guide)[0])


if __name__ == "__main__":
    unittest.main()
