"""Deterministic, contract-neutral concept draft generation.

The initial implementation uses transparent rules rather than an LLM. It
organizes supplied facts and proposes a review scaffold; it does not estimate
market demand, rank products, or make feasibility decisions.
"""

from __future__ import annotations

from typing import Protocol

from .concept import (
    ClaimKind,
    ProductConceptDraft,
    ProposedAttribute,
    SourcedClaim,
    ValidationIssue,
    validate_concept_draft,
)
from .context import AttributeSignal, ProductPlanningContext
from .analysis import analyze_opportunities, dimension_mismatches


class ConceptGenerator(Protocol):
    """Plug-in boundary for deterministic or later evidence-grounded LLM generation."""

    def generate(
        self,
        context: ProductPlanningContext,
    ) -> tuple[ProductConceptDraft, tuple[ValidationIssue, ...]]: ...


def _input_usable(context: ProductPlanningContext, input_name: str) -> bool:
    return context.input_statuses.get(input_name) in {"ok", "partial"}


def _attribute_kind(signal: AttributeSignal) -> ClaimKind:
    if signal.origin == "user_requested":
        return "user_requested"
    if signal.origin == "evidence_observation" and signal.evidence_ids:
        return "evidence_observation"
    if signal.origin == "agent_proposal":
        return "proposal"
    if signal.value is None:
        return "unknown"
    return "to_validate"


def _proposed_attributes(context: ProductPlanningContext) -> tuple[ProposedAttribute, ...]:
    attributes: list[ProposedAttribute] = []
    positions: dict[tuple[str, str], int] = {}

    def add(signal: AttributeSignal, *, trend_signal: bool = False) -> None:
        if signal.value is None:
            return
        kind = _attribute_kind(signal)
        if trend_signal:
            kind = "evidence_observation" if signal.evidence_ids else "to_validate"
        attribute = ProposedAttribute(
            name=signal.name.strip(),
            value=signal.value,
            kind=kind,
            evidence_ids=signal.evidence_ids,
        )
        key = (attribute.name.casefold(), str(attribute.value))
        existing_index = positions.get(key)
        if existing_index is None:
            positions[key] = len(attributes)
            attributes.append(attribute)
            return

        existing = attributes[existing_index]
        evidence_ids = tuple(dict.fromkeys((*existing.evidence_ids, *attribute.evidence_ids)))
        # Preserve the strongest explicit provenance when the same value is
        # present in both the user request and an upstream trend result.
        priority = {
            "user_requested": 4,
            "evidence_observation": 3,
            "proposal": 2,
            "to_validate": 1,
            "unknown": 0,
            "interpretation": 0,
            "hypothesis": 0,
        }
        selected = attribute if priority[attribute.kind] > priority[existing.kind] else existing
        attributes[existing_index] = ProposedAttribute(
            name=selected.name,
            value=selected.value,
            kind=selected.kind,
            evidence_ids=evidence_ids,
        )

    if _input_usable(context, "planning_request"):
        for signal in context.request.requested_attributes:
            add(signal)
    candidates = (
        context.trends.candidates
        if _input_usable(context, "trend_result")
        and _input_usable(context, "planning_request")
        else ()
    )
    for candidate in candidates:
        if dimension_mismatches(context.request, candidate):
            continue
        for signal in candidate.attributes:
            requested_values = {
                str(requested.value).strip().casefold()
                for requested in context.request.requested_attributes
                if requested.value is not None
                and requested.name.strip().casefold() == signal.name.strip().casefold()
                and requested.origin == "user_requested"
            }
            if requested_values and str(signal.value).strip().casefold() not in requested_values:
                continue
            add(signal, trend_signal=True)
    return tuple(attributes)


