from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from vogue_npp.domain.candidates import Candidate, CandidateAttribute, ScoreWeights
from vogue_npp.domain.retrieval import EvidenceRef
from vogue_npp.domain.trend_batch import TrendBatch
from vogue_npp.domain.trend_evaluator import Category, EvidenceAssessment, InMemoryCategoryTaxonomy, TrendFitWeights
from vogue_npp.workflows.trend_planning import (
    PlanningRunRequest, build_candidate_image_request, generate_candidate_visual,
    run_trend_planning,
)


def candidate():
    return Candidate("c1", "new_product", "Burgundy outerwear", "outer", "2027FW", ("T1",), None,
        (CandidateAttribute("color", "Burgundy", "evidence_observation", ("D1",)),),
        (EvidenceRef("D1", "source", None, "Burgundy", date(2026, 9, 1), "verified", True),), (), (),
        ("시각 세부는 제안입니다.",), ("가격 미정",), ("사업성 미평가",), ("MD 확인",))


class CountingProvider:
    provider_name = "test"
    model = "test"
    def __init__(self): self.calls = 0
    def generate(self, request):
        self.calls += 1
        from vogue_npp.workflows.image_generation import GeneratedImage
        return GeneratedImage(b"png", "image/png", "test", "test")


class VerifiedResolver:
    def assess(self, document):
        return EvidenceAssessment(document.document_id, "verified", True, date(2026, 9, 1), independence_group=document.document_id)


class TrendPlanningVisualTests(unittest.TestCase):
    def test_use_case_is_repeatable_and_requires_configured_scoring(self):
        batch = TrendBatch.from_mapping({"schema_version":"1.0", "batch_id":"B1", "target_season":"2027FW", "trends":[{
            "trend_id":"T1", "name":"Burgundy", "description":"Burgundy color fashion trend",
            "evidence":[{"document_id":"D1", "title":"Source", "excerpt":"Burgundy color fashion trend", "published_at":"2026-09-01"}]}]})
        taxonomy = InMemoryCategoryTaxonomy((Category(
            "outer", "Outerwear", relevant_attribute_types=("color",),
            attribute_value_affinities=(("color:burgundy", 1.0),),
        ),), "tax1")
        request = PlanningRunRequest(batch, existing_products=({
            "product_id":"P1", "category_id":"outer", "name":"Classic jacket",
            "attributes":{"color":"Black"}, "attribute_evidence":{"color":["CAT1"]},
            "evidence_refs":(EvidenceRef("CAT1", "catalog", None, None, None, "permitted", True),),
        },))
        trend_weights = TrendFitWeights(.7,.3,"test-fit-v1")
        first = run_trend_planning(request, taxonomy=taxonomy, evidence_resolver=VerifiedResolver(), trend_fit_weights=trend_weights)
        self.assertEqual(first.status, "needs_scoring_configuration")
        self.assertEqual(len(first.candidates), 2)
        self.assertFalse(first.selection.selected)
        self.assertEqual(first.run_id, run_trend_planning(request, taxonomy=taxonomy, evidence_resolver=VerifiedResolver(), trend_fit_weights=trend_weights).run_id)
        components = {item.candidate_id:{"product_fit":70,"inventory_signal":60,"evidence_confidence":100} for item in first.candidates}
        second = run_trend_planning(request, taxonomy=taxonomy, evidence_resolver=VerifiedResolver(), trend_fit_weights=trend_weights,
            weights=ScoreWeights(.4,.2,.2,.2,"test-approved-v1"), score_components=components)
        self.assertEqual(second.status, "completed")
        self.assertLessEqual(len(second.selection.selected), 5)
        self.assertEqual(len(second.briefs), len(second.selection.selected))
        self.assertTrue(all(brief.visual_status == "not_requested" for brief in second.briefs))
        self.assertEqual(second.briefs[0].claims[0]["kind"], "proposal")
        self.assertEqual(second.briefs[0].claims[0]["evidence_ids"], [])

    def test_prompt_retains_evidence_and_does_not_call_provider(self):
        item = candidate()
        request = build_candidate_image_request(item)
        self.assertIn("D1", request.prompt)
        self.assertEqual(request.evidence_ids, ("D1",))
        provider = CountingProvider()
        result = generate_candidate_visual(item, provider=provider, enabled=False, confirmed=False)
        self.assertEqual(result.status, "not_requested")
        self.assertEqual(provider.calls, 0)

    def test_image_provider_requires_both_enablement_and_confirmation(self):
        item = candidate()
        provider = CountingProvider()
        prepared = generate_candidate_visual(item, provider=provider, enabled=True, confirmed=False)
        self.assertEqual(prepared.status, "ready")
        self.assertEqual(provider.calls, 0)
        with tempfile.TemporaryDirectory() as directory:
            result = generate_candidate_visual(item, provider=provider, enabled=True, confirmed=True, output_dir=Path(directory))
        self.assertEqual(result.status, "generated")
        self.assertEqual(provider.calls, 1)


if __name__ == "__main__":
    unittest.main()
