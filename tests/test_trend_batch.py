from __future__ import annotations

import json
import unittest

from vogue_npp.domain.trend_batch import TrendBatch, TrendBatchValidationError


def payload() -> dict:
    return {
        "schema_version": "1.0",
        "batch_id": "TB-001",
        "target_season": "2027FW",
        "trends": [{
            "name": "Burgundy",
            "description": "버건디 컬러를 활용한 가을·겨울 패션 트렌드",
            "evidence": [{
                "document_id": "DOC-1",
                "title": "Fashion color report",
                "published_at": "2026-10-20",
                "excerpt": "버건디 색상 사용이 보고되었습니다.",
            }],
        }],
    }


class TrendBatchTests(unittest.TestCase):
    def test_accepts_name_description_and_evidence_without_rank_or_similarity(self) -> None:
        batch = TrendBatch.from_json(json.dumps(payload(), ensure_ascii=False))
        self.assertEqual(batch.trends[0].name, "Burgundy")
        self.assertIsNone(batch.trends[0].trend_id)
        self.assertFalse(hasattr(batch.trends[0], "rank"))
        self.assertFalse(hasattr(batch.trends[0], "similarity"))

    def test_rejects_missing_name_and_evidence(self) -> None:
        data = payload()
        data["trends"][0]["name"] = "  "
        with self.assertRaisesRegex(TrendBatchValidationError, "name"):
            TrendBatch.from_mapping(data)
        data = payload()
        data["trends"][0]["evidence"] = []
        with self.assertRaisesRegex(TrendBatchValidationError, "evidence"):
            TrendBatch.from_mapping(data)

    def test_rejects_duplicate_ids_and_untraceable_evidence(self) -> None:
        data = payload()
        data["trends"].append(data["trends"][0] | {"trend_id": "T-1"})
        data["trends"][0]["trend_id"] = "T-1"
        with self.assertRaisesRegex(TrendBatchValidationError, "duplicate trend_id"):
            TrendBatch.from_mapping(data)
        data = payload()
        data["trends"][0]["evidence"][0].pop("excerpt")
        with self.assertRaisesRegex(TrendBatchValidationError, "traced"):
            TrendBatch.from_mapping(data)

    def test_rejects_rank_similarity_unknown_fields_and_large_payload(self) -> None:
        data = payload()
        data["trends"][0]["rank"] = 1
        with self.assertRaisesRegex(TrendBatchValidationError, "unsupported fields"):
            TrendBatch.from_mapping(data)
        with self.assertRaisesRegex(TrendBatchValidationError, "payload exceeds"):
            TrendBatch.from_json(b" " * 1_000_001)

    def test_rejects_duplicate_document_ids_and_bad_url(self) -> None:
        data = payload()
        data["trends"][0]["evidence"].append(data["trends"][0]["evidence"][0])
        with self.assertRaisesRegex(TrendBatchValidationError, "duplicate document_id"):
            TrendBatch.from_mapping(data)
        data = payload()
        data["trends"][0]["evidence"][0]["source_url"] = "file:///etc/passwd"
        with self.assertRaisesRegex(TrendBatchValidationError, r"HTTP\(S\)"):
            TrendBatch.from_mapping(data)


if __name__ == "__main__":
    unittest.main()
