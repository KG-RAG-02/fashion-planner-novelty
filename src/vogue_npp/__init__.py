"""Internal, contract-neutral core for VOGUE's New Product Planning Agent."""

from .context import (
    AgentResult,
    AttributeSignal,
    InventoryProduct,
    PlanningInputs,
    PlanningRequest,
    ProductPlanningContext,
    SalesAnalysisResult,
    SalesObservation,
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
from .hm_sales_adapter import load_hm_sales_analysis
from .settings import Settings, load_settings

__all__ = [
    "AgentResult",
    "AttributeSignal",
    "InventoryProduct",
    "PlanningInputs",
    "PlanningRequest",
    "ProductPlanningContext",
    "SalesAnalysisResult",
    "SalesObservation",
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
    "load_hm_sales_analysis",
    "validate_concept_draft",
]