def _inventory_relationships(context: ProductPlanningContext) -> tuple[SourcedClaim, ...]:
    relationships: list[SourcedClaim] = []
    products = (
        context.inventory.products
        if _input_usable(context, "inventory_product_result")
        else ()
    )
    for product in products:
        if not product.style_id or not product.style_id.strip() or not product.evidence_ids:
            continue
        style_id = product.style_id.strip()
        value = f"자사 상품 {style_id}가 재고 결과에 포함되어 있습니다."
        if product.quantity is not None:
            value += (
                f" 재고 스냅샷: {product.quantity} {product.unit or '(단위 미상)'}"
                f"; 정의: {product.inventory_definition or '미확인'}"
            )
        if product.as_of:
            value += f"; 기준 시점: {product.as_of}"
        if product.quantity is not None:
            value += ". 이 값은 조회 시점의 재고이며 수요나 판매 추세를 뜻하지 않습니다."
        else:
            value += "."
        relationships.append(
            SourcedClaim(
                value=value,
                kind="evidence_observation",
                evidence_ids=product.evidence_ids,
            )
        )
        for attribute in product.attributes:
            if attribute.value is None or not attribute.evidence_ids:
                continue
            relationships.append(
                SourcedClaim(
                    value=(
                        f"자사 상품 {style_id}의 확인된 속성: "
                        f"{attribute.name}={attribute.value}."
                    ),
                    kind="evidence_observation",
                    evidence_ids=attribute.evidence_ids,
                )
            )
    return tuple(relationships)


def _product_definition(context: ProductPlanningContext) -> SourcedClaim:
    request_usable = _input_usable(context, "planning_request")
    parts = [
        value
        for value in (
            context.request.season if request_usable else None,
            context.request.category if request_usable else None,
        )
        if value
    ]
    prefix = " ".join(parts) if parts else "신상품"
    requested_attributes = [
        f"{signal.name.strip()}={signal.value}"
        for signal in (context.request.requested_attributes if request_usable else ())
        if signal.value is not None
        and signal.name.strip()
        and signal.origin == "user_requested"
    ]
    evidenced_trends = [
        candidate
        for candidate in (
            context.trends.candidates
            if request_usable and _input_usable(context, "trend_result")
            else ()
        )
        if candidate.evidence_ids
        and candidate.name.strip()
        and not dimension_mismatches(context.request, candidate)
    ]
    fragments = [f"{prefix} 콘셉트 검토 초안"]
    if requested_attributes:
        fragments.append("요청 속성: " + ", ".join(dict.fromkeys(requested_attributes)))
    if evidenced_trends:
        fragments.append(
            "참고할 근거 연결 트렌드 후보: "
            + ", ".join(dict.fromkeys(candidate.name for candidate in evidenced_trends))
        )
    return SourcedClaim(
        value=". ".join(fragments) + ".",
        kind="proposal",
        evidence_ids=tuple(
            dict.fromkeys(
                evidence_id
                for candidate in evidenced_trends
                for evidence_id in candidate.evidence_ids
            )
        ),
    )


def _validation_questions(
    context: ProductPlanningContext,
    analysis_questions: tuple[str, ...] = (),
) -> tuple[str, ...]:
    questions = [*context.questions_for_validation, *analysis_questions]
    for input_name, status in context.input_statuses.items():
        if status in {"error", "no_results"}:
            questions.append(
                f"{input_name} 상태가 '{status}'이므로 해당 입력을 사용하지 않았습니다. 재조회 또는 조건 확인이 필요합니다."
            )
    if not context.request.season:
        questions.append("기획 시즌을 확인해 주세요.")
    if not context.request.category:
        questions.append("상품 카테고리를 확인해 주세요.")
    request_usable = _input_usable(context, "planning_request")
    request_values = {
        "season": context.request.season if request_usable else None,
        "category": context.request.category if request_usable else None,
        "market": context.request.market if request_usable else (),
        "channel": context.request.channel if request_usable else (),
    }
    for field_name, value in request_values.items():
        if value and context.request.field_origins.get(field_name, "unknown") == "unknown":
            questions.append(f"{field_name} 값의 출처(user/inferred)를 확인해 주세요.")
    if any(
        signal.value is not None and signal.origin == "unknown"
        for signal in (context.request.requested_attributes if request_usable else ())
    ):
        questions.append("출처가 확인되지 않은 요청 속성이 있어 MD 확인이 필요합니다.")
    questions.append("대상 고객과 착용 상황을 MD가 확인해 주세요.")
    questions.append("기존 자사 상품과의 차별화 방향은 상품기획 검토가 필요합니다.")
    if not _input_usable(context, "trend_result") or not context.trends.candidates:
        questions.append("근거가 연결된 트렌드 후보를 확인할 수 있는지 검토해 주세요.")
    elif not any(
        candidate.evidence_ids and candidate.name.strip()
        for candidate in (
            context.trends.candidates
            if _input_usable(context, "trend_result") and request_usable
            else ()
        )
    ):
        questions.append("트렌드 후보를 뒷받침하는 Evidence 참조를 확인해 주세요.")
    if not _input_usable(context, "inventory_product_result") or not context.inventory.products:
        questions.append("관련 자사 상품과 재고 자료의 조회 여부를 확인해 주세요.")
    if not any(
        product.style_id and product.evidence_ids
        for product in (
            context.inventory.products
            if _input_usable(context, "inventory_product_result")
            else ()
        )
    ):
        questions.append("자사 상품 관계를 뒷받침할 Evidence 연결을 확인해 주세요.")
    return tuple(dict.fromkeys(question for question in questions if question.strip()))


