"""Local keyword retrieval and synthetic evidence record resolution."""

from __future__ import annotations

import re
from typing import Any

from .analytics import _period_sales, analyze
from .fixtures import _evidence, _source_map, _weeks_for_profile, load_fixture


def search_documents(query: str, *, limit: int = 8) -> list[dict[str, Any]]:
    data = load_fixture()
    sources = _source_map(data)
    tokens = [token.casefold() for token in re.findall(r"[\w가-힣]+", query) if len(token) > 1]
    if not tokens:
        return []
    results = []
    for document in data["documents"]:
        for passage in document["passages"]:
            haystack = f"{document['title']} {passage['section']} {passage['text']}".casefold()
            score = sum(haystack.count(token) for token in set(tokens))
            if score:
                results.append({
                    "score": score,
                    "title": document["title"], "section": passage["section"],
                    "text": passage["text"], "passage_id": passage["passage_id"],
                    "source": _evidence(document["source_id"], passage["passage_id"], sources, "문서 구절"),
                    "document_version": document["version"],
                    "season": document["season"],
                })
    return sorted(results, key=lambda item: (-item["score"], item["passage_id"]))[:limit]


def get_evidence(record_id: str) -> dict[str, Any] | None:
    """Resolve a displayed evidence ID to the corresponding synthetic record."""
    data = load_fixture()
    sources = _source_map(data)
    related_source_ids: list[str] = []
    if record_id == "catalog:scope":
        row: Any = {"scope": data["scope"], "style_count": len(data["products"]), "styles": [p["style_id"] for p in data["products"]]}
        source_id = data["scope"]["source_id"]
        kind = "catalog_scope"
    elif record_id.startswith("DOC-"):
        found = next(((doc, passage) for doc in data["documents"] for passage in doc["passages"] if passage["passage_id"] == record_id), None)
        if not found:
            return None
        doc, passage = found
        row = {"document": doc["title"], "section": passage["section"], "text": passage["text"], "date": doc["date"], "season": doc["season"], "version": doc["version"]}
        source_id = doc["source_id"]
        kind = "document_passage"
    elif record_id.startswith("FB-"):
        found = next((item for item in data["feedback"] if item["feedback_id"] == record_id), None)
        if not found:
            return None
        row = found
        source_id = found["source_id"]
        kind = "synthetic_feedback"
    elif record_id == "sales:category":
        profiles = _period_sales(data)
        row = {
            "category": data["scope"]["category"],
            "period": analyze()["period"],
            "style_count": len(profiles),
            "styles": [{"style_id": style_id, **metric} for style_id, metric in profiles.items()],
            "calculation_notes": ["revenue is synthetic MSRP × (1 − discount) × units; it is not source revenue", "return rate is return units divided by units", "stock coverage is separately shown per style"],
        }
        source_id = "SRC-DEMO-SALES-01"
        related_source_ids = ["SRC-DEMO-CATALOG-01"]
        kind = "synthetic_category_sales_aggregate"
    elif ":" in record_id:
        style_id, metric_name = record_id.split(":", 1)
        product = next((item for item in data["products"] if item["style_id"] == style_id), None)
        if not product:
            return None
        sales_profile = next((item for item in data["sales_profiles"] if item["style_id"] == style_id), None)
        inventory = next((item for item in data["inventory"] if item["style_id"] == style_id), None)
        row = {"product": product, "metric": metric_name}
        if metric_name in {"sales", "units", "weekly-average"} and sales_profile:
            row["sales_observation"] = {
                "weekly_units": sales_profile["weekly_units"],
                "units_total": sum(sales_profile["weekly_units"]),
                "week_start_dates": _weeks_for_profile(sales_profile),
                "channel": sales_profile["channel"],
                "discount_rate": sales_profile["discount_rate"],
                "return_units": sales_profile["return_units"],
                "stockout_days": sales_profile["stockout_days"],
            }
            source_id = sales_profile["source_id"]
            kind = "synthetic_sales_aggregate"
        elif metric_name == "inventory" and inventory:
            row["inventory_snapshot"] = inventory
            source_id = inventory["source_id"]
            kind = "synthetic_inventory_snapshot"
        else:
            source_id = product["source_id"]
            kind = "synthetic_product_catalog"
    else:
        return None
    related = [sources[key] for key in related_source_ids]
    return {"record_id": record_id, "kind": kind, "record": row, "source": sources[source_id], "related_sources": related}
