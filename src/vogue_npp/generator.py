"""Deterministic, contract-neutral concept draft generation.

The initial implementation uses transparent rules rather than an LLM. It
organizes supplied facts and proposes a review scaffold; it does not estimate
market demand, rank products, or make feasibility decisions.
"""

from __future__ import annotations

from .concept import (
    ClaimKind,
    ProductConceptDraft,
    ProposedAttribute,
    SourcedClaim,
    ValidationIssue,
    validate_concept_draft,
)
from .context import AttributeSignal, ProductPlanningContext


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

    for signal in context.request.requested_attributes:
        add(signal)
    for candidate in context.trends.candidates:
        for signal in candidate.attributes:
            add(signal, trend_signal=True)
    return tuple(attributes)


def _inventory_relationships(context: ProductPlanningContext) -> tuple[SourcedClaim, ...]:
    relationships: list[SourcedClaim] = []
    for product in context.inventory.products:
        if not product.style_id or not product.evidence_ids:
            continue
        value = f"관련 자사 상품 {product.style_id}가 입력 결과에 포함되어 있습니다."
        if product.as_of:
            value += f" 재고 정보 기준 시점: {product.as_of}."
        relationships.append(
            SourcedClaim(
                value=value,
                kind="evidence_observation",
                evidence_ids=product.evidence_ids,
            )
        )
    return tuple(relationships)


def _product_definition(context: ProductPlanningContext) -> SourcedClaim:
    parts = [value for value in (context.request.season, context.request.category) if value]
    prefix = " ".join(parts) if parts else "신상품"
    requested_attributes = [
        f"{signal.name.strip()}={signal.value}"
        for signal in context.request.requested_attributes
        if signal.value is not None and signal.name.strip()
    ]
    evidenced_trends = [
        candidate
        for candidate in context.trends.candidates
        if candidate.evidence_ids
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


def _validation_questions(context: ProductPlanningContext) -> tuple[str, ...]:
    questions = list(context.questions_for_validation)
    if not context.request.season:
        questions.append("기획 시즌을 확인해 주세요.")
    if not context.request.category:
        questions.append("상품 카테고리를 확인해 주세요.")
    request_values = {
        "season": context.request.season,
        "category": context.request.category,
        "market": context.request.market,
        "channel": context.request.channel,
    }
    for field_name, value in request_values.items():
        if value and context.request.field_origins.get(field_name, "unknown") == "unknown":
            questions.append(f"{field_name} 값의 출처(user/inferred)를 확인해 주세요.")
    questions.append("대상 고객과 착용 상황을 MD가 확인해 주세요.")
    if not context.trends.candidates:
        questions.append("근거가 연결된 트렌드 후보를 확인할 수 있는지 검토해 주세요.")
    if not context.inventory.products:
        questions.append("관련 자사 상품과 재고 자료의 조회 여부를 확인해 주세요.")
    if not any(product.style_id and product.evidence_ids for product in context.inventory.products):
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

    draft = ProductConceptDraft(
        request_id=context.request_id,
        season=context.request.season,
        category=context.request.category,
        market=context.request.market,
        channel=context.request.channel,
        field_origins={
            **context.request.field_origins,
            **{
                field_name: context.request.field_origins.get(field_name, "unknown")
                for field_name in ("season", "category", "market", "channel")
            },
        },
        input_statuses=context.input_statuses,
        input_conflicts=context.conflicts,
        evidence_ids=context.evidence_ids,
        limitations=context.limitations,
        opportunity=SourcedClaim(
            value="요청 조건과 입력된 트렌드·자사 상품 근거를 바탕으로 신상품 기회를 검토합니다.",
            kind="proposal",
        ),
        target_customer=SourcedClaim(
            value=None,
            kind="unknown",
        ),
        product_definition=_product_definition(context),
        attributes=_proposed_attributes(context),
        relation_to_own_products=_inventory_relationships(context),
        differentiation=(),
        risks=tuple(
            SourcedClaim(value=limitation, kind="to_validate")
            for limitation in context.limitations
        ),
        questions_for_validation=_validation_questions(context),
    )
    return draft, validate_concept_draft(context, draft)
