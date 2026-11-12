from __future__ import annotations

import unittest
import json
import tempfile
import os
from pathlib import Path
from unittest.mock import patch

from vogue_npp.domain.retrieval import (
    EvidenceRef,
    RetrievalQuery,
    RetrievalResult,
    RetrievalSourcePolicy,
)
from vogue_npp.prototype.server import _build_planning_draft_response
from vogue_npp.sources.synthetic_corpus_retriever import SyntheticCorpusRetriever


_DOCS = [
    {"document_id":"SYN-DOC-TREND-001","evidence_id":"SYN-INPUT-EV-TREND-001","source_id":"SYN-TREND-INPUT-SNAPSHOT","source_type":"supplied_input_evidence","permission_status":"authorized","permitted_uses":["product_planning"],"verified":True,"synthetic":True,"season":"27SS","category_id":"outerwear","title":"trend olive","text":"올리브 트렌드 관찰","locator":"trend/1"},
    {"document_id":"SYN-DOC-BRAND-001","evidence_id":"SYN-EV-BRAND-GUIDE-001","source_id":"SYN-BRAND-GUIDE","source_type":"approved_brand_guideline","permission_status":"authorized","permitted_uses":["product_planning"],"verified":True,"synthetic":True,"season":"27SS","category_id":"outerwear","title":"브랜드 가이드","text":"올리브 색상과 기능성 소재 지침","locator":"guide/1"},
    {"document_id":"SYN-DOC-PRECEDENT-001","evidence_id":"SYN-EV-PRECEDENT-001","source_id":"SYN-APPROVED-PRECEDENTS","source_type":"approved_precedent","permission_status":"authorized","permitted_uses":["product_planning"],"verified":True,"synthetic":True,"season":"27SS","category_id":"outerwear","title":"선행 상품","text":"올리브 경량 아우터 사례","locator":"precedent/1"},
    {"document_id":"SYN-DOC-TAXONOMY-001","evidence_id":"SYN-EV-TAXONOMY-001","source_id":"SYN-PRODUCT-TAXONOMY","source_type":"approved_taxonomy","permission_status":"authorized","permitted_uses":["product_planning"],"verified":True,"synthetic":True,"season":"27SS","category_id":"outerwear","title":"아우터 분류","text":"outerwear taxonomy","locator":"taxonomy/1"},
    {"document_id":"SYN-DOC-UNKNOWN-001","evidence_id":"SYN-EV-UNKNOWN-PERMISSION-001","source_id":"SYN-OTHER","source_type":"approved_precedent","permission_status":"unknown","permitted_uses":["product_planning"],"verified":True,"synthetic":True,"title":"unknown","text":"올리브","locator":"x"},
    {"document_id":"SYN-DOC-DENIED-001","evidence_id":"SYN-EV-DENIED-001","source_id":"SYN-OTHER","source_type":"approved_precedent","permission_status":"denied","permitted_uses":["product_planning"],"verified":True,"synthetic":True,"title":"denied","text":"올리브","locator":"x"},
    {"document_id":"SYN-DOC-OTHER-USE-001","evidence_id":"SYN-EV-OTHER-USE-001","source_id":"SYN-OTHER","source_type":"approved_precedent","permission_status":"authorized","permitted_uses":["other"],"verified":True,"synthetic":True,"title":"other use","text":"올리브","locator":"x"},
]


def corpus_path(test_case):
    if not hasattr(test_case, "_corpus_tmp"):
        test_case._corpus_tmp = tempfile.TemporaryDirectory()
        test_case.addCleanup(test_case._corpus_tmp.cleanup)
        path = Path(test_case._corpus_tmp.name) / "corpus.json"
        path.write_text(json.dumps({"synthetic": True, "index_version": "synthetic-fixture-v1", "documents": _DOCS}, ensure_ascii=False), encoding="utf-8")
        test_case._corpus_path = path
    return test_case._corpus_path


