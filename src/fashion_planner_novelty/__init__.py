"""Internal, contract-neutral core for VOGUE's New Product Planning Agent."""

from .domain.context import (
    AgentResult,
    AttributeSignal,
    InventoryProduct,
    InventoryProductResult,
    PlanningInputs,
    PlanningRequest,
    ProductPlanningContext,
    TrendCandidate,
    TrendResult,
    build_planning_context,
)
from .domain.concept import (
    OpportunityFinding,
    ProductConceptDraft,
    ProposedAttribute,
    SourcedClaim,
    ValidationIssue,
    validate_concept_draft,
)
from .domain.analysis import OpportunityAnalysis, analyze_opportunities
from .domain.generator import ConceptGenerator, RuleBasedConceptGenerator, generate_concept_draft
from .settings import Settings, load_settings
from .workflows.image_generation import (
    GeneratedImage,
    ImageGenerationRequest,
    OpenAIImageProvider,
)
from .domain.styling import STYLING_RULE_VERSION, StylingRelationship

__all__ = [
    "AgentResult",
    "AttributeSignal",
    "InventoryProduct",
    "InventoryProductResult",
    "GeneratedImage",
    "ImageGenerationRequest",
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
    "TrendResult",
    "ValidationIssue",
    "RuleBasedConceptGenerator",
    "STYLING_RULE_VERSION",
    "StylingRelationship",
    "OpenAIImageProvider",
    "Settings",
    "build_planning_context",
    "analyze_opportunities",
    "generate_concept_draft",
    "load_settings",
    "validate_concept_draft",
]
