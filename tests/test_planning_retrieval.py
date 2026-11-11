from __future__ import annotations

import unittest
import json
from dataclasses import replace
from datetime import date

from vogue_npp.domain.context import (
    AgentResult, AttributeSignal, InventoryProduct, InventoryProductResult,
    PlanningInputs, PlanningRequest, TrendCandidate, TrendResult, build_planning_context,
)
from vogue_npp.domain.retrieval import (
    EvidenceRef, RetrievalQuery, RetrievalResult, RetrievalSourcePolicy,
)
from vogue_npp.prototype.server import _build_planning_draft_response
from vogue_npp.domain.generator import RuleBasedConceptGenerator
from vogue_npp.workflows.image_generation import build_image_generation_request
from vogue_npp.workflows.planning_retrieval import retrieve_planning_knowledge


REQUEST_ID = "rag-request-1"


def make_context():
    request = PlanningRequest(
        AgentResult("request-agent", REQUEST_ID, "internal-0", "ok", ("request-E1",)),
        original_query="Do not send this full query to a broad search.", season="27SS",
        market=("KR",), channel=("online",), category="outerwear",
        requested_attributes=(AttributeSignal("color", "olive", "user_requested"),),
    )
    trend = TrendResult(
        AgentResult("trend-agent", REQUEST_ID, "internal-0", "ok", ("trend-E1",)),
        (TrendCandidate("utility", "candidate", season="27SS", category="outerwear",
                        attributes=(AttributeSignal("silhouette", "relaxed", "evidence_observation", ("trend-E1",)),),
                        evidence_ids=("trend-E1",)),),
    )
    inventory = InventoryProductResult(
        AgentResult("stock-agent", REQUEST_ID, "internal-0", "ok", ("stock-E1",)),
        (InventoryProduct("ST-1", (), category="outerwear", evidence_ids=("stock-E1",)),),
    )
    sales = {"request_id": REQUEST_ID, "agent_id": "sales-market-agent", "status": "ok",
             "evidence": [{"evidence_id": "market-E1"}], "findings": []}
    return build_planning_context(PlanningInputs(request, trend, inventory, sales))


class FakeRetriever:
    def __init__(self, result=None, *, fail_purposes=()):
        self.result = result or RetrievalResult("no_results")
        self.fail_purposes = set(fail_purposes)
        self.queries = []

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        self.queries.append(query)
        if query.purpose in self.fail_purposes:
            raise RuntimeError("fixture failure")
        return self.result


def policy():
    purposes = ("evidence_lookup", "planning_reference", "precedent", "taxonomy")
    return RetrievalSourcePolicy(
        source_ids_by_purpose={name: ("SRC-shared",) for name in purposes},
        source_types_by_purpose={name: ("approved_planning",) for name in purposes},
    )


def ref(evidence_id, source_id="SRC-shared", *, permission="authorized", uses=("product_planning",), verified=True):
    return EvidenceRef(
        evidence_id, source_id, "guide#section-2", "Approved fit guidance.", date(2026, 1, 1),
        "verified" if verified else "unverified", verified,
        source_type="approved_planning", source_name="Brand guide",
        permission_status=permission, permitted_uses=uses,
    )


