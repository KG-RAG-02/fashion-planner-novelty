from __future__ import annotations

import unittest
from datetime import date

from vogue_npp.domain.candidates import (
    Candidate, CandidateAttribute, CandidateScore, ScoreWeights,
    generate_existing_candidates, generate_new_candidate, score_candidate,
    select_top_candidates,
)
from vogue_npp.domain.retrieval import EvidenceRef
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
        taxonomy = InMemoryCategoryTaxonomy((Category(
            "outer", "Outerwear", relevant_attribute_types=("color",),
            attribute_value_affinities=(("color:burgundy", 1.0),),
        ),), "tax1")
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

    def test_existing_candidate_preserves_attributes_without_sales_analysis(self):
        trend = self._trend()
        result = generate_existing_candidates(trend, "outer", ({
            "product_id":"P1", "category_id":"outer", "name":"Jacket",
            "attributes":{"color":"Black"}, "attribute_evidence":{"color":["CAT1"]},
        },))
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.candidates[0].attributes[0].evidence_ids, ("CAT1",))
        self.assertEqual(result.candidates[0].source_record_refs, ())
        self.assertEqual(generate_existing_candidates(trend, "outer", ()).status, "no_results")

    def test_scorer_abstains_without_config_then_scores_with_config(self):
        candidate = Candidate("c1", "new_product", "Burgundy outer", "outer", None, ("T1",), None,
            (CandidateAttribute("color", "Burgundy", "evidence_observation", ("D1",)),),
            (EvidenceRef("D1", "SRC1", None, None, None, "permitted", True),), (), (), (), (), (), ())
        abstain = score_candidate(candidate, trend_fit=80, product_fit=70, inventory_signal=50, evidence_confidence=90)
        self.assertEqual(abstain.status, "unconfigured")
        weights = ScoreWeights(.25,.25,.25,.25,"reviewed-v1")
        scored = score_candidate(candidate, trend_fit=80, product_fit=70, inventory_signal=50, evidence_confidence=90, weights=weights)
        self.assertEqual(scored.status, "scored")
        self.assertAlmostEqual(scored.score, 72.5)
        self.assertEqual(scored.coverage, 1.0)
        unverified = Candidate(candidate.candidate_id, candidate.candidate_type, candidate.title, candidate.category_id,
            candidate.target_season, candidate.responds_to_trend_ids, candidate.product_id, candidate.attributes,
            (EvidenceRef("D1", "SRC1", None, None, None, "unverified", False),), candidate.source_record_refs,
            candidate.kg_paths, candidate.assumptions, candidate.unknowns, candidate.risks, candidate.validation_questions)
        rejected = score_candidate(unverified, trend_fit=80, product_fit=70,
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

    def test_duplicate_keeps_highest_scoring_candidate_even_if_generated_later(self):
        def candidate(cid, trend_id):
            return Candidate(cid, "existing_improvement", "Jacket improvement", "outer", None, (trend_id,), "P1",
                (CandidateAttribute("color", "Black", "evidence_observation", ("E",)),),
                (EvidenceRef("E", "S", None, None, None, "ok", True),), (), (), (), (), (), ())

        weaker = candidate("weak", "T-1")
        stronger = candidate("strong", "T-2")
        scores = {
            "weak": CandidateScore("weak", "scored", 72, {}, 1, "w", ("E",)),
            "strong": CandidateScore("strong", "scored", 94, {}, 1, "w", ("E",)),
        }
        result = select_top_candidates((weaker, stronger), scores, max_per_trend=None, max_per_type=None)
        self.assertEqual([item.candidate_id for item in result.selected], ["strong"])
        self.assertEqual(result.excluded["weak"], "중복 후보로 제외되었습니다.")

    def test_single_requested_category_can_fill_top_five_across_trends_and_types(self):
        candidates = []
        scores = {}
        for index in range(5):
            candidate_type = "existing_improvement" if index < 3 else "new_product"
            item = Candidate(
                f"short-{index}", candidate_type, f"Short concept {index}", "men-shorts", "2027SS",
                (f"T-{index}",), f"P-{index}" if index < 3 else None,
                (CandidateAttribute("style", f"direction-{index}", "proposal"),),
                (EvidenceRef(f"E-{index}", "S", None, None, None, "ok", True),), (), (), (), (), (), (),
            )
            candidates.append(item)
            scores[item.candidate_id] = CandidateScore(item.candidate_id, "scored", 95-index, {}, 1, "w", (f"E-{index}",))

        result = select_top_candidates(candidates, scores)
        self.assertEqual(len(result.selected), 5)
        self.assertEqual({item.category_id for item in result.selected}, {"men-shorts"})


if __name__ == "__main__":
    unittest.main()
