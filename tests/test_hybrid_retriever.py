from __future__ import annotations

import unittest
from datetime import date

from vogue_npp.domain.retrieval import EvidenceRef, KGPath, RetrievalQuery, RetrievalResult
from vogue_npp.sources.hybrid_retriever import HybridKnowledgeRetriever


def ref(evidence_id: str, *, source="SRC-A", locator=None, quote=None):
    return EvidenceRef(
        evidence_id=evidence_id,
        source_id=source,
        locator=locator or f"doc#{evidence_id}",
        quote=quote or f"quote {evidence_id}",
        source_date=date(2026, 1, 1),
        access_status="authorized",
        verified=True,
        source_type="approved_brand_guideline",
        source_name="Synthetic source",
        permission_status="authorized",
        permitted_uses=("product_planning",),
        content_hash=f"hash-{evidence_id}",
    )


class StaticRetriever:
    def __init__(self, result: RetrievalResult | Exception):
        self.result = result
        self.queries = []

    def retrieve(self, query):
        self.queries.append(query)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def query():
    return RetrievalQuery(
        purpose="planning_reference",
        request_id="hybrid-1",
        category_ids=("outerwear",),
        attribute_terms=("olive",),
        exact_terms=("outerwear",),
        allowed_source_ids=("SRC-A",),
        allowed_source_types=("approved_brand_guideline",),
        limit=2,
        candidate_limit=8,
    )


class HybridRetrieverTests(unittest.TestCase):
    def test_rrf_merges_unique_results_and_preserves_provenance(self):
        lexical = StaticRetriever(RetrievalResult(
            "ok", evidence=(ref("E1"), ref("E2")), index_version="lex-v1", retrieval_run_id="lex-run",
        ))
        dense = StaticRetriever(RetrievalResult(
            "ok", evidence=(ref("E2"), ref("E3")), index_version="dense-v1", retrieval_run_id="dense-run",
        ))
        result = HybridKnowledgeRetriever(lexical, dense).retrieve(query())
        self.assertEqual(result.status, "ok")
        self.assertEqual([item.evidence_id for item in result.evidence], ["E2", "E1"])
        self.assertEqual(result.evidence[0].matched_by, "rrf:dense+lexical")
        self.assertEqual(result.index_version, "lexical=lex-v1;dense=dense-v1")
        self.assertEqual(lexical.queries[0].limit, 8)
        self.assertEqual(dense.queries[0].limit, 8)
        self.assertEqual(lexical.queries[0].candidate_limit, None)

    def test_single_backend_failure_is_partial_and_discards_its_payload(self):
        lexical = StaticRetriever(RuntimeError("sensitive failure detail"))
        dense = StaticRetriever(RetrievalResult("ok", evidence=(ref("E1"),)))
        result = HybridKnowledgeRetriever(lexical, dense).retrieve(query())
        self.assertEqual(result.status, "partial")
        self.assertEqual([item.evidence_id for item in result.evidence], ["E1"])
        self.assertNotIn("sensitive failure detail", str(result.limitations))

    def test_identity_conflict_is_removed_and_marks_partial(self):
        lexical = StaticRetriever(RetrievalResult("ok", evidence=(ref("E1", locator="doc#one"),)))
        dense = StaticRetriever(RetrievalResult("ok", evidence=(ref("E1", locator="doc#other"),)))
        result = HybridKnowledgeRetriever(lexical, dense).retrieve(query())
        self.assertEqual(result.status, "partial")
        self.assertFalse(result.evidence)
        self.assertTrue(any("식별 정보" in item for item in result.limitations))

    def test_kg_paths_survive_only_when_their_evidence_survives(self):
        valid = KGPath(("outerwear", "anorak"), ("includes",), "tax-v1", ("E1",))
        orphan = KGPath(("outerwear", "shell"), ("includes",), "tax-v1", ("E-UNKNOWN",))
        lexical = StaticRetriever(RetrievalResult("ok", evidence=(ref("E1"),), kg_paths=(valid, orphan)))
        dense = StaticRetriever(RetrievalResult("no_results"))
        result = HybridKnowledgeRetriever(lexical, dense).retrieve(query())
        self.assertEqual(result.status, "partial")
        self.assertEqual(result.kg_paths, (valid,))

    def test_two_empty_routes_return_no_results(self):
        hybrid = HybridKnowledgeRetriever(
            StaticRetriever(RetrievalResult("no_results")),
            StaticRetriever(RetrievalResult("no_results")),
        )
        self.assertEqual(hybrid.retrieve(query()).status, "no_results")


if __name__ == "__main__":
    unittest.main()