class PlanningRetrievalTests(unittest.TestCase):
    def test_unconfigured_routes_are_distinct_and_do_not_call_adapter(self):
        retriever = FakeRetriever()
        result = retrieve_planning_knowledge(make_context(), retriever=retriever)
        self.assertFalse(retriever.queries)
        self.assertEqual({item.status for item in result.by_purpose}, {"not_configured"})

    def test_queries_are_scoped_and_market_evidence_is_never_resolved(self):
        retriever = FakeRetriever()
        result = retrieve_planning_knowledge(make_context(), retriever=retriever, policy=policy())
        self.assertEqual(len(retriever.queries), 4)
        lookup = next(item for item in retriever.queries if item.purpose == "evidence_lookup")
        self.assertEqual(lookup.request_id, REQUEST_ID)
        self.assertEqual(set(lookup.evidence_ids), {"request-E1", "trend-E1", "stock-E1"})
        self.assertEqual(lookup.query_plan_version, "planning-query-plan-v2")
        self.assertEqual(lookup.candidate_limit, 30)
        self.assertIn("outerwear", lookup.exact_terms)
        self.assertNotIn("market-E1", lookup.evidence_ids)
        semantic = next(item for item in retriever.queries if item.purpose == "planning_reference")
        self.assertEqual(semantic.allowed_source_ids, ("SRC-shared",))
        self.assertNotIn("Do not send this full query", semantic.attribute_terms)
        self.assertEqual({item.status for item in result.by_purpose}, {"no_results", "not_configured"})

    def test_only_verified_authorized_allowlisted_references_are_exposed(self):
        retriever = FakeRetriever(RetrievalResult("ok", evidence=(
            ref("trend-E1"),
            ref("denied-E1", permission="denied"),
            ref("wrong-source-E1", source_id="OTHER"),
            ref("not-for-planning-E1", uses=("training",)),
            ref("unverified-E1", verified=False),
        )))
        result = retrieve_planning_knowledge(make_context(), retriever=retriever, policy=policy())
        for purpose_result in result.by_purpose:
            if purpose_result.purpose in {"catalog_comparison", "assortment_relation"}:
                self.assertEqual(purpose_result.status, "not_configured")
                continue
            self.assertEqual([item.evidence_id for item in purpose_result.evidence], ["trend-E1"])
            self.assertEqual(purpose_result.status, "partial")
            self.assertTrue(purpose_result.limitations)

    def test_provider_error_is_local_to_route(self):
        retriever = FakeRetriever(fail_purposes={"precedent"})
        result = retrieve_planning_knowledge(make_context(), retriever=retriever, policy=policy())
        statuses = {item.purpose: item.status for item in result.by_purpose}
        self.assertEqual(statuses["precedent"], "error")
        self.assertEqual(statuses["taxonomy"], "no_results")

    def test_error_payload_cannot_leak_embedded_hits(self):
        retriever = FakeRetriever(RetrievalResult("error", evidence=(ref("trend-E1"),)))
        result = retrieve_planning_knowledge(make_context(), retriever=retriever, policy=policy())
        self.assertTrue(all(not item.evidence for item in result.by_purpose))
        self.assertEqual(sum(item.status == "error" for item in result.by_purpose), 4)
        self.assertEqual(sum(item.status == "not_configured" for item in result.by_purpose), 2)

    def test_retrieved_document_text_is_not_sent_to_product_image_prompt(self):
        context = make_context()
        knowledge = retrieve_planning_knowledge(
            context,
            retriever=FakeRetriever(RetrievalResult("ok", evidence=(ref("RAG-E1"),))),
            policy=policy(),
        )
        enriched = replace(context, planning_knowledge=knowledge)
        draft, _ = RuleBasedConceptGenerator().generate(enriched)
        request = build_image_generation_request(enriched, draft)
        self.assertNotIn("Approved fit guidance.", request.prompt)
        self.assertNotIn("RAG-E1", request.evidence_ids)
        self.assertTrue(any(item.evidence_id == "RAG-E1" for item in request.excluded_evidence))
        self.assertEqual(draft.planning_references[0]["evidence_id"], "RAG-E1")
        self.assertNotIn("Approved fit guidance.", [str(item.value) for item in draft.attributes])

    def test_api_continues_draft_and_preserves_project07_payload(self):
        market_payload = make_context().sales_market_result
        response = _build_planning_draft_response(
            {
                "request_id": "api-rag-1",
                "planning_request": {"request_id": "api-rag-1", "season": "27SS", "category": "outerwear"},
                "trend_result": {"request_id": "api-rag-1", "status": "ok", "evidence_ids": ["trend-E1"]},
                "inventory_product_result": {"request_id": "api-rag-1", "status": "ok", "evidence_ids": ["stock-E1"]},
                "sales_market_result": {**market_payload, "request_id": "api-rag-1"},
            },
            knowledge_retriever=FakeRetriever(fail_purposes={"planning_reference"}),
            retrieval_policy=policy(),
        )
        self.assertIn("draft", response)
        self.assertEqual(response["draft"]["sales_market_result"]["evidence"], market_payload["evidence"])
        statuses = {item["purpose"]: item["status"] for item in response["planning_knowledge"]["by_purpose"]}
        self.assertEqual(statuses["planning_reference"], "error")
        self.assertEqual(response["input_statuses"]["sales_market_result"], "ok")

    def test_api_serializes_authorized_reference_dates_and_evidence(self):
        response = _build_planning_draft_response(
            {
                "request_id": "api-rag-2",
                "planning_request": {"request_id": "api-rag-2", "season": "27SS", "category": "outerwear"},
                "trend_result": {"request_id": "api-rag-2", "status": "ok", "evidence_ids": ["trend-E1"]},
                "inventory_product_result": {"request_id": "api-rag-2", "status": "ok"},
            },
            knowledge_retriever=FakeRetriever(RetrievalResult("ok", evidence=(ref("trend-E1"),))),
            retrieval_policy=policy(),
        )
        encoded = json.dumps(response)
        self.assertIn("2026-01-01", encoded)
        self.assertIn("trend-E1", response["planning_knowledge"]["evidence_ids"])
        self.assertEqual(response["draft"]["planning_references"][0]["permission_status"], "authorized")
        self.assertEqual(
            response["planning_knowledge"]["by_purpose"][0]["query_plan_version"],
            "planning-query-plan-v2",
        )


if __name__ == "__main__":
    unittest.main()
