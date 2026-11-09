from __future__ import annotations

import unittest
from pathlib import Path

from vogue_npp.domain.retrieval import (
    EvidenceRef,
    RetrievalQuery,
    RetrievalResult,
    RetrievalSourcePolicy,
)
from vogue_npp.prototype.server import _build_planning_draft_response
from vogue_npp.sources.synthetic_corpus_retriever import SyntheticCorpusRetriever


FIXTURE_PATH = Path(__file__).parents[1] / "data" / "fixtures" / "planning_rag" / "synthetic_corpus.json"


def fixture_and_policy():
    retriever = SyntheticCorpusRetriever(FIXTURE_PATH)
    data = {"synthetic": True, "documents": retriever.documents}
    assert data["synthetic"] is True
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
    return data, policy


class SyntheticPlanningRagFixtureTests(unittest.TestCase):
    def test_fixture_is_entirely_marked_synthetic_and_has_expected_document_types(self):
        data, _ = fixture_and_policy()
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
        retriever = SyntheticCorpusRetriever(FIXTURE_PATH)
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
        retriever = SyntheticCorpusRetriever(FIXTURE_PATH)
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
        data, policy = fixture_and_policy()
        retriever = SyntheticCorpusRetriever(FIXTURE_PATH)
        sales_payload = {
            "request_id": "synthetic-rag-1", "agent_id": "market-research-agent",
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
        data, policy = fixture_and_policy()
        retriever = SyntheticCorpusRetriever(FIXTURE_PATH)
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
