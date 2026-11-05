"""Internal, contract-neutral core for VOGUE's New Product Planning Agent."""

from .context import (
    AgentResult,
    AttributeSignal,
    InventoryProduct,
    PlanningInputs,
    PlanningRequest,
    ProductPlanningContext,
    TrendCandidate,
    build_planning_context,
)

__all__ = [
    "AgentResult",
    "AttributeSignal",
    "InventoryProduct",
    "PlanningInputs",
    "PlanningRequest",
    "ProductPlanningContext",
    "TrendCandidate",
    "build_planning_context",
]
