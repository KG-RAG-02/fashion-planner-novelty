"""Map versioned local H&M aggregates into the internal sales input model.

Category mapping is supplied by the caller because Kaggle's H&M taxonomy is
not the project's agreed merchandising taxonomy. No season is inferred.
"""

from __future__ import annotations

import csv
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
    observation_limit: int = 50,
) -> SalesAnalysisResult:
    """Load top, explicitly category-mapped Style aggregates for one request.

    The mapping may name either H&M ``product_group_name`` or
    ``product_type_name`` and map it to the request taxonomy. The function
    does not map season or channel codes and does not interpret price as money.
    """

    if not request_id.strip() or not schema_version.strip():
        raise ValueError("request_id and schema_version are required.")
    if not requested_category.strip():
        raise ValueError("requested_category is required for category-scoped sales evidence.")
    if not category_mapping_version.strip():
        raise ValueError("category_mapping_version is required for reproducible sales mapping.")
    if observation_limit < 1:
        raise ValueError("observation_limit must be at least 1.")

    path = processed_dir.expanduser().resolve() / "style_sales_summary.csv"
    if not path.is_file():
        raise FileNotFoundError(f"Processed H&M sales summary is missing: {path}")

    normalized_map = {key.strip().casefold(): value.strip() for key, value in source_category_map.items()}
    observations: list[SalesObservation] = []
    truncated = False
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {
            "product_code", "product_group_name", "product_type_name", "purchase_rows",
            "observation_period", "sales_source_id", "catalog_source_id",
            "sales_evidence_id", "catalog_evidence_id",
        }
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"style_sales_summary.csv is missing columns: {sorted(missing)}")

        for row in reader:
            mapped_category = (
                normalized_map.get((row.get("product_type_name") or "").strip().casefold())
                or normalized_map.get((row.get("product_group_name") or "").strip().casefold())
            )
            if mapped_category is None or mapped_category.casefold() != requested_category.strip().casefold():
                continue
            period = (row.get("observation_period") or "").split("–", maxsplit=1)
            if len(period) != 2 or not all(part.strip() for part in period):
                continue
            try:
                purchase_rows = int(row["purchase_rows"])
            except (ValueError, TypeError):
                continue
            sales_evidence_id = row["sales_evidence_id"].strip()
            catalog_evidence_id = row["catalog_evidence_id"].strip()
            if purchase_rows < 0 or not sales_evidence_id or not catalog_evidence_id:
                continue

            catalog_attributes = tuple(
                AttributeSignal(name=name, value=value, origin="evidence_observation", evidence_ids=(catalog_evidence_id,))
                for name, value in (
                    ("product_group", row.get("product_group_name", "").strip()),
                    ("product_type", row.get("product_type_name", "").strip()),
                    ("color_group", row.get("representative_colour_group_name", "").strip()),
                    ("department", row.get("department_name", "").strip()),
                )
                if value
            )
            observations.append(
                SalesObservation(
                    category=mapped_category,
                    purchase_rows=purchase_rows,
                    period_start=period[0].strip(),
                    period_end=period[1].strip(),
                    source_id=row["sales_source_id"].strip(),
                    evidence_ids=(sales_evidence_id, catalog_evidence_id),
                    product_code=row["product_code"].strip() or None,
                    product_group=row["product_group_name"].strip() or None,
                    attributes=catalog_attributes,
                    source_channel_code=row.get("top_sales_channel_id", "").strip() or None,
                )
            )
            if len(observations) > observation_limit:
                observations.pop()
                truncated = True
                break

    status = "ok" if observations else "no_results"
    limitations = [
        "Historical Kaggle purchase rows are observations, not future demand or customer-preference proof.",
        "The source has no explicit merchandising season; no season was inferred.",
        "Category mapping was supplied by the caller and must be reviewed against the project taxonomy.",
        f"Category mapping version: {category_mapping_version}.",
        "Source channel IDs are not mapped to online/store labels in this adapter.",
        "Price is omitted from concept context because its currency and commercial meaning are not established.",
    ]
    if truncated:
        limitations.append(f"Sales context was limited to the top {observation_limit} matching Style rows.")
    if not observations:
        limitations.append("No processed Style rows matched the requested category and supplied mapping.")

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
        dataset_label="H&M Kaggle 과거 판매 자료",
    )
