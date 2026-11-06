"""Internal, contract-neutral core for VOGUE's New Product Planning Agent."""

from .domain.context import (
    AgentResult,
    AttributeSignal,
    InventoryProduct,
    InventoryProductResult,
    PlanningInputs,
    PlanningRequest,
    ProductPlanningContext,
    SalesAnalysisResult,
    SalesObservation,
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
from .sources.hm.hm_sales_adapter import load_hm_sales_analysis
from .settings import Settings, load_settings
from .workflows.image_generation import (
    ConceptImageWorkflowResult,
    GeneratedImage,
    ImageGenerationRequest,
    ImageGenerationResult,
    OpenAIImageProvider,
    build_image_generation_request,
    run_concept_to_image,
    run_image_generation,
)
from .domain.styling import STYLING_RULE_VERSION, StylingRelationship

__all__ = [
    "AgentResult",
    "AttributeSignal",
    "InventoryProduct",
    "InventoryProductResult",
    "GeneratedImage",
    "ImageGenerationRequest",
    "ImageGenerationResult",
    "PlanningInputs",
    "PlanningRequest",
    "ProductPlanningContext",
    "SalesAnalysisResult",
    "SalesObservation",
    "OpportunityAnalysis",
    "OpportunityFinding",
    "ConceptGenerator",
    "ConceptImageWorkflowResult",
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
    "build_image_generation_request",
    "analyze_opportunities",
    "generate_concept_draft",
    "run_concept_to_image",
    "run_image_generation",
    "load_settings",
    "load_hm_sales_analysis",
    "validate_concept_draft",
]
