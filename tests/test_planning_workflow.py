from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from vogue_npp.planning_workflow import build_review_brief
from vogue_npp.prototype.repository import (
    list_hm_brief_reviews, list_hm_planning_briefs, save_hm_brief_review,
    save_hm_planning_brief,
)


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = json.loads((ROOT / "data/processed/hm-personalized-fashion-recommendations/hm_planning_analysis.json").read_text())


class PlanningWorkflowTests(unittest.TestCase):
    def test_brief_separates_observation_hypothesis_and_unknown(self) -> None:
        opportunity = ANALYSIS["opportunity_candidates"][0]
        brief = build_review_brief({
            "opportunity_id": opportunity["opportunity_id"],
            "request": {"target_season": "28SS", "color_hypothesis": "해당 유형의 색상 가설"},
        }, ANALYSIS)
        claims = {item["field"]: item for item in brief["claims"]}
        self.assertEqual(brief["status"], "partial")
        self.assertEqual(claims["historical_category_scale"]["kind"], "evidence_observation")
        self.assertTrue(claims["historical_category_scale"]["evidence_ids"])
        self.assertEqual(claims["color_direction"]["kind"], "hypothesis")
        self.assertEqual(claims["target_customer"]["kind"], "unknown")
        self.assertIn("trend_result", brief["image_prompt_package"]["unknowns_to_exclude_from_assertions"])

    def test_unknown_candidate_is_not_substituted(self) -> None:
        with self.assertRaises(ValueError):
            build_review_brief({"opportunity_id": "not-a-candidate"}, ANALYSIS)

    def test_saved_briefs_are_versioned_per_opportunity(self) -> None:
        previous = os.environ.get("VOGUE_DB_PATH")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.environ["VOGUE_DB_PATH"] = str(Path(tmp) / "brief.sqlite3")
                opportunity_id = ANALYSIS["opportunity_candidates"][0]["opportunity_id"]
                payload = {"opportunity_id": opportunity_id, "request": {"color_hypothesis": "MD 검토 가설"}}
                one = save_hm_planning_brief(payload, ANALYSIS)
                two = save_hm_planning_brief(payload, ANALYSIS)
                self.assertEqual((one["brief_version"], two["brief_version"]), (1, 2))
                self.assertEqual(len(list_hm_planning_briefs()), 2)
                self.assertEqual(two["image_prompt_package"]["brief_id"], two["brief_id"])
                review = save_hm_brief_review({
                    "brief_id": one["brief_id"], "decision": "revise",
                    "ratings": {"evidence_grounding": 4, "request_fit": 3, "product_direction": 2},
                    "feedback": "가격 근거 입력 후 재검토",
                })
                self.assertEqual(review["brief_version"], 1)
                self.assertEqual(list_hm_brief_reviews()[0]["brief_id"], one["brief_id"])
                with self.assertRaises(ValueError):
                    save_hm_brief_review({"brief_id": one["brief_id"], "decision": "revise", "ratings": {}})
        finally:
            if previous is None:
                os.environ.pop("VOGUE_DB_PATH", None)
            else:
                os.environ["VOGUE_DB_PATH"] = previous


if __name__ == "__main__":
    unittest.main()
