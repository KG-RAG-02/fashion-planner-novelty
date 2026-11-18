"""The existing stock item the outfit image pairs with the new product.

One item, chosen by rule: the stock agent's per-trend result (slot) for the primary trend, best rank
first. The stock agent already picks that item from the new product's pair categories, and the orchestrator's
planning sheet shows the same item as the trend's stock card. An item that this service's outfit role rule
(outfit-role-pairing) places in the same role as the requested product (two tops, two bottoms) is
skipped, because the model could not wear both.
"""

from __future__ import annotations

from dataclasses import dataclass

from .context import InventoryProduct, ProductPlanningContext, TrendCandidate
from .styling import _inventory_role, _request_role

OUTFIT_COMPANION_RULE = "primary_trend_stock_slot"


@dataclass(frozen=True)
class OutfitCompanion:
    """The stock item for the outfit image; ``product_index`` indexes the received stock ``products``."""

    product_index: int
    style_id: str | None
    category: str | None
    attributes: tuple[tuple[str, tuple[str, ...]], ...]
    trend_style_id: str
    rank: int | None
    role: str | None
    selection_rule: str = OUTFIT_COMPANION_RULE

    def specification(self) -> dict[str, object]:
        """Image-prompt description of the stock item: identity, category and its stock attributes."""
        spec: dict[str, object] = {"stock_product_id": self.style_id, "category": self.category}
        for name, values in self.attributes:
            spec[name] = values[0] if len(values) == 1 else list(values)
        return {key: value for key, value in spec.items() if value not in (None, "", [])}


def _usable(context: ProductPlanningContext, input_name: str) -> bool:
    return context.input_statuses.get(input_name) in {"ok", "partial"}


def _product_at(context: ProductPlanningContext, source_index: int) -> InventoryProduct | None:
    for position, product in enumerate(context.inventory.products):
        index = product.source_product_index if product.source_product_index is not None else position
        if index == source_index:
            return product
    return None


def _attributes(product: InventoryProduct) -> tuple[tuple[str, tuple[str, ...]], ...]:
    grouped: dict[str, list[str]] = {}
    for signal in product.attributes:
        if isinstance(signal.value, str) and signal.value.strip():
            values = grouped.setdefault(signal.name.strip(), [])
            if signal.value.strip() not in values:
                values.append(signal.value.strip())
    return tuple((name, tuple(values)) for name, values in grouped.items())


def select_outfit_companion(
    context: ProductPlanningContext, primary: TrendCandidate | None,
) -> OutfitCompanion | None:
    """The primary trend's best-ranked stock item that can be worn with the new product, or None."""
    if primary is None or not primary.source_style_id or not _usable(context, "inventory_product_result"):
        return None
    slots = sorted(
        (slot for slot in context.inventory.trend_results
         if slot.style_id == primary.source_style_id and slot.mapping_status == "linked"
         and slot.product_index is not None and slot.status in {None, "ok", "partial"}),
        key=lambda slot: (slot.rank if slot.rank is not None else float("inf"), slot.trend_result_index),
    )
    requested_role = _request_role(context.request)[0] if _usable(context, "planning_request") else None
    for slot in slots:
        product = _product_at(context, slot.product_index)
        if product is None:
            continue
        role = _inventory_role(product)[0]
        if requested_role is not None and role == requested_role:
            continue  # same role as the new product: the model could not wear both
        return OutfitCompanion(
            product_index=slot.product_index,
            style_id=product.style_id,
            category=product.category,
            attributes=_attributes(product),
            trend_style_id=primary.source_style_id,
            rank=slot.rank,
            role=role,
        )
    return None
