"""Internal concept-draft model and provenance safety checks.

This is an internal review model, not the shared ProductConcept wire schema.
It can validate a candidate produced by the deterministic local generator
without selecting a model provider or committing the team to a public payload
layout.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

from .context import (
    ContextInputStatus,
    ContextConflict,
    ContextOrigin,
    ProductPlanningContext,
)


ClaimKind = Literal[
    "user_requested",
    "evidence_observation",
    "interpretation",
    "hypothesis",
    "proposal",
    "to_validate",
    "unknown",
]


@dataclass(frozen=True)
class SourcedClaim:
    value: str | None
    kind: ClaimKind
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProposedAttribute:
    name: str
    value: str | int | float | bool | None
    kind: ClaimKind
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class OpportunityFinding:
    """Evidence-linked comparison for human review, not a market-gap claim."""

    statement: SourcedClaim
    trend_name: str | None = None
    style_id: str | None = None
    attribute_name: str | None = None
    questions: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProductProfile:
    """One sourced product definition shared by draft, image, and P07 handoff."""

    category: SourcedClaim
    product_type: SourcedClaim
    gender: SourcedClaim
    season: SourcedClaim
    material: SourcedClaim
    silhouette: SourcedClaim
    color: SourcedClaim
    details: tuple[ProposedAttribute, ...] = ()


def _profile_claim(value: str | None, *, kind: ClaimKind = "unknown",
                  evidence_ids: tuple[str, ...] = ()) -> SourcedClaim:
    if value is None or not value.strip():
        return SourcedClaim(None, "unknown")
    return SourcedClaim(value.strip(), kind, evidence_ids)


def base_product_profile(context: ProductPlanningContext) -> ProductProfile:
    """Build fields fixed by the request; leave analytical design fields unknown."""
    request = context.request
    request_ok = context.input_statuses.get("planning_request") in {"ok", "partial"}

    def request_field(name: str, value: str | None) -> SourcedClaim:
        if not request_ok or not value:
            return _profile_claim(None)
        ids = tuple(request.field_evidence_ids.get(name, ()))
        return _profile_claim(value, kind="user_requested", evidence_ids=ids)

    explicit: dict[str, SourcedClaim] = {}
    aliases = {
        "product_type": {"product_type", "product type", "상품종류", "상품 종류"},
        "gender": {"gender", "성별"},
        "material": {"material", "fabric", "소재", "원단"},
        "silhouette": {"silhouette", "실루엣"},
        "color": {"color", "colour", "색상", "컬러"},
    }
    if request_ok:
        for signal in request.requested_attributes:
            if signal.value is None or signal.origin == "unknown":
                continue
            field_name = next((key for key, names in aliases.items()
                               if signal.name.strip().casefold() in {n.casefold() for n in names}), None)
            if not field_name or not isinstance(signal.value, str) or not signal.value.strip():
                continue
            kind: ClaimKind = "user_requested" if signal.origin == "user_requested" else (
                "evidence_observation" if signal.origin == "evidence_observation" else "to_validate"
            )
            explicit.setdefault(field_name, _profile_claim(
                signal.value, kind=kind, evidence_ids=signal.evidence_ids,
            ))
    gender = explicit.get("gender", _profile_claim(None))
    if gender.value is not None and gender.value.casefold() not in {"women", "men", "unisex", "unknown"}:
        gender = _profile_claim(None)
    product_type = explicit.get("product_type")
    if product_type is None:
        product_type = request_field("product_role", request.product_role)
    return ProductProfile(
        category=request_field("category", request.category),
        product_type=product_type,
        gender=gender,
        season=request_field("season", request.season),
        material=explicit.get("material", _profile_claim(None)),
        silhouette=explicit.get("silhouette", _profile_claim(None)),
        color=explicit.get("color", _profile_claim(None)),
    )


@dataclass(frozen=True)
class ProductConceptDraft:
    """Internal candidate shape for human review before wire serialization."""

    request_id: str
    season: str | None
    category: str | None
    opportunity: SourcedClaim
    target_customer: SourcedClaim
    product_definition: SourcedClaim
    product_profile: ProductProfile
    market: tuple[str, ...] = ()
    channel: tuple[str, ...] = ()
    request_constraints: tuple[str, ...] = ()
    field_origins: Mapping[str, ContextOrigin] = field(default_factory=dict)
    input_statuses: Mapping[str, ContextInputStatus] = field(default_factory=dict)
    input_conflicts: tuple[ContextConflict, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    attributes: tuple[ProposedAttribute, ...] = ()
    opportunity_findings: tuple[OpportunityFinding, ...] = ()
    relation_to_own_products: tuple[SourcedClaim, ...] = ()
    differentiation: tuple[SourcedClaim, ...] = ()
    risks: tuple[SourcedClaim, ...] = ()
    questions_for_validation: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidationIssue:
    path: str
    code: str
    message: str


def _check_claim(
    claim: SourcedClaim,
    *,
    path: str,
    known_evidence_ids: set[str],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if claim.kind not in {
        "user_requested",
        "evidence_observation",
        "interpretation",
        "hypothesis",
        "proposal",
        "to_validate",
        "unknown",
    }:
        issues.append(
            ValidationIssue(
                path=path,
                code="UNSUPPORTED_CLAIM_KIND",
                message="The claim kind is not recognized by this internal model.",
            )
        )
    if claim.value is not None and not claim.value.strip():
        issues.append(
            ValidationIssue(
                path=path,
                code="EMPTY_CLAIM_VALUE",
                message="A claim value must contain text or be null.",
            )
        )
    if claim.kind == "unknown" and claim.value is not None:
        issues.append(
            ValidationIssue(
                path=path,
                code="UNKNOWN_HAS_VALUE",
                message="An unknown claim must not carry an asserted value.",
            )
        )
    if claim.kind == "evidence_observation" and not claim.evidence_ids:
        issues.append(
            ValidationIssue(
                path=path,
                code="OBSERVATION_WITHOUT_EVIDENCE",
                message="An evidence observation must cite at least one input Evidence ID.",
            )
        )
    for evidence_id in claim.evidence_ids:
        if evidence_id not in known_evidence_ids:
            issues.append(
                ValidationIssue(
                    path=path,
                    code="UNKNOWN_EVIDENCE_ID",
                    message=f"Evidence ID '{evidence_id}' is not present in the inputs.",
                )
            )
    return issues


def validate_concept_draft(
    context: ProductPlanningContext,
    draft: ProductConceptDraft,
) -> tuple[ValidationIssue, ...]:
    """Check provenance and user-request fidelity for an internal draft.

    This does not validate a public schema, infer whether evidence is licensed,
    decide whether a concept is commercially viable, or approve the concept.
    """

    issues: list[ValidationIssue] = []
    if draft.request_id != context.request_id:
        issues.append(
            ValidationIssue(
                path="request_id",
                code="REQUEST_ID_MISMATCH",
                message="The concept draft must retain the input request_id.",
            )
        )

    for field_name, origin in draft.field_origins.items():
        if origin not in {"user", "inferred", "unknown"}:
            issues.append(
                ValidationIssue(
                    path=f"field_origins.{field_name}",
                    code="UNSUPPORTED_FIELD_ORIGIN",
                    message="A request field origin must be user, inferred, or unknown.",
                )
            )

    known_evidence_ids = set(context.evidence_ids)
    for path, claim in (
        ("opportunity", draft.opportunity),
        ("target_customer", draft.target_customer),
        ("product_definition", draft.product_definition),
    ):
        issues.extend(
            _check_claim(
                claim,
                path=path,
                known_evidence_ids=known_evidence_ids,
            )
        )

    profile = draft.product_profile
    for field_name in ("category", "product_type", "gender", "season", "material", "silhouette", "color"):
        claim = getattr(profile, field_name)
        issues.extend(_check_claim(claim, path=f"product_profile.{field_name}",
                                   known_evidence_ids=known_evidence_ids))
    if profile.gender.value is not None and profile.gender.value not in {
        "women", "men", "unisex", "unknown",
    }:
        issues.append(ValidationIssue(
            path="product_profile.gender", code="INVALID_GENDER",
            message="Gender must match the Project_07 allowed enum.",
        ))
    if profile.category.value != draft.category and profile.category.value is not None:
        issues.append(ValidationIssue(
            path="product_profile.category", code="CATEGORY_MISMATCH",
            message="Structured product category must match the planning draft category.",
        ))
    if profile.season.value != draft.season and profile.season.value is not None:
        issues.append(ValidationIssue(
            path="product_profile.season", code="SEASON_MISMATCH",
            message="Structured product season must match the planning draft season.",
        ))
    for index, attribute in enumerate(profile.details):
        if not attribute.name.strip():
            issues.append(ValidationIssue(path=f"product_profile.details[{index}]",
                                          code="EMPTY_ATTRIBUTE_NAME",
                                          message="A product detail must have a name."))
        if attribute.kind not in {
            "user_requested", "evidence_observation", "interpretation", "hypothesis",
            "proposal", "to_validate", "unknown",
        }:
            issues.append(ValidationIssue(path=f"product_profile.details[{index}]",
                                          code="UNSUPPORTED_CLAIM_KIND",
                                          message="A product detail has an unsupported claim kind."))
        if attribute.kind == "unknown" and attribute.value is not None:
            issues.append(ValidationIssue(path=f"product_profile.details[{index}]",
                                          code="UNKNOWN_HAS_VALUE",
                                          message="An unknown product detail must not carry a value."))
        for evidence_id in attribute.evidence_ids:
            if evidence_id not in known_evidence_ids:
                issues.append(ValidationIssue(path=f"product_profile.details[{index}]",
                                              code="UNKNOWN_EVIDENCE_ID",
                                              message=f"Evidence ID '{evidence_id}' is not present in the inputs."))
        if attribute.kind == "evidence_observation" and not attribute.evidence_ids:
            issues.append(ValidationIssue(path=f"product_profile.details[{index}]",
                                          code="OBSERVATION_WITHOUT_EVIDENCE",
                                          message="An evidence observation must cite an input Evidence ID."))

    requested_profile_values = {
        str(value) for value in (
            context.request.original_query, context.request.season, context.request.category,
            context.request.product_role, context.request.target_customer,
            *context.request.market, *context.request.channel, *context.request.constraints,
            *(signal.value for signal in context.request.requested_attributes if signal.value is not None),
        ) if value
    }
    for field_name in ("product_type", "gender", "material", "silhouette", "color"):
        claim = getattr(profile, field_name)
        if claim.kind == "user_requested" and claim.value not in requested_profile_values:
            issues.append(ValidationIssue(
                path=f"product_profile.{field_name}", code="UNSUPPORTED_USER_REQUEST_CLAIM",
                message="A user-requested profile value must match a value in the request.",
            ))

    for collection_name, claims in (
        ("relation_to_own_products", draft.relation_to_own_products),
        ("differentiation", draft.differentiation),
        ("risks", draft.risks),
    ):
        for index, claim in enumerate(claims):
            issues.extend(
                _check_claim(
                    claim,
                    path=f"{collection_name}[{index}]",
                    known_evidence_ids=known_evidence_ids,
                )
            )

    for index, finding in enumerate(draft.opportunity_findings):
        issues.extend(
            _check_claim(
                finding.statement,
                path=f"opportunity_findings[{index}].statement",
                known_evidence_ids=known_evidence_ids,
            )
        )
        for question_index, question in enumerate(finding.questions):
            if not question.strip():
                issues.append(
                    ValidationIssue(
                        path=f"opportunity_findings[{index}].questions[{question_index}]",
                        code="EMPTY_VALIDATION_QUESTION",
                        message="An opportunity review question must contain text.",
                    )
                )

    requested_attributes = {
        (signal.name.strip().casefold(), signal.value)
        for signal in context.request.requested_attributes
        if signal.value is not None
    }
    for index, attribute in enumerate(draft.attributes):
        path = f"attributes[{index}]"
        if not attribute.name.strip():
            issues.append(
                ValidationIssue(
                    path=path,
                    code="EMPTY_ATTRIBUTE_NAME",
                    message="An attribute must have a non-empty name.",
                )
            )

        if attribute.kind not in {
            "user_requested",
            "evidence_observation",
            "interpretation",
            "hypothesis",
            "proposal",
            "to_validate",
            "unknown",
        }:
            issues.append(
                ValidationIssue(
                    path=path,
                    code="UNSUPPORTED_CLAIM_KIND",
                    message="The attribute kind is not recognized by this internal model.",
                )
            )
        if isinstance(attribute.value, str) and not attribute.value.strip():
            issues.append(
                ValidationIssue(
                    path=path,
                    code="EMPTY_ATTRIBUTE_VALUE",
                    message="An attribute value must contain text or be null.",
                )
            )
        if attribute.kind == "unknown" and attribute.value is not None:
            issues.append(
                ValidationIssue(
                    path=path,
                    code="UNKNOWN_ATTRIBUTE_HAS_VALUE",
                    message="An unknown attribute must not carry an asserted value.",
                )
            )
        if attribute.kind == "evidence_observation" and not attribute.evidence_ids:
            issues.append(
                ValidationIssue(
                    path=path,
                    code="OBSERVATION_WITHOUT_EVIDENCE",
                    message="An observed attribute must cite input Evidence IDs.",
                )
            )
        if attribute.kind == "user_requested" and attribute.value is not None:
            key = (attribute.name.strip().casefold(), attribute.value)
            if key not in requested_attributes:
                issues.append(
                    ValidationIssue(
                        path=path,
                        code="UNREQUESTED_VALUE_MARKED_AS_USER_INPUT",
                        message=(
                            "A user_requested attribute must match a non-empty "
                            "attribute in the original planning request."
                        ),
                    )
                )
        for evidence_id in attribute.evidence_ids:
            if evidence_id not in known_evidence_ids:
                issues.append(
                    ValidationIssue(
                        path=path,
                        code="UNKNOWN_EVIDENCE_ID",
                        message=f"Evidence ID '{evidence_id}' is not present in the inputs.",
                    )
                )

    profile_attribute_aliases = {
        "product_type": {"product_type", "product type", "상품종류", "상품 종류"},
        "gender": {"gender", "성별"},
        "material": {"material", "fabric", "소재", "원단"},
        "silhouette": {"silhouette", "shape", "실루엣"},
        "color": {"color", "colour", "color_group", "colour_group", "색상", "컬러"},
    }
    for field_name, aliases in profile_attribute_aliases.items():
        profile_value = getattr(profile, field_name).value
        if profile_value is None:
            continue
        matching_values = {
            str(item.value).strip() for item in draft.attributes
            if item.name.strip().casefold() in {name.casefold() for name in aliases}
            and item.value is not None
        }
        if matching_values and profile_value not in matching_values:
            issues.append(ValidationIssue(
                path=f"product_profile.{field_name}", code="PROFILE_ATTRIBUTE_MISMATCH",
                message="Structured profile conflicts with the corresponding draft attribute.",
            ))
    for index, question in enumerate(draft.questions_for_validation):
        if not question.strip():
            issues.append(
                ValidationIssue(
                    path=f"questions_for_validation[{index}]",
                    code="EMPTY_VALIDATION_QUESTION",
                    message="A validation question must contain text.",
                )
            )

    return tuple(issues)
