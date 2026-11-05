from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from vogue_npp.prototype.repository import list_hm_planning_reviews, save_hm_planning_review


ROOT = Path(__file__).resolve().parents[1]


class HmPlanningReviewTests(unittest.TestCase):
    def test_review_preserves_candidate_source_snapshot_separately(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            previous = os.environ.get("VOGUE_DB_PATH")
            os.environ["VOGUE_DB_PATH"] = str(Path(tmp) / "review.sqlite3")
            try:
                analysis = json.loads((ROOT / "data/processed/hm-personalized-fashion-recommendations/hm_planning_analysis.json").read_text())
                opportunity = analysis["opportunity_candidates"][0]
                saved = save_hm_planning_review({
                    "opportunity_id": opportunity["opportunity_id"],
                    "request": {"target_season": "28SS", "market": "KR"},
                    "decision": {"selection_reason": "과거 규모를 검토", "counter_evidence": "자료 기간이 과거임"},
                }, analysis)
                listed = list_hm_planning_reviews()
                self.assertEqual(len(listed), 1)
                self.assertEqual(listed[0]["review_id"], saved["review_id"])
                self.assertEqual(listed[0]["analysis_version"], analysis["analysis_version"])
                self.assertEqual(listed[0]["source_period"], "2018-09-20–2020-09-22")
                self.assertEqual(listed[0]["decision"]["opportunity_snapshot"]["evidence"], opportunity["evidence"])
            finally:
                if previous is None:
                    os.environ.pop("VOGUE_DB_PATH", None)
                else:
                    os.environ["VOGUE_DB_PATH"] = previous

    def test_unlisted_opportunity_is_rejected(self) -> None:
        analysis = {"opportunity_candidates": []}
        with self.assertRaises(ValueError):
            save_hm_planning_review({"opportunity_id": "forged", "decision": {"selection_reason": "x"}}, analysis)


if __name__ == "__main__":
    unittest.main()
