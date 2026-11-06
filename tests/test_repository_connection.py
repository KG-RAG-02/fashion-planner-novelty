from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vogue_npp.prototype import repository


class RepositoryConnectionTests(unittest.TestCase):
    def test_context_managed_connection_closes_after_committing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "repository.sqlite3"
            with patch.dict(os.environ, {"VOGUE_DB_PATH": str(path)}):
                with repository.connect() as db:
                    db.execute("CREATE TABLE sample (value TEXT NOT NULL)")
                    db.execute("INSERT INTO sample(value) VALUES ('saved')")
                with self.assertRaises(sqlite3.ProgrammingError):
                    db.execute("SELECT value FROM sample")
                with repository.connect() as check:
                    self.assertEqual(check.execute("SELECT value FROM sample").fetchone()[0], "saved")


if __name__ == "__main__":
    unittest.main()
