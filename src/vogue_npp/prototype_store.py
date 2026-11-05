"""Compatibility facade for the decomposed local prototype components.

New code should import directly from :mod:`vogue_npp.prototype` modules.
This facade preserves the original import surface for the prototype server.
"""

from __future__ import annotations

from .prototype.analytics import _period_sales, analyze
from .prototype.config import (
    DB_PATH,
    DEFAULT_DB_PATH,
    DEFAULT_HM_ANALYSIS_PATH,
    FIXTURE,
    HM_ANALYSIS_PATH,
    IMAGEGEN_ASSET,
    IMAGEGEN_VARIANT_ID,
    ROOT,
)
from .prototype.fixtures import (
    _evidence,
    _source_map,
    _weeks_for_profile,
    get_hm_analysis,
    load_fixture,
)
from .prototype.repository import (
    BRIEF_FIELDS,
    _mock_svg,
    connect,
    generate_variant,
    get_brief,
    get_variant_image,
    initialize,
    list_brief_versions,
    list_evaluations,
    list_variants,
    save_brief,
    save_evaluation,
    utc_now,
)
from .prototype.retrieval import get_evidence, search_documents

__all__ = [
    "ROOT", "FIXTURE", "DB_PATH", "HM_ANALYSIS_PATH", "IMAGEGEN_VARIANT_ID",
    "IMAGEGEN_ASSET", "BRIEF_FIELDS", "analyze", "connect", "generate_variant",
    "get_brief", "get_evidence", "get_hm_analysis", "get_variant_image",
    "initialize", "list_brief_versions", "list_evaluations", "list_variants",
    "load_fixture", "save_brief", "save_evaluation", "search_documents", "utc_now",
]
