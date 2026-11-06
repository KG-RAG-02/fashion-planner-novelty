"""Technology-neutral KG/RAG and SQL evidence access ports.

No production database is configured in this repository. Callers must provide
adapters backed by an authorized source; this module includes explicit empty
and in-memory adapters for deterministic local use only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Mapping, Protocol, Sequence


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


class KnowledgeRetriever(Protocol):
    def retrieve(self, query: RetrievalQuery) -> RetrievalResult: ...


@dataclass(frozen=True)
class EmptyKnowledgeRetriever:
    """Explicit no-index adapter. It never pretends the corpus was queried."""

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        return RetrievalResult("no_results", limitations=("KG/vector index is not configured; no retrieval was performed.",))


@dataclass(frozen=True)
class SalesInventoryQuery:
    product_ids: tuple[str, ...]
    period_start: date
    period_end: date
    channel_id: str | None
    inventory_as_of: datetime | None


@dataclass(frozen=True)
class SalesMetric:
    sku_id: str
    units_sold: float | None
    net_revenue: float | None
    currency: str | None
    period_start: date
    period_end: date
    channel_id: str | None
    source_id: str
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class InventoryMetric:
    sku_id: str
    available: float | None
    reserved: float | None
    unit: str | None
    as_of: datetime | None
    location_id: str | None
    definition: str | None
    source_id: str
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class SalesInventoryResult:
    status: QueryStatus
    sales: tuple[SalesMetric, ...] = ()
    inventory: tuple[InventoryMetric, ...] = ()
    limitations: tuple[str, ...] = ()


class MerchDataRepository(Protocol):
    def query_sales_inventory(self, query: SalesInventoryQuery) -> SalesInventoryResult: ...


@dataclass(frozen=True)
class UnconfiguredMerchDataRepository:
    """Signals the absence of an authorized operational data connection."""

    def query_sales_inventory(self, query: SalesInventoryQuery) -> SalesInventoryResult:
        return SalesInventoryResult("error", limitations=("Operational product/sales/inventory source is not configured.",))


@dataclass(frozen=True)
class InMemoryMerchDataRepository:
    """Deterministic fixture repository with explicit no-result vs zero rows."""

    sales_rows: tuple[SalesMetric, ...] = ()
    inventory_rows: tuple[InventoryMetric, ...] = ()
    query_status: str = "ok"

    def query_sales_inventory(self, query: SalesInventoryQuery) -> SalesInventoryResult:
        if self.query_status != "ok":
            return SalesInventoryResult("error", limitations=("Fixture configured to simulate a query failure.",))
        product_ids = set(query.product_ids)
        sales = tuple(row for row in self.sales_rows
                      if row.sku_id.split(":", 1)[0] in product_ids
                      and row.period_start >= query.period_start and row.period_end <= query.period_end
                      and (query.channel_id is None or row.channel_id == query.channel_id))
        inventory = tuple(row for row in self.inventory_rows
                          if row.sku_id.split(":", 1)[0] in product_ids
                          and (query.inventory_as_of is None or (row.as_of is not None and row.as_of <= query.inventory_as_of)))
        if not sales and not inventory:
            return SalesInventoryResult("no_results", limitations=("No matching fixture rows; this is not evidence of actual zero activity or stock.",))
        return SalesInventoryResult("ok", sales, inventory)

