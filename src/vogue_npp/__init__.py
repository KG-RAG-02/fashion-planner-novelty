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
from .concept import (
    ProductConceptDraft,
    ProposedAttribute,
    SourcedClaim,
    ValidationIssue,
    validate_concept_draft,
)
from .generator import generate_concept_draft

__all__ = [
    "AgentResult",
    "AttributeSignal",
    "InventoryProduct",
    "PlanningInputs",
    "PlanningRequest",
    "ProductPlanningContext",
    "ProductConceptDraft",
    "ProposedAttribute",
    "SourcedClaim",
    "TrendCandidate",
    "ValidationIssue",
    "build_planning_context",
    "generate_concept_draft",
    "validate_concept_draft",
]
