"""Prompted concept generation with strict local validation and rule fallback.

The HTTP layer can inject the opt-in OpenAI Responses adapter. Offline tests
use fake providers; disabled or failed model calls retain the rule baseline.
"""

from __future__ import annotations

import copy
import json
import math
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

from ..domain.concept import (
    ProductProfile,
    ProductConceptDraft,
    ProposedAttribute,
    SourcedClaim,
    ValidationIssue,
    base_product_profile,
    validate_concept_draft,
)
from ..domain.context import ProductPlanningContext
from ..domain.generator import ConceptGenerator, RuleBasedConceptGenerator
from ..domain.prompt_budget import (
    PromptReduction,
    reduce_prompt_data,
    resolve_output_aliases,
    restore_model_text,
)
from ..domain.prompt_safety import serialize_untrusted_prompt_data
from ..domain.prompt_registry import load_prompt, prompt_version_id, render_prompt
from ..domain.trend_basis import TREND_SELECTION_RULE, build_trend_basis, select_primary_trend


PROMPT_VERSION = prompt_version_id("text_planning")
MAX_MODEL_OUTPUT_CHARS = 64_000
CLAIM_KINDS = {"user_requested", "evidence_observation", "proposal", "hypothesis", "unknown"}
PLANNING_SYSTEM_PROMPT = load_prompt("text_planning", "system")
INPUT_OVER_BUDGET_LIMITATION = (
    "텍스트 LLM 입력 데이터가 축약 후에도 한도를 넘어 LLM을 호출하지 않고 결정적 규칙 기반 초안을 사용했습니다."
)


class ConceptOutputValidationError(ValueError):
    """Safe validation failure carrying only a stable issue code."""

    def __init__(self, issue_code: str):
        super().__init__("structured concept output failed local validation")
        self.code = f"TEXT_OUTPUT_VALIDATION_{issue_code}"


class StructuredTextProvider(Protocol):
    """Provider seam. Implementations must expose no tools or side-effect APIs."""

    model_name: str

    def generate_json(self, *, system_prompt: str, user_prompt: str) -> str | dict[str, Any]:
        """Return one JSON object; implementations must not log prompts or secrets."""


@dataclass(frozen=True)
class PlanningPrompt:
    version: str
    system_prompt: str
    user_prompt: str
    allowed_evidence_ids: frozenset[str]
    # Set only when the data exceeded PROMPT_DATA_MAX_CHARS and was reduced.
    reduction: PromptReduction | None = None
    # True when even the reduced data does not fit. user_prompt is then empty:
    # sending it would mean sending the serializer's ID-less preview.
    over_budget: bool = False


def _usable(context: ProductPlanningContext, slot: str) -> bool:
    return context.input_statuses.get(slot) in {"ok", "partial"}


def _decode_bounded(serialized_data: str) -> object:
    try:
        return json.loads(serialized_data)
    except json.JSONDecodeError:
        return {}


def _is_preview_collapse(bounded_prompt_data: object) -> bool:
    """True for the serializer's over-budget form, a string preview without the data."""
    return (isinstance(bounded_prompt_data, dict) and bounded_prompt_data.get("truncated") is True
            and "data_preview" in bounded_prompt_data)


