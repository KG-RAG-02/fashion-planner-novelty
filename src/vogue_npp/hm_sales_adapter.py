"""Map versioned local H&M aggregates into the internal sales input model.

Category mapping is supplied by the caller because Kaggle's H&M taxonomy is
not the project's agreed merchandising taxonomy. No season is inferred.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Mapping

from .context import (
    AgentResult,
    AttributeSignal,
    SalesAnalysisResult,
    SalesObservation,
)


DEFAULT_PROCESSED_DIR = Path("data/processed/hm-personalized-fashion-recommendations")


def load_hm_sales_analysis(
    *,
    request_id: str,
    schema_version: str,
    requested_category: str,
    source_category_map: Mapping[str, str],
    category_mapping_version: str,
    processed_dir: Path = DEFAULT_PROCESSED_DIR,
    observation_limit: int | None = None,
) -> SalesAnalysisResult:
    """Load exact article-classified category aggregates for one request.

    The mapping may name either H&M ``product_group_name`` or
    ``product_type_name`` and map it to the request taxonomy. Sales are summed
    from weekly article rows after joining the catalog by article_id. This
    avoids assigning every article in a multi-type product_code to one
    representative type. The function does not infer season or channel labels.
    """

    if not request_id.strip() or not schema_version.strip():
        raise ValueError("request_id and schema_version are required.")
    if not requested_category.strip():
        raise ValueError("requested_category is required for category-scoped sales evidence.")
    if not category_mapping_version.strip():
        raise ValueError("category_mapping_version is required for reproducible sales mapping.")
    if observation_limit is not None and observation_limit < 1:
        raise ValueError("observation_limit must be at least 1 when supplied.")

    root = processed_dir.expanduser().resolve()
    manifest_path = root / "manifest.json"
    catalog_path = root / "article_catalog.csv"
    weekly_path = root / "weekly_sales_by_article_channel.csv"
    for path in (manifest_path, catalog_path, weekly_path):
        if not path.is_file():
            raise FileNotFoundError(f"Processed H&M input is missing: {path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    catalog: dict[str, dict[str, str]] = {}
    with catalog_path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required_catalog = {"article_id", "product_code", "product_group_name", "product_type_name", "colour_group_name", "department_name"}
        missing = required_catalog - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"article_catalog.csv is missing columns: {sorted(missing)}")
        for row in reader:
            article_id = (row.get("article_id") or "").strip()
            if article_id:
                catalog[article_id] = row

    normalized_map = {key.strip().casefold(): value.strip() for key, value in source_category_map.items()}
    aggregates: dict[tuple[str, str, str], dict[str, object]] = {}
    unmatched_rows = 0
    with weekly_path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"article_id", "purchase_rows", "week_start", "sales_channel_id"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"weekly_sales_by_article_channel.csv is missing columns: {sorted(missing)}")

        for row in reader:
            article_id = (row.get("article_id") or "").strip()
            meta = catalog.get(article_id)
            if meta is None:
                unmatched_rows += 1
                continue
            group_name = (meta.get("product_group_name") or "").strip() or "(unknown)"
            type_name = (meta.get("product_type_name") or "").strip() or "(unknown)"
            mapped_category = (
                normalized_map.get(type_name.casefold())
                or normalized_map.get(group_name.casefold())
            )
            if mapped_category is None or mapped_category.casefold() != requested_category.strip().casefold():
                continue
            try:
                purchase_rows = int(row["purchase_rows"])
            except (ValueError, TypeError):
                continue
            if purchase_rows < 0:
                continue
            key = (mapped_category, group_name, type_name)
            metric = aggregates.setdefault(key, {"purchase_rows": 0, "articles": set(), "channels": set()})
            metric["purchase_rows"] = int(metric["purchase_rows"]) + purchase_rows
            metric["articles"].add(article_id)  # type: ignore[union-attr]
            metric["channels"].add((row.get("sales_channel_id") or "").strip())  # type: ignore[union-attr]

    observation = manifest.get("observation_period", {})
    period_start = observation.get("start")
    period_end = observation.get("end")
    if not period_start or not period_end:
        raise ValueError("manifest.json does not contain a valid observation period.")
    sales_fingerprint = str(manifest.get("source_transactions", {}).get("container_sha256", "unknown"))[:12]
    catalog_fingerprint = str(manifest.get("source_articles", {}).get("container_sha256", "unknown"))[:12]
    observations: list[SalesObservation] = []
    for (mapped, group_name, type_name), metric in sorted(aggregates.items()):
        category_evidence_id = f"E-HM-CATEGORY-{sales_fingerprint}-{catalog_fingerprint}-{group_name}-{type_name}-{period_start}-{period_end}"
        catalog_evidence_id = f"E-HM-TAXONOMY-{catalog_fingerprint}-{group_name}-{type_name}"
        attributes = (
            AttributeSignal(name="product_group", value=group_name, origin="evidence_observation", evidence_ids=(catalog_evidence_id,)),
            AttributeSignal(name="product_type", value=type_name, origin="evidence_observation", evidence_ids=(catalog_evidence_id,)),
            AttributeSignal(name="unique_article_count", value=len(metric["articles"]), origin="evidence_observation", evidence_ids=(category_evidence_id,)),
        )
        channels = metric["channels"]
        observations.append(SalesObservation(
            category=mapped, purchase_rows=int(metric["purchase_rows"]), period_start=period_start,
            period_end=period_end, source_id="KAGGLE-HM-TRANSACTIONS",
            evidence_ids=(category_evidence_id, catalog_evidence_id), product_group=group_name,
            attributes=attributes, source_channel_code=next(iter(channels)) if len(channels) == 1 else None,
        ))

    truncated = observation_limit is not None and len(observations) > observation_limit
    if truncated:
        observations = observations[:observation_limit]

    status = "ok" if observations else "no_results"
    limitations = [
        "Historical Kaggle purchase rows are observations, not future demand or customer-preference proof.",
        "The source has no explicit merchandising season; no season was inferred.",
        "Category mapping was supplied by the caller and must be reviewed against the project taxonomy.",
        f"Category mapping version: {category_mapping_version}.",
        "Source channel IDs are not mapped to online/store labels in this adapter.",
        "Price is omitted from concept context because its currency and commercial meaning are not established.",
        "Category sales were summed from weekly article aggregates joined to article_catalog by article_id; multi-type product_codes retain their article-level assignments.",
    ]
    if truncated:
        limitations.append(f"Category observations were limited to {observation_limit} mapped group/type rows; the returned rows do not represent the full mapped category total.")
    if unmatched_rows:
        limitations.append(f"{unmatched_rows} weekly article aggregate rows could not be joined to article_catalog and were excluded from category mapping.")
    if not observations:
        limitations.append("No processed article-level category aggregates matched the requested category and supplied mapping.")

    result = AgentResult(
        agent_id="hm-kaggle-sales-analysis",
        request_id=request_id,
        schema_version=schema_version,
        status=status,
        evidence_ids=tuple(
            dict.fromkeys(evidence_id for row in observations for evidence_id in row.evidence_ids)
        ),
            limitations=tuple(limitations),
    )
    return SalesAnalysisResult(
        result=result,
        observations=tuple(observations),
        category_mapping_version=category_mapping_version,
        dataset_label="H&M Kaggle 과거 판매 자료 (article-level category aggregation)",
    )
