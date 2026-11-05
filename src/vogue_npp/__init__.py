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
    OpportunityFinding,
    ProductConceptDraft,
    ProposedAttribute,
    SourcedClaim,
    ValidationIssue,
    validate_concept_draft,
)
from .analysis import OpportunityAnalysis, analyze_opportunities
from .generator import ConceptGenerator, RuleBasedConceptGenerator, generate_concept_draft
from .settings import Settings, load_settings

__all__ = [
    "AgentResult",
    "AttributeSignal",
    "InventoryProduct",
    "PlanningInputs",
    "PlanningRequest",
    "ProductPlanningContext",
    "OpportunityAnalysis",
    "OpportunityFinding",
    "ConceptGenerator",
    "ProductConceptDraft",
    "ProposedAttribute",
    "SourcedClaim",
    "TrendCandidate",
    "ValidationIssue",
    "RuleBasedConceptGenerator",
    "Settings",
    "build_planning_context",
    "analyze_opportunities",
    "generate_concept_draft",
    "load_settings",
    "validate_concept_draft",
]
