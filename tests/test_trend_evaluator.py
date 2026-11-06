from __future__ import annotations

import unittest
from datetime import date

from vogue_npp.domain.trend_batch import TrendBatch
from vogue_npp.domain.trend_evaluator import (
    Category, CategoryMapping, EvidenceAssessment, InMemoryCategoryTaxonomy,
    TrendFitWeights, evaluate_trend_batch,
)


def batch():
    return TrendBatch.from_mapping({
        "schema_version": "1.0", "batch_id": "TB-1",
        "trends": [{"trend_id": "T-1", "name": " Burgundy ", "description": "Burgundy color trend",
                    "evidence": [{"document_id": "D-1", "title": "Report", "excerpt": "Burgundy color adoption", "published_at": "2026-09-01"}]}]
    })


class VerifiedResolver:
    def assess(self, document):
        return EvidenceAssessment(document.document_id, "verified", True, date(2026, 9, 1))


class CategoryTests(unittest.TestCase):
    def test_requested_four_trend_names_are_extracted_as_supported_style_values(self):
        names = ("미니멀리즘", "맥시멀리즘", "고프코어", "발레코어")
        batch_data = {
            "schema_version": "1.0", "batch_id": "TB-FOUR-STYLES",
            "trends": [{
                "trend_id": f"T-{index}", "name": name,
                "description": f"{name} 패션 방향",
                "evidence": [{
                    "document_id": f"DOC-{index}", "title": f"{name} report",
                    "excerpt": f"{name} 패션 방향", "published_at": "2026-09-01",
                }],
            } for index, name in enumerate(names, 1)],
        }
        evaluated = evaluate_trend_batch(
            TrendBatch.from_mapping(batch_data),
            InMemoryCategoryTaxonomy((Category("men-shorts", "Men's shorts", relevant_attribute_types=("style",)),), "tax-1"),
            VerifiedResolver(), TrendFitWeights(0.7, 0.3, "test-fit-v1"),
        )
        extracted = list(evaluated)
        self.assertEqual([item.attributes[0].value for item in extracted], list(names))
        self.assertTrue(all(item.attributes[0].status == "evidence_observation" for item in extracted))
        self.assertTrue(all(item.category_evaluations[0].status == "ok" for item in extracted))

    def test_taxonomy_exact_alias_ambiguous_unmapped(self):
        taxonomy = InMemoryCategoryTaxonomy((
            Category("outer", "Outerwear", ("coat",)),
            Category("jacket", "Jacket", ("coat",)),
            Category("knit", "Knitwear", ("sweater",)),
        ), "tax-1")
        self.assertEqual(taxonomy.map_category("Outerwear").status, "exact")
        self.assertEqual(taxonomy.map_category("sweater").status, "alias")
        self.assertEqual(taxonomy.map_category("coat").status, "ambiguous")
        self.assertEqual(taxonomy.map_category("unknown").status, "unmapped")

    def test_evaluates_each_category_without_claiming_rank_and_preserves_evidence(self):
        taxonomy = InMemoryCategoryTaxonomy((
            Category("outer", "Outerwear", relevant_attribute_types=("color",)),
            Category("knit", "Knitwear", relevant_attribute_types=("material",)),
        ), "tax-1")
        result = evaluate_trend_batch(batch(), taxonomy, VerifiedResolver(), TrendFitWeights(.7,.3,"test-v1"))[0]
        self.assertEqual([item.category_id for item in result.category_evaluations], ["outer", "knit"])
        self.assertEqual([item.score for item in result.category_evaluations], [100.0, 30.0])
        self.assertTrue(all(item.status == "ok" for item in result.category_evaluations))
        self.assertIn("D-1", result.attributes[0].evidence_ids)
        self.assertFalse(hasattr(result, "rank"))

    def test_unverified_evidence_never_gets_a_fit_score(self):
        taxonomy = InMemoryCategoryTaxonomy((Category("outer", "Outerwear"),), "tax-1")
        result = evaluate_trend_batch(batch(), taxonomy)[0]
        self.assertFalse(result.evidence[0].verified)
        self.assertIsNone(result.category_evaluations[0].score)
        self.assertEqual(result.category_evaluations[0].status, "insufficient_evidence")


if __name__ == "__main__":
    unittest.main()
