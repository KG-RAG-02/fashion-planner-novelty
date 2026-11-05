"""Conservative, evidence-only comparisons for internal concept planning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .concept import OpportunityFinding, SourcedClaim
from .context import (
    AttributeSignal,
    InventoryProduct,
    PlanningRequest,
    ProductPlanningContext,
    SalesObservation,
    TrendCandidate,
)


@dataclass(frozen=True)
class OpportunityAnalysis:
    """Internal comparison results; not a market-gap or demand assessment."""

    findings: tuple[OpportunityFinding, ...] = ()
    questions: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


def _key(value: object) -> str:
    return str(value).strip().casefold()


def dimension_mismatches(
    request: PlanningRequest,
    item: TrendCandidate | InventoryProduct,
) -> tuple[str, ...]:
    """Return populated request dimensions that contradict one input item."""

    mismatches: list[str] = []
    for field_name in ("season", "category"):
        requested = getattr(request, field_name)
        observed = getattr(item, field_name)
        if requested and observed and _key(requested) != _key(observed):
            mismatches.append(field_name)

    for field_name in ("market", "channel"):
        requested_values = {_key(value) for value in getattr(request, field_name)}
        observed_values = {_key(value) for value in getattr(item, field_name)}
        if requested_values and observed_values and requested_values.isdisjoint(observed_values):
            mismatches.append(field_name)
    return tuple(mismatches)


def _evidence_attributes(signals: Iterable[AttributeSignal]) -> tuple[AttributeSignal, ...]:
    return tuple(
        signal
        for signal in signals
        if signal.name.strip() and signal.value is not None and signal.evidence_ids
    )


def _requested_values(request: PlanningRequest) -> dict[str, set[str]]:
    values: dict[str, set[str]] = {}
    for signal in request.requested_attributes:
        if signal.name.strip() and signal.value is not None and signal.origin == "user_requested":
            values.setdefault(_key(signal.name), set()).add(_key(signal.value))
    return values


def analyze_opportunities(context: ProductPlanningContext) -> OpportunityAnalysis:
    """Compare trend and own-catalog evidence without inferring a market gap.

    Only evidence-backed values on dimension-compatible inputs are compared.
    Missing catalog attributes are not treated as absent products because the
    shared contract has not defined query coverage or catalog completeness.
    """

    findings: list[OpportunityFinding] = []
    questions: list[str] = []
    limitations: list[str] = []
    trend_status = context.input_statuses.get("trend_result")
    sales_status = context.input_statuses.get("sales_analysis_result")
    inventory_status = context.input_statuses.get("inventory_product_result")
    request_status = context.input_statuses.get("planning_request")

    if request_status not in {"ok", "partial"}:
        limitations.append(
            f"PlanningRequest input status is '{request_status}'; request-dependent comparisons were not analyzed."
        )
    if trend_status in {"error", "no_results"}:
        limitations.append(f"TrendResult input status is '{trend_status}'; no trend claims were analyzed.")
    if sales_status in {"error", "no_results"}:
        limitations.append(f"SalesAnalysisResult status is '{sales_status}'; no sales observations were analyzed.")
    if inventory_status in {"error", "no_results"}:
        limitations.append(
            f"InventoryProductResult input status is '{inventory_status}'; "
            "no own-catalog comparisons were analyzed."
        )

    request_usable = request_status in {"ok", "partial"}
    sales_findings: list[OpportunityFinding] = []
    eligible_sales: list[SalesObservation] = []
    if request_usable and sales_status in {"ok", "partial"}:
        for observation in context.sales.observations:
            if not context.request.category or not observation.category:
                questions.append(
                    "판매 집계의 상품 분류와 요청 카테고리 매핑을 확인할 수 없어 해당 판매 행을 콘셉트 근거에 사용하지 않았습니다."
                )
                continue
            if _key(context.request.category) != _key(observation.category):
                continue
            if observation.season and context.request.season and _key(observation.season) != _key(context.request.season):
                questions.append("판매 관찰의 시즌이 요청 시즌과 달라 해당 관찰을 기획 근거에서 제외했습니다.")
                continue
            if observation.purchase_rows < 0 or not observation.evidence_ids:
                questions.append("유효한 구매 행 수 또는 Evidence가 없는 판매 관찰은 사용하지 않았습니다.")
                continue
            eligible_sales.append(observation)
            product_label = (
                f"상품 코드 {observation.product_code}"
                if observation.product_code
                else (observation.product_group or observation.category)
            )
            statement = (
                f"{context.sales.dataset_label}에서 {observation.period_start}~{observation.period_end} 기간에 "
                f"{product_label}의 구매 기록 {observation.purchase_rows:,} {observation.unit}가 관측됐습니다. "
                "이는 해당 자료 기간의 관찰이며 미래 수요나 고객 선호를 뜻하지 않습니다."
            )
            sales_findings.append(
                OpportunityFinding(
                    statement=SourcedClaim(
                        value=statement,
                        kind="evidence_observation",
                        evidence_ids=observation.evidence_ids,
                    ),
                    style_id=observation.product_code,
                    attribute_name="purchase_rows",
                    limitations=(
                        f"판매 출처 {observation.source_id}; 기준 기간 {observation.period_start}–{observation.period_end}.",
                        "과거 구매 기록은 미래 수요나 인과적 고객 니즈를 입증하지 않습니다.",
                    ),
                )
            )
    if not sales_findings:
        limitations.append(
            "요청 카테고리와 매핑된 유효 판매 관찰이 없어 판매 데이터 우선 분석을 수행할 수 없습니다."
        )
        questions.append("판매 데이터의 상품 분류 매핑과 적용 가능한 관측 기간을 확인해 주세요.")
    candidates = (
        context.trends.candidates
        if request_usable and trend_status in {"ok", "partial"}
        else ()
    )
    products = (
        context.inventory.products
        if request_usable
        and context.inventory is not None
        and inventory_status in {"ok", "partial"}
        else ()
    )
    findings.extend(sales_findings)
    eligible_candidates: list[TrendCandidate] = []
    eligible_products: list[InventoryProduct] = []

    for candidate in candidates:
        mismatches = dimension_mismatches(context.request, candidate)
        if mismatches:
            questions.append(
                f"트렌드 후보 '{candidate.name or '(이름 없음)'}'의 "
                f"{', '.join(mismatches)}가 요청 조건과 달라 기획 근거로 사용하지 않았습니다."
            )
            continue
        if not candidate.name.strip() or not candidate.evidence_ids:
            questions.append("이름 또는 Evidence가 부족한 트렌드 후보는 비교에서 제외했습니다.")
            continue
        eligible_candidates.append(candidate)

    for product in products:
        mismatches = dimension_mismatches(context.request, product)
        if mismatches:
            questions.append(
                f"자사 상품 '{product.style_id or '(Style ID 없음)'}'의 "
                f"{', '.join(mismatches)}가 요청 조건과 달라 비교에서 제외했습니다."
            )
            continue
        if not product.style_id or not product.style_id.strip() or not product.evidence_ids:
            questions.append("Style ID 또는 Evidence가 부족한 자사 상품은 비교에서 제외했습니다.")
            continue
        eligible_products.append(product)

    # Sales is the primary signal; add its directly evidenced attribute
    # relationships with trend inputs before the lower-priority own-stock view.
    for observation in eligible_sales:
        for candidate in eligible_candidates:
            for sales_attribute in _evidence_attributes(observation.attributes):
                for trend_attribute in _evidence_attributes(candidate.attributes):
                    if _key(sales_attribute.name) != _key(trend_attribute.name):
                        continue
                    same_value = _key(sales_attribute.value) == _key(trend_attribute.value)
                    relation = "같은 값" if same_value else "서로 다른 값"
                    statement = (
                        f"판매 관찰 상품 {observation.product_code or observation.product_group}의 "
                        f"{sales_attribute.name}={sales_attribute.value}와 트렌드 후보 "
                        f"'{candidate.name}'의 {trend_attribute.name}={trend_attribute.value}가 {relation}으로 확인됩니다. "
                        f"판매 기록은 {observation.period_start}~{observation.period_end} 기간의 "
                        f"{observation.purchase_rows:,} {observation.unit}입니다."
                    )
                    relation_questions = [
                        "이 판매·트렌드 관계는 관찰 수준이며 인과나 미래 수요를 뜻하지 않습니다.",
                        "이 관계를 신상품 콘셉트에 반영할지 MD 검토가 필요합니다.",
                    ]
                    findings.append(
                        OpportunityFinding(
                            statement=SourcedClaim(
                                value=statement,
                                kind="evidence_observation",
                                evidence_ids=tuple(dict.fromkeys((
                                    *observation.evidence_ids,
                                    *sales_attribute.evidence_ids,
                                    *trend_attribute.evidence_ids,
                                ))),
                            ),
                            trend_name=candidate.name,
                            style_id=observation.product_code,
                            attribute_name=sales_attribute.name,
                            questions=tuple(relation_questions),
                            limitations=(
                                "판매 집계는 과거 관찰이며 트렌드가 판매를 유발했다는 증거가 아닙니다.",
                            ),
                        )
                    )
                    questions.extend(relation_questions)

    requested_values = _requested_values(context.request)
    compared = 0
    for candidate in eligible_candidates:
        trend_attributes = _evidence_attributes(candidate.attributes)
        for product in eligible_products:
            for trend_attribute in trend_attributes:
                for own_attribute in _evidence_attributes(product.attributes):
                    if _key(trend_attribute.name) != _key(own_attribute.name):
                        continue
                    compared += 1
                    trend_value = _key(trend_attribute.value)
                    own_value = _key(own_attribute.value)
                    if trend_value == own_value:
                        statement = (
                            f"근거가 연결된 트렌드 후보 '{candidate.name}'와 "
                            f"자사 상품 {product.style_id}에서 "
                            f"{trend_attribute.name} 값 '{trend_attribute.value}'가 모두 관찰됩니다."
                        )
                    else:
                        statement = (
                            f"근거가 연결된 트렌드 후보 '{candidate.name}'의 "
                            f"{trend_attribute.name} 값 '{trend_attribute.value}'와 "
                            f"자사 상품 {product.style_id}의 확인 값 "
                            f"'{own_attribute.value}'가 다릅니다."
                        )
                    comparison_questions = [
                        "이 속성 관계가 신규 상품 기회인지 MD가 검토해야 합니다."
                    ]
                    requested = requested_values.get(_key(trend_attribute.name), set())
                    if requested and trend_value not in requested:
                        comparison_questions.append(
                            f"트렌드 속성 값이 사용자 요청과 다르므로 '{trend_attribute.name}' 조건을 확인해야 합니다."
                        )
                    questions.extend(comparison_questions)
                    findings.append(
                        OpportunityFinding(
                            statement=SourcedClaim(
                                value=statement,
                                kind="evidence_observation",
                                evidence_ids=tuple(
                                    dict.fromkeys(
                                        (*trend_attribute.evidence_ids, *own_attribute.evidence_ids)
                                    )
                                ),
                            ),
                            trend_name=candidate.name,
                            style_id=product.style_id,
                            attribute_name=trend_attribute.name,
                            questions=tuple(comparison_questions),
                            limitations=(
                                "속성 비교는 전달된 자료의 관찰이며 고객 수요나 상품 차별성의 증거가 아닙니다.",
                            ),
                        )
                    )

    if compared == 0:
        questions.append(
            "비교 가능한 트렌드·자사 상품 속성 근거가 없어 기획 기회나 상품 공백을 판단하지 않았습니다."
        )
        limitations.append(
            "상품 카탈로그 범위와 속성 완전성이 계약에 정의되지 않아, 자료에 없는 속성을 실제 상품 부재로 해석할 수 없습니다."
        )

    unique_questions = tuple(dict.fromkeys(question for question in questions if question.strip()))
    unique_limitations = tuple(dict.fromkeys(limitation for limitation in limitations if limitation.strip()))
    return OpportunityAnalysis(
        findings=tuple(findings),
        questions=unique_questions,
        limitations=unique_limitations,
    )
