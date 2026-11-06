from __future__ import annotations

import unittest
from datetime import date

from vogue_npp.domain.candidates import (
    Candidate, CandidateAttribute, CandidateScore, ScoreWeights,
    generate_existing_candidates, generate_new_candidate, score_candidate,
    select_top_candidates,
)
from vogue_npp.domain.retrieval import EvidenceRef, SalesInventoryResult, SalesMetric
from vogue_npp.domain.trend_batch import TrendBatch
from vogue_npp.domain.trend_evaluator import (
    Category, EvidenceAssessment, InMemoryCategoryTaxonomy, TrendFitWeights, evaluate_trend_batch,
)


class VerifiedResolver:
    def assess(self, document):
        return EvidenceAssessment(document.document_id, "verified", True, date(2026, 9, 1), independence_group="src-1")


class CandidateTests(unittest.TestCase):
    def _trend(self):
        batch = TrendBatch.from_mapping({"schema_version":"1.0", "batch_id":"B1", "trends":[{
            "trend_id":"T1", "name":"Burgundy", "description":"Burgundy color fashion trend",
            "evidence":[{"document_id":"D1", "title":"Source", "excerpt":"Burgundy color fashion trend", "published_at":"2026-09-01"}]}]})
        taxonomy = InMemoryCategoryTaxonomy((Category("outer", "Outerwear", relevant_attribute_types=("color",)),), "tax1")
        return evaluate_trend_batch(batch, taxonomy, VerifiedResolver(), TrendFitWeights(.7,.3,"test-v1"))[0]

    def test_new_candidate_requires_fit_and_verified_evidence(self):
        trend = self._trend()
        self.assertEqual(trend.category_evaluations[0].status, "ok")
        ref = EvidenceRef("D1", "SRC1", "p1", "Burgundy color", date(2026, 9, 1), "permitted", True)
        result = generate_new_candidate(trend, "outer", target_season="2027FW", evidence_refs=(ref,))
        self.assertEqual(result.status, "ok")
        candidate = result.candidates[0]
        self.assertEqual(candidate.attributes[0].evidence_ids, ("D1",))
        self.assertTrue(candidate.unknowns)
        self.assertEqual(generate_new_candidate(trend, "outer", target_season=None).status, "insufficient_evidence")

    def test_existing_candidate_preserves_attributes_and_query_status(self):
        trend = self._trend()
        data = SalesInventoryResult("ok", (SalesMetric("P1:S1", 4, 20, "USD", date(2026,1,1), date(2026,1,31), "web", "SQL1"),))
        result = generate_existing_candidates(trend, "outer", ({"product_id":"P1", "category_id":"outer", "name":"Jacket", "attributes":{"color":"Black"}, "attribute_evidence":{"color":["CAT1"]}},), data)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.candidates[0].attributes[0].evidence_ids, ("CAT1",))
        self.assertEqual(result.candidates[0].sql_metric_refs, ("SQL1",))
        self.assertEqual(generate_existing_candidates(trend, "outer", (), SalesInventoryResult("error")).status, "error")

    def test_scorer_abstains_without_config_then_scores_with_config(self):
        candidate = Candidate("c1", "new_product", "Burgundy outer", "outer", None, ("T1",), None,
            (CandidateAttribute("color", "Burgundy", "evidence_observation", ("D1",)),),
            (EvidenceRef("D1", "SRC1", None, None, None, "permitted", True),), (), (), (), (), (), ())
        abstain = score_candidate(candidate, trend_fit=80, sales_observation=60, product_fit=70, inventory_signal=50, evidence_confidence=90)
        self.assertEqual(abstain.status, "unconfigured")
        weights = ScoreWeights(.25,.25,.2,.15,.15,"reviewed-v1")
        scored = score_candidate(candidate, trend_fit=80, sales_observation=60, product_fit=70, inventory_signal=50, evidence_confidence=90, weights=weights)
        self.assertEqual(scored.status, "scored")
        self.assertAlmostEqual(scored.score, 70.0)
        self.assertEqual(scored.coverage, 1.0)
        unverified = Candidate(candidate.candidate_id, candidate.candidate_type, candidate.title, candidate.category_id,
            candidate.target_season, candidate.responds_to_trend_ids, candidate.product_id, candidate.attributes,
            (EvidenceRef("D1", "SRC1", None, None, None, "unverified", False),), candidate.sql_metric_refs,
            candidate.kg_paths, candidate.assumptions, candidate.unknowns, candidate.risks, candidate.validation_questions)
        rejected = score_candidate(unverified, trend_fit=80, sales_observation=60, product_fit=70,
            inventory_signal=50, evidence_confidence=90, weights=weights)
        self.assertEqual(rejected.status, "insufficient_data")

    def test_selector_deduplicates_and_caps_category_without_filling_invalid_slots(self):
        def candidate(cid, category, title):
            return Candidate(cid, "existing_improvement", title, category, None, ("T1",), cid,
                (CandidateAttribute("color","Red","evidence_observation",("E",)),),
                (EvidenceRef("E","S",None,None,None,"ok",True),), (), (), (), (), (), ())
        rows = [candidate("1","A","First"), candidate("2","A","Duplicate"), candidate("3","B","Third"), candidate("4","C","Fourth")]
        scores = {row.candidate_id: CandidateScore(row.candidate_id,"scored",90-i,{"trend_fit":90-i},1,"w",("E",)) for i,row in enumerate(rows)}
        selection = select_top_candidates(rows, scores, limit=5, max_per_category=1, max_per_type=None, max_per_trend=None)
        self.assertEqual(len(selection.selected), 3)
        self.assertIn("카테고리 다양성", selection.excluded["2"])
        repeated_id = select_top_candidates((rows[0], rows[0]), scores, limit=5, max_per_category=5)
        self.assertEqual(len(repeated_id.selected), 1)
        self.assertNotIn(rows[0].candidate_id, repeated_id.excluded)


if __name__ == "__main__":
    unittest.main()