def generate_concept_draft(
    context: ProductPlanningContext,
) -> tuple[ProductConceptDraft, tuple[ValidationIssue, ...]]:
    """Build a review-only concept scaffold from already normalized inputs.

    The function deliberately does not infer customer demand, product
    differentiation, price, cost, production feasibility, or sales potential.
    The returned issues must be resolved or presented as limitations before a
    future wire adapter emits a shared ``ProductConcept`` response.
    """

    analysis = analyze_opportunities(context)
    analysis_evidence_ids = tuple(
        dict.fromkeys(
            evidence_id
            for finding in analysis.findings
            for evidence_id in finding.statement.evidence_ids
        )
    )
    opportunity_summary = (
        f"Evidence가 연결된 트렌드·자사 상품 속성 비교 {len(analysis.findings)}건을 "
        "검토 대상으로 정리했습니다. 기획 기회 해석은 MD 검토가 필요합니다."
        if analysis.findings
        else "비교 가능한 입력 근거가 부족해 구체적인 기획 기회는 판단하지 않았습니다."
    )
    draft = ProductConceptDraft(
        request_id=context.request_id,
        season=context.request.season if _input_usable(context, "planning_request") else None,
        category=context.request.category if _input_usable(context, "planning_request") else None,
        market=context.request.market if _input_usable(context, "planning_request") else (),
        channel=context.request.channel if _input_usable(context, "planning_request") else (),
        request_constraints=(
            context.request.constraints
            if _input_usable(context, "planning_request")
            else ()
        ),
        field_origins={
            **(
                context.request.field_origins
                if _input_usable(context, "planning_request")
                else {}
            ),
            **{
                field_name: (
                    context.request.field_origins.get(field_name, "unknown")
                    if _input_usable(context, "planning_request")
                    else "unknown"
                )
                for field_name in ("season", "category", "market", "channel")
            },
        },
        input_statuses=context.input_statuses,
        input_conflicts=context.conflicts,
        evidence_ids=context.evidence_ids,
        limitations=tuple(dict.fromkeys((*context.limitations, *analysis.limitations))),
        opportunity=SourcedClaim(
            value=opportunity_summary,
            kind="proposal" if analysis.findings else "to_validate",
            evidence_ids=analysis_evidence_ids,
        ),
        target_customer=SourcedClaim(
            value=None,
            kind="unknown",
        ),
        product_definition=_product_definition(context),
        attributes=_proposed_attributes(context),
        opportunity_findings=analysis.findings,
        relation_to_own_products=_inventory_relationships(context),
        differentiation=(),
        risks=tuple(
            SourcedClaim(value=limitation, kind="to_validate")
            for limitation in tuple(dict.fromkeys((*context.limitations, *analysis.limitations)))
        ),
        questions_for_validation=_validation_questions(context, analysis.questions),
    )
    return draft, validate_concept_draft(context, draft)


class RuleBasedConceptGenerator:
    """Current provider-free implementation of the concept generation port."""

    def generate(
        self,
        context: ProductPlanningContext,
    ) -> tuple[ProductConceptDraft, tuple[ValidationIssue, ...]]:
        return generate_concept_draft(context)