def fixture_and_policy():
    allowed = {
        "evidence_lookup": ("SYN-TREND-INPUT-SNAPSHOT",),
        "planning_reference": ("SYN-BRAND-GUIDE",),
        "precedent": ("SYN-APPROVED-PRECEDENTS",),
        "taxonomy": ("SYN-PRODUCT-TAXONOMY",),
    }
    types = {
        "evidence_lookup": ("supplied_input_evidence",),
        "planning_reference": ("approved_brand_guideline",),
        "precedent": ("approved_precedent",),
        "taxonomy": ("approved_taxonomy",),
    }
    policy = RetrievalSourcePolicy(
        source_ids_by_purpose=allowed,
        source_types_by_purpose=types,
    )
    return policy


class SyntheticPlanningRagFixtureTests(unittest.TestCase):
    def setUp(self):
        self._rag_env = patch.dict(os.environ, {"VOGUE_SYNTHETIC_PLANNING_RAG_ENABLED": "false"})
        self._rag_env.start()
        self.addCleanup(self._rag_env.stop)

    def test_fixture_is_entirely_marked_synthetic_and_has_expected_document_types(self):
        retriever = SyntheticCorpusRetriever(corpus_path(self))
        data = {"synthetic": True, "documents": retriever.documents}
        self.assertTrue(data["synthetic"])
        self.assertTrue(all(item["synthetic"] for item in data["documents"]))
        self.assertEqual(
            {item["source_type"] for item in data["documents"]}
            - {"supplied_input_evidence"},
            {"approved_precedent", "approved_brand_guideline", "approved_taxonomy"},
        )
        self.assertIn("unknown", {item["permission_status"] for item in data["documents"]})
        self.assertIn("denied", {item["permission_status"] for item in data["documents"]})

    def test_adapter_ranks_lexical_matches_and_returns_traceable_content_hash(self):
        retriever = SyntheticCorpusRetriever(corpus_path(self))
        result = retriever.retrieve(RetrievalQuery(
            purpose="precedent", request_id="retriever-test-1", season="27SS",
            category_ids=("outerwear",), attribute_terms=("올리브",),
            allowed_source_ids=("SYN-APPROVED-PRECEDENTS",),
            allowed_source_types=("approved_precedent",), limit=5,
        ))
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.evidence[0].evidence_id, "SYN-EV-PRECEDENT-001")
        self.assertIn("lexical:올리브", result.evidence[0].matched_by)
        self.assertEqual(len(result.evidence[0].content_hash), 64)
        self.assertEqual(result.index_version, "synthetic-fixture-v1")

    def test_adapter_uses_exact_evidence_lookup_and_enforces_every_allowlist(self):
        retriever = SyntheticCorpusRetriever(corpus_path(self))
        base = dict(
            purpose="evidence_lookup", request_id="retriever-test-2",
            evidence_ids=("SYN-INPUT-EV-TREND-001",),
            allowed_source_ids=("SYN-TREND-INPUT-SNAPSHOT",),
            allowed_source_types=("supplied_input_evidence",),
        )
        result = retriever.retrieve(RetrievalQuery(**base))
        self.assertEqual([item.evidence_id for item in result.evidence], ["SYN-INPUT-EV-TREND-001"])
        self.assertEqual(result.evidence[0].matched_by, "exact_evidence_id")
        disallowed = retriever.retrieve(RetrievalQuery(**{
            **base, "allowed_source_ids": ("UNLISTED-SOURCE",),
        }))
        self.assertEqual(disallowed.status, "no_results")

    def test_all_four_retrieval_purposes_apply_source_and_scope_filters(self):
        policy = fixture_and_policy()
        retriever = SyntheticCorpusRetriever(corpus_path(self))
        sales_payload = {
            "request_id": "synthetic-rag-1", "agent_id": "sales-market-agent",
            "status": "partial", "findings": [{"evidence_ids": ["MARKET-SYN-1"]}],
            "limitations": ["synthetic handoff only"],
        }
        input_payloads = {
            "planning_request": {
                "request_id": "synthetic-rag-1", "schema_version": "1.0",
                "season": "27SS", "category": "outerwear",
                "requested_attributes": [{"name": "color", "value": "올리브", "source": "user"}],
            },
            "trend_result": {
                "request_id": "synthetic-rag-1", "schema_version": "1.0",
                "status": "ok", "evidence_ids": ["SYN-INPUT-EV-TREND-001"],
            },
            "inventory_product_result": {
                "request_id": "synthetic-rag-1", "schema_version": "1.0",
                "status": "ok", "products": [],
            },
            "sales_market_result": sales_payload,
        }
        response = _build_planning_draft_response(
            input_payloads,
            knowledge_retriever=retriever,
            retrieval_policy=policy,
        )
        statuses = {item["purpose"]: item["status"] for item in response["planning_knowledge"]["by_purpose"]}
        self.assertEqual(statuses, {
            "evidence_lookup": "ok", "planning_reference": "ok", "precedent": "ok", "taxonomy": "ok",
            "catalog_comparison": "not_configured", "assortment_relation": "not_configured",
        })
        ids_by_purpose = {
            item["purpose"]: {ref["evidence_id"] for ref in item["evidence"]}
            for item in response["planning_knowledge"]["by_purpose"]
        }
        self.assertEqual(ids_by_purpose["evidence_lookup"], {"SYN-INPUT-EV-TREND-001"})
        self.assertEqual(ids_by_purpose["planning_reference"], {"SYN-EV-BRAND-GUIDE-001"})
        self.assertEqual(ids_by_purpose["taxonomy"], {"SYN-EV-TAXONOMY-001"})
        self.assertEqual(ids_by_purpose["precedent"], {"SYN-EV-PRECEDENT-001"})
        denied = {"SYN-EV-UNKNOWN-PERMISSION-001", "SYN-EV-DENIED-001", "SYN-EV-OTHER-USE-001"}
        self.assertFalse(denied.intersection(response["planning_knowledge"]["evidence_ids"]))
        precedent_query = next(query for query in retriever.queries if query.purpose == "precedent")
        self.assertEqual(precedent_query.season, "27SS")
        self.assertEqual(precedent_query.category_ids, ("outerwear",))
        self.assertEqual(precedent_query.allowed_source_ids, ("SYN-APPROVED-PRECEDENTS",))
        self.assertEqual(response["draft"]["planning_references"][0]["evidence_id"], "SYN-EV-BRAND-GUIDE-001")
        self.assertNotIn("SYN-EV-PRECEDENT-001", str(response["draft"]["attributes"]))
        self.assertEqual(response["draft"]["sales_market_result"], sales_payload)
        self.assertEqual(response["input_evidence"]["trend_result"]["payload"], input_payloads["trend_result"])
        self.assertEqual(response["input_evidence"]["inventory_product_result"]["payload"], input_payloads["inventory_product_result"])

    def test_missing_scope_matches_return_no_results_without_claiming_absence(self):
        policy = fixture_and_policy()
        retriever = SyntheticCorpusRetriever(corpus_path(self))
        response = _build_planning_draft_response(
            {
                "request_id": "synthetic-rag-2",
                "planning_request": {
                    "request_id": "synthetic-rag-2", "schema_version": "1.0",
                    "season": "28FW", "category": "footwear",
                },
                "trend_result": {"request_id": "synthetic-rag-2", "schema_version": "1.0", "status": "no_results"},
                "inventory_product_result": {"request_id": "synthetic-rag-2", "schema_version": "1.0", "status": "no_results"},
            },
            knowledge_retriever=retriever,
            retrieval_policy=policy,
        )
        status_map = {item["purpose"]: item["status"] for item in response["planning_knowledge"]["by_purpose"]}
        self.assertEqual(status_map["planning_reference"], "no_results")
        self.assertEqual(status_map["precedent"], "no_results")
        self.assertEqual(status_map["taxonomy"], "no_results")
        self.assertIn("초안", response["draft"]["title"])


if __name__ == "__main__":
    unittest.main()
