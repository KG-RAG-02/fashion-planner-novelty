from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from vogue_npp.prototype import repository


class PlanningBriefRepositoryTests(unittest.TestCase):
    def test_planning_briefs_are_versioned_without_sales_fixture_dependency(self):
        previous = os.environ.get("VOGUE_DB_PATH")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.environ["VOGUE_DB_PATH"] = str(Path(tmp) / "planning.sqlite3")
                initial = repository.get_brief()
                self.assertEqual(initial["payload"]["category_season"], "미정")
                saved = repository.save_brief({"title":"남성 반바지 검토", "facts":"트렌드 Evidence 확인 필요"})
                current = repository.get_brief()
                self.assertEqual((saved["version"], current["version"]), (1, 1))
                self.assertEqual(current["payload"]["title"], "남성 반바지 검토")
                self.assertEqual(len(repository.list_brief_versions()), 1)
        finally:
            if previous is None:
                os.environ.pop("VOGUE_DB_PATH", None)
            else:
                os.environ["VOGUE_DB_PATH"] = previous


if __name__ == "__main__":
    unittest.main()