def build_planning_prompt(context: ProductPlanningContext) -> PlanningPrompt:
    """Build separate trusted instructions and bounded JSON data for one request."""
    request_usable = _usable(context, "planning_request")
    trend_usable = _usable(context, "trend_result") and request_usable
    inventory_usable = _usable(context, "inventory_product_result")
    request = context.request
    # The model sees only the primary trend chosen by this service's rule (the same trend the
    # rule-based Draft uses); it does not choose among trends. None: no usable trend.
    primary = select_primary_trend(context)
    trend_candidates = []
    if primary is not None:
        trend_candidates = [{
            "name": primary.name,
            "qualification": primary.qualification,
            "season": primary.season,
            "market": list(primary.market),
            "channel": list(primary.channel),
            "category": primary.category,
            "description": primary.description,
            "evidence_ids": list(primary.evidence_ids),
            "description_evidence_ids": list(primary.description_evidence_ids),
            "attributes": [
                {"name": attr.name, "value": attr.value, "origin": attr.origin,
                 "evidence_ids": list(attr.evidence_ids)}
                for attr in primary.attributes
            ],
        }]
    products = []
    if inventory_usable:
        products = [{
            "style_id": item.style_id,
            "category": item.category,
            "season": item.season,
            "quantity": item.quantity,
            "unit": item.unit,
            "inventory_definition": item.inventory_definition,
            "as_of": item.as_of,
            "evidence_ids": list(item.evidence_ids),
            "attributes": [
                {"name": attr.name, "value": attr.value, "origin": attr.origin,
                 "evidence_ids": list(attr.evidence_ids)}
                for attr in item.attributes
            ],
        } for item in context.inventory.products]

    prompt_data = {
        "request_id": context.request_id,
        "input_statuses": dict(context.input_statuses),
        "request": ({
            "query": request.original_query,
            "season": request.season,
            "market": list(request.market),
            "channel": list(request.channel),
            "category": request.category,
            "product_role": request.product_role,
            "target_customer": request.target_customer,
            "constraints": list(request.constraints),
            "missing_fields": list(request.missing_fields),
            "requested_attributes": [
                {"name": item.name, "value": item.value, "origin": item.origin,
                 "evidence_ids": list(item.evidence_ids)}
                for item in request.requested_attributes
            ],
            "evidence_ids": list(request.result.evidence_ids),
        } if request_usable else None),
        "primary_trend": ({"name": primary.name, "selection_rule": TREND_SELECTION_RULE}
                          if primary is not None else None),
        "trend_candidates": trend_candidates,
        "trend_limitations": list(context.trends.result.limitations) if trend_usable else [],
        "inventory_products": products,
        "inventory_limitations": list(context.inventory.result.limitations) if inventory_usable else [],
        "conflicts": [{"field": item.field, "values": dict(item.values), "message": item.message}
                      for item in context.conflicts],
        "limitations": list(context.limitations),
        "questions_for_validation": list(context.questions_for_validation),
    }
    serialized_data = serialize_untrusted_prompt_data(prompt_data)
    bounded_prompt_data = _decode_bounded(serialized_data)
    reduction = None
    if _is_preview_collapse(bounded_prompt_data):
        # The preview has no Evidence IDs, so every citation would be rejected
        # after a paid call. Reduce the data deterministically instead; data
        # under the budget never reaches this branch and stays byte-identical.
        reduction = reduce_prompt_data(prompt_data, request_season=request.season if request_usable else None)
        if reduction.fits:
            serialized_data = serialize_untrusted_prompt_data(reduction.data)
            bounded_prompt_data = _decode_bounded(serialized_data)
        if not reduction.fits or _is_preview_collapse(bounded_prompt_data):
            return PlanningPrompt(PROMPT_VERSION, PLANNING_SYSTEM_PROMPT, "", frozenset(),
                                  reduction=reduction, over_budget=True)

    evidence_ids: set[str] = set()

    def collect_ids(value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"evidence_id", "evidence_ids", "description_evidence_ids"}:
                    if isinstance(child, str):
                        evidence_ids.add(child)
                    elif isinstance(child, list):
                        evidence_ids.update(item for item in child if isinstance(item, str))
                else:
                    collect_ids(child)
        elif isinstance(value, list):
            for child in value:
                collect_ids(child)

    collect_ids(bounded_prompt_data)
    allowed_ids = frozenset(evidence_ids)
    if reduction is not None:
        # Allowed IDs are what the model was shown, mapped back to real IDs.
        allowed_ids = frozenset(reduction.alias_to_real.get(item, item) for item in evidence_ids)
    user_prompt = render_prompt(
        "text_planning", "user", {"UNTRUSTED_PLANNING_INPUT_JSON": serialized_data},
    )
    return PlanningPrompt(PROMPT_VERSION, PLANNING_SYSTEM_PROMPT, user_prompt, allowed_ids, reduction=reduction)


