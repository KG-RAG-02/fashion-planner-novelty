"""Technology-neutral KG/RAG evidence access ports.

No production database is configured in this repository. Callers must provide
adapters backed by an authorized source; this module includes explicit empty
and in-memory adapters for deterministic local use only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol


QueryStatus = str  # "ok", "no_results", "error"


@dataclass(frozen=True)
class EvidenceRef:
    evidence_id: str
    source_id: str
    locator: str | None
    quote: str | None
    source_date: date | None
    access_status: str
    verified: bool


@dataclass(frozen=True)
class KGPath:
    nodes: tuple[str, ...]
    relationships: tuple[str, ...]
    taxonomy_version: str
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class RetrievalResult:
    status: QueryStatus
    evidence: tuple[EvidenceRef, ...] = ()
    kg_paths: tuple[KGPath, ...] = ()
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class RetrievalQuery:
    trend_ids: tuple[str, ...]
    category_ids: tuple[str, ...]
    attribute_terms: tuple[str, ...] = ()
    allowed_source_ids: tuple[str, ...] = ()
    limit: int = 50

    def __post_init__(self) -> None:
        if self.limit < 1 or self.limit > 500:
            raise ValueError("retrieval limit must be between 1 and 500")


class KnowledgeRetriever(Protocol):
    def retrieve(self, query: RetrievalQuery) -> RetrievalResult: ...


@dataclass(frozen=True)
class EmptyKnowledgeRetriever:
    """Explicit no-index adapter. It never pretends the corpus was queried."""

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        return RetrievalResult("no_results", limitations=("KG/vector index is not configured; no retrieval was performed.",))
