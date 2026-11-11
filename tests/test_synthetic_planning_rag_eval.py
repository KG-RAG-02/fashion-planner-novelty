from __future__ import annotations

import unittest

from scripts.evaluate_synthetic_planning_rag import evaluate


class SyntheticPlanningRagEvaluationTests(unittest.TestCase):
    def test_fixed_snapshot_meets_provenance_and_scope_baseline(self):
        report = evaluate()
        self.assertEqual(report["query_count"], 8)
        self.assertEqual(report["rag"]["recall_at_k"], 1.0)
        self.assertEqual(report["rag"]["no_results_accuracy"], 1.0)
        self.assertEqual(report["rag"]["source_locator_content_hash_completeness"], 1.0)
        self.assertEqual(report["rag"]["permission_violation_count"], 0)
        self.assertEqual(report["rag"]["stale_document_leakage_count"], 0)
        self.assertEqual(report["baseline_without_rag"]["recall_at_k"], 0.0)

    def test_each_eval_case_has_a_deterministic_run_id(self):
        first = evaluate()
        second = evaluate()
        self.assertEqual(
            [item["retrieval_run_id"] for item in first["cases"]],
            [item["retrieval_run_id"] for item in second["cases"]],
        )


if __name__ == "__main__":
    unittest.main()