def _parse_json_object(value: str | dict[str, Any]) -> dict[str, Any]:
    def unique_object(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = item
        return result

    def reject_constant(_value):
        raise ValueError("invalid number")

    if isinstance(value, str):
        if len(value) > MAX_MODEL_OUTPUT_CHARS:
            raise ValueError("oversized output")
        try:
            value = json.loads(value, object_pairs_hook=unique_object, parse_constant=reject_constant)
        except (json.JSONDecodeError, TypeError, ValueError):
            raise ValueError("invalid output") from None
    if not isinstance(value, dict):
        raise ValueError("invalid output")
    try:
        encoded = json.dumps(value, allow_nan=False, ensure_ascii=False)
    except (TypeError, ValueError):
        raise ValueError("invalid output") from None
    if len(encoded) > MAX_MODEL_OUTPUT_CHARS:
        raise ValueError("oversized output")
    return value


def _claim(value: object, *, path: str, allowed_ids: frozenset[str]) -> SourcedClaim:
    if not isinstance(value, dict) or set(value) != {"value", "kind", "evidence_ids"}:
        raise ValueError(f"invalid {path}")
    claim_value = value["value"]
    kind = value["kind"]
    ids = value["evidence_ids"]
    if claim_value is not None and (not isinstance(claim_value, str) or len(claim_value) > 3_000):
        raise ValueError(f"invalid {path}")
    if kind not in CLAIM_KINDS or not isinstance(ids, list) or any(not isinstance(i, str) for i in ids):
        raise ValueError(f"invalid {path}")
    if any(item not in allowed_ids for item in ids):
        raise ValueError(f"invalid {path}")
    return SourcedClaim(claim_value, kind, tuple(dict.fromkeys(ids)))


def parse_concept_output(
    value: str | dict[str, Any],
    context: ProductPlanningContext,
    allowed_evidence_ids: frozenset[str],
) -> ProductConceptDraft:
    """Validate strict model JSON and map it to the existing internal draft."""
    data = _parse_json_object(value)
    required = {
        "request_id", "opportunity", "target_customer", "product_definition", "product_profile", "attributes",
        "relation_to_own_products", "differentiation", "risks", "questions_for_validation", "limitations",
    }
    if set(data) != required or data.get("request_id") != context.request_id:
        raise ValueError("invalid output")
    opportunity = _claim(data["opportunity"], path="opportunity", allowed_ids=allowed_evidence_ids)
    target_customer = _claim(data["target_customer"], path="target_customer", allowed_ids=allowed_evidence_ids)
    product_definition = _claim(data["product_definition"], path="product_definition", allowed_ids=allowed_evidence_ids)
    profile_data = data["product_profile"]
    profile_fields = {"category", "product_type", "gender", "season", "material", "silhouette", "color", "details"}
    if not isinstance(profile_data, dict) or set(profile_data) != profile_fields:
        raise ValueError("invalid product_profile")
    parsed_profile = {
        key: _claim(profile_data[key], path=f"product_profile.{key}", allowed_ids=allowed_evidence_ids)
        for key in profile_fields - {"details"}
    }
    raw_details = profile_data["details"]
    if not isinstance(raw_details, list) or len(raw_details) > 20:
        raise ValueError("invalid product_profile.details")
    details: list[ProposedAttribute] = []
    for item in raw_details:
        if not isinstance(item, dict) or set(item) != {"name", "value", "kind", "evidence_ids"}:
            raise ValueError("invalid product_profile.details")
        name, detail_value, kind, ids = item["name"], item["value"], item["kind"], item["evidence_ids"]
        if (not isinstance(name, str) or not name.strip() or len(name) > 120
                or (detail_value is not None and (not isinstance(detail_value, str) or len(detail_value) > 1_000))
                or kind not in CLAIM_KINDS or not isinstance(ids, list)
                or any(not isinstance(eid, str) or eid not in allowed_evidence_ids for eid in ids)):
            raise ValueError("invalid product_profile.details")
        details.append(ProposedAttribute(name.strip(), detail_value, kind, tuple(dict.fromkeys(ids))))
    base_profile = base_product_profile(context)
    # The LLM must return concrete values for every orchestrator-required profile field.
    # Category and season remain exact echoes of normalized request identity.
    required_profile_fields = ("category", "product_type", "gender", "season", "material")
    for field_name in required_profile_fields:
        claim = parsed_profile[field_name]
        if claim.value is None or not claim.value.strip():
            raise ValueError(f"empty required product profile field: {field_name}")
    if (parsed_profile["category"].value != base_profile.category.value
            or parsed_profile["season"].value != base_profile.season.value):
        raise ValueError("product profile request fields mismatch")
    parsed_profile["category"] = base_profile.category
    parsed_profile["season"] = base_profile.season
    # Gender cannot be inferred from category. Keep an explicit request value;
    # otherwise only the LLM's proposal sentinel is valid.
    gender = parsed_profile["gender"]
    if gender.value not in {"women", "men", "unisex", "unknown"}:
        raise ValueError("invalid product profile gender")
    if base_profile.gender.value is not None:
        if gender.value != base_profile.gender.value:
            raise ValueError("product profile request gender mismatch")
        parsed_profile["gender"] = base_profile.gender
    elif gender.value != "unknown" or gender.kind != "proposal":
        raise ValueError("unrequested product profile gender must be unknown proposal")
    product_profile = ProductProfile(**parsed_profile, details=tuple(details))
    direct_user_values = {
        value for value in (
            context.request.original_query, context.request.season, context.request.category,
            context.request.target_customer, *context.request.market, *context.request.channel,
            *context.request.constraints,
        ) if value
    }
    for claim in (opportunity, target_customer, product_definition):
        if claim.kind == "user_requested" and claim.value not in direct_user_values:
            raise ValueError("invalid output")
    request_values = direct_user_values | {
        str(signal.value) for signal in context.request.requested_attributes if signal.value is not None
    }
    for field_name in ("product_type", "gender", "material", "silhouette", "color"):
        claim = getattr(product_profile, field_name)
        if claim.kind == "user_requested" and claim.value not in request_values:
            raise ValueError("invalid product profile provenance")

    raw_attributes = data["attributes"]
    if not isinstance(raw_attributes, list) or len(raw_attributes) > 50:
        raise ValueError("invalid output")
    attributes: list[ProposedAttribute] = []
    for item in raw_attributes:
        if not isinstance(item, dict) or set(item) != {"name", "value", "kind", "evidence_ids"}:
            raise ValueError("invalid output")
        name, attr_value, kind, ids = item["name"], item["value"], item["kind"], item["evidence_ids"]
        if not isinstance(name, str) or not name.strip() or len(name) > 120:
            raise ValueError("invalid output")
        if attr_value is not None and not isinstance(attr_value, (str, int, float, bool)):
            raise ValueError("invalid output")
        if isinstance(attr_value, float) and not math.isfinite(attr_value):
            raise ValueError("invalid output")
        if isinstance(attr_value, str) and len(attr_value) > 1_000:
            raise ValueError("invalid output")
        if kind not in CLAIM_KINDS or not isinstance(ids, list) or any(not isinstance(i, str) for i in ids):
            raise ValueError("invalid output")
        if any(item_id not in allowed_evidence_ids for item_id in ids):
            raise ValueError("invalid output")
        attributes.append(ProposedAttribute(name, attr_value, kind, tuple(dict.fromkeys(ids))))

    def claims(key: str) -> tuple[SourcedClaim, ...]:
        values = data[key]
        if not isinstance(values, list) or len(values) > 30:
            raise ValueError("invalid output")
        return tuple(_claim(item, path=key, allowed_ids=allowed_evidence_ids) for item in values)

    def text_list(key: str, max_count: int = 30) -> tuple[str, ...]:
        values = data[key]
        if not isinstance(values, list) or len(values) > max_count:
            raise ValueError("invalid output")
        if any(not isinstance(item, str) or not item.strip() or len(item) > 1_000 for item in values):
            raise ValueError("invalid output")
        return tuple(dict.fromkeys(values))

    request = context.request
    planning_usable = _usable(context, "planning_request")
    draft = ProductConceptDraft(
        request_id=context.request_id,
        season=request.season if planning_usable else None,
        category=request.category if planning_usable else None,
        market=request.market if planning_usable else (),
        channel=request.channel if planning_usable else (),
        request_constraints=request.constraints if planning_usable else (),
        field_origins=dict(request.field_origins) if planning_usable else {},
        input_statuses=dict(context.input_statuses),
        input_conflicts=context.conflicts,
        evidence_ids=tuple(sorted(allowed_evidence_ids)),
        limitations=tuple(dict.fromkeys((*context.limitations, *text_list("limitations")))),
        opportunity=opportunity,
        target_customer=target_customer,
        product_definition=product_definition,
        product_profile=product_profile,
        attributes=tuple(attributes),
        relation_to_own_products=claims("relation_to_own_products"),
        differentiation=claims("differentiation"),
        risks=claims("risks"),
        questions_for_validation=tuple(dict.fromkeys((
            *context.questions_for_validation,
            *text_list("questions_for_validation"),
        ))),
        # The rule's record, never the model's: the output has no trend field to choose with.
        trend_basis=build_trend_basis(context),
    )
    issues = validate_concept_draft(context, draft)
    if issues:
        raise ConceptOutputValidationError(issues[0].code)
    return draft


@dataclass
class PromptedConceptGenerator:
    """Opt-in structured generation adapter; deterministic fallback by default."""

    provider: StructuredTextProvider | None = None
    enabled: bool = False
    fallback: ConceptGenerator | None = None
    generation_status: str = field(default="not_requested", init=False)
    generation_error_code: str | None = field(default=None, init=False)
    llm_empty_fields: tuple[str, ...] = field(default=(), init=False)
    prompt_reduction: dict[str, object] | None = field(default=None, init=False)

    @property
    def generation_metadata(self) -> dict[str, object]:
        attempted = self.enabled
        metadata = {
            "engine": "structured_text" if self.generation_status == "generated" else "rule_based",
            "status": self.generation_status,
            "prompt_version": PROMPT_VERSION if attempted else None,
            "model": getattr(self.provider, "model_name", None) if attempted else None,
            "error_code": self.generation_error_code,
            "llm_empty_fields": list(self.llm_empty_fields),
        }
        if self.prompt_reduction is not None:
            # Only runs whose LLM input had to be reduced carry this key, so the
            # metadata of every run under the budget stays exactly as before.
            metadata["prompt_reduction"] = copy.deepcopy(self.prompt_reduction)
        return metadata

    def _rule_fallback(
        self,
        context: ProductPlanningContext,
        fallback: ConceptGenerator,
        *,
        error_code: str,
        limitation: str,
        message: str,
    ) -> tuple[ProductConceptDraft, tuple[ValidationIssue, ...]]:
        self.generation_status = "fallback"
        self.generation_error_code = error_code
        self.llm_empty_fields = ()
        safe_draft, base_issues = fallback.generate(context)
        safe_draft = replace(
            safe_draft,
            limitations=tuple(dict.fromkeys((*safe_draft.limitations, limitation))),
        )
        issue = ValidationIssue(path="generation", code="TEXT_GENERATION_FALLBACK", message=message)
        return safe_draft, (*base_issues, issue)

    def generate(self, context: ProductPlanningContext) -> tuple[ProductConceptDraft, tuple[ValidationIssue, ...]]:
        fallback = self.fallback or RuleBasedConceptGenerator()
        self.prompt_reduction = None
        if not self.enabled:
            self.generation_status = "disabled"
            self.generation_error_code = None
            self.llm_empty_fields = ()
            return fallback.generate(context)
        if self.provider is None:
            self.generation_status = "unavailable"
            self.generation_error_code = "TEXT_API_NOT_CONFIGURED"
            self.llm_empty_fields = ()
            safe_draft, base_issues = fallback.generate(context)
            safe_draft = replace(
                safe_draft,
                limitations=tuple(dict.fromkeys((
                    *safe_draft.limitations,
                    "텍스트 생성 기능은 요청되었지만 승인된 모델 제공자가 없어 규칙 기반 초안을 사용했습니다.",
                ))),
            )
            issue = ValidationIssue(
                path="generation",
                code="TEXT_GENERATION_UNAVAILABLE",
                message="승인된 텍스트 생성 제공자가 구성되지 않아 규칙 기반 초안을 반환했습니다.",
            )
            return safe_draft, (*base_issues, issue)
        prompt = build_planning_prompt(context)
        reduction = prompt.reduction
        if reduction is not None:
            self.prompt_reduction = reduction.metadata(allowed_evidence_ids=len(prompt.allowed_evidence_ids))
        if prompt.over_budget:
            # No provider call: the only sendable form would be the ID-less preview.
            return self._rule_fallback(
                context,
                fallback,
                error_code="TEXT_INPUT_OVER_BUDGET",
                limitation=INPUT_OVER_BUDGET_LIMITATION,
                message="텍스트 생성 입력이 한도를 넘어 LLM을 호출하지 않고 규칙 기반 초안으로 대체했습니다.",
            )
        try:
            raw = self.provider.generate_json(
                system_prompt=prompt.system_prompt,
                user_prompt=prompt.user_prompt,
            )
            if reduction is not None:
                # The model saw the reduced data: map aliases back to real IDs and
                # drop copied grouping notes before the usual strict validation.
                raw = restore_model_text(
                    resolve_output_aliases(_parse_json_object(raw), reduction.alias_to_real),
                    reduction.alias_to_real,
                )
            draft = parse_concept_output(raw, context, prompt.allowed_evidence_ids)
            self.llm_empty_fields = _empty_poster_fields(draft)
            rule_draft, _ = fallback.generate(context)
            draft = _fill_empty_non_differentiation_fields(draft, rule_draft)
            draft = _apply_first_evidence_colour(draft, rule_draft, context)
            trimmed = reduction.trimmed_limitation() if reduction is not None else None
            if trimmed is not None:
                draft = replace(draft, limitations=tuple(dict.fromkeys((*draft.limitations, trimmed))))
            self.generation_status = "generated"
            self.generation_error_code = None
            return draft, ()
        except Exception as exc:
            return self._rule_fallback(
                context,
                fallback,
                error_code=getattr(exc, "code", "TEXT_OUTPUT_INVALID"),
                limitation="텍스트 생성 응답을 검증하지 못해 결정적 규칙 기반 초안을 사용했습니다.",
                message="텍스트 생성 결과를 검증하지 못해 규칙 기반 초안으로 대체했습니다.",
            )


def _empty_poster_fields(draft: ProductConceptDraft) -> tuple[str, ...]:
    """Return poster-facing fields that the successful LLM response left empty."""
    empty: list[str] = []

    def claim_empty(claim: SourcedClaim) -> bool:
        return claim.value is None or not str(claim.value).strip()

    for name in ("opportunity", "product_definition"):
        if claim_empty(getattr(draft, name)):
            empty.append(name)
    # 필수 필드는 비어 있으면 parse_concept_output이 먼저 거부한다. 규칙 Draft로 채운 필드가
    # 메타데이터에 드러나도록 프로필 7개 필드를 모두 확인한다.
    for name in ("category", "product_type", "gender", "season", "material", "silhouette", "color"):
        if claim_empty(getattr(draft.product_profile, name)):
            empty.append(f"product_profile.{name}")
    if not draft.product_profile.details:
        empty.append("product_profile.details")
    if not draft.relation_to_own_products:
        empty.append("relation_to_own_products")
    if not draft.differentiation:
        empty.append("differentiation")
    return tuple(empty)


_COLOUR_NAMES = frozenset({"color", "colour", "color_group", "colour_group", "색상", "컬러"})


def _apply_first_evidence_colour(
    draft: ProductConceptDraft,
    rule_draft: ProductConceptDraft,
    context: ProductPlanningContext,
) -> ProductConceptDraft:
    """Apply the colour rule on the model path too.

    When the primary trend has two or more evidence-linked colours and the request fixes none,
    the profile colour is the rule's first evidence colour, whatever colour the model chose.
    """
    basis = rule_draft.trend_basis
    if basis is None or base_product_profile(context).color.value is not None:
        return draft
    colours = {
        item.value.strip() for item in basis.design_attributes
        if item.name.strip().casefold() in _COLOUR_NAMES and isinstance(item.value, str) and item.value.strip()
    }
    rule_colour = rule_draft.product_profile.color
    if len(colours) < 2 or rule_colour.value is None or draft.product_profile.color == rule_colour:
        return draft
    attributes = draft.attributes
    # Keep the Draft consistent (validate_concept_draft: the profile colour is one of the colour attributes).
    if not any(item.name.strip().casefold() in _COLOUR_NAMES and str(item.value).strip() == rule_colour.value
               for item in attributes):
        attributes = (*attributes, ProposedAttribute("color", rule_colour.value, rule_colour.kind,
                                                     rule_colour.evidence_ids))
    return replace(draft, attributes=attributes,
                   product_profile=replace(draft.product_profile, color=rule_colour))


def _fill_empty_non_differentiation_fields(
    draft: ProductConceptDraft,
    fallback: ProductConceptDraft,
) -> ProductConceptDraft:
    """Use rules for empty poster fields, while preserving empty differentiation."""

    def claim_or_fallback(claim: SourcedClaim, fallback_claim: SourcedClaim) -> SourcedClaim:
        return fallback_claim if claim.value is None or not str(claim.value).strip() else claim

    model_profile = draft.product_profile
    fallback_profile = fallback.product_profile
    profile = replace(
        model_profile,
        product_type=claim_or_fallback(model_profile.product_type, fallback_profile.product_type),
        material=claim_or_fallback(model_profile.material, fallback_profile.material),
        silhouette=claim_or_fallback(model_profile.silhouette, fallback_profile.silhouette),
        color=claim_or_fallback(model_profile.color, fallback_profile.color),
        details=model_profile.details or fallback_profile.details,
    )
    return replace(
        draft,
        opportunity=claim_or_fallback(draft.opportunity, fallback.opportunity),
        product_definition=claim_or_fallback(draft.product_definition, fallback.product_definition),
        product_profile=profile,
        relation_to_own_products=draft.relation_to_own_products or fallback.relation_to_own_products,
        # differentiation intentionally remains exactly as returned by LLM.
    )
