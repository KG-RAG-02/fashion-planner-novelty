"""Filesystem locations used by the local prototype."""

from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = ROOT / "data" / "local" / "prototype.sqlite3"
def database_path() -> Path:
    """Resolve the database path at call time so runtime configuration is honored."""

    return Path(os.getenv("VOGUE_DB_PATH", str(DEFAULT_DB_PATH)))


# Backwards-compatible import-time values; runtime code uses the resolvers above.
DB_PATH = database_path()
