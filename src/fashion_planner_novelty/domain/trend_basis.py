"""The one trend a Draft is planned around.

A Draft is built around a single primary trend instead of pooling every usable
trend. The rule is deterministic and shared by the rule-based generator and the
text-LLM path; the LLM never chooses the trend. Among the usable candidates
(named, evidenced, no request-dimension mismatch) it picks the candidate with

1. the most evidence-linked design attributes, then
2. the most Evidence IDs (candidate + description + attribute evidence), then
3. the earliest input order.

No I/O, no model call.
"""

from __future__ import annotations

from .analysis import dimension_mismatches
from .concept import TrendBasis, TrendBasisAttribute
from .context import AttributeSignal, ProductPlanningContext, TrendCandidate


TREND_SELECTION_RULE = "most_evidence_linked_design_attributes"

# 시각 디자인 속성으로 보는 속성 이름의 단일 집합. 주 트렌드 선택 규칙이 쓴다.
DESIGN_ATTRIBUTE_NAMES = frozenset({
    "color", "colour", "color_group", "colour_group", "색상", "컬러",
    "pattern", "print", "패턴", "프린트", "silhouette", "shape", "실루엣",
    "material", "fabric", "소재", "원단", "fit", "핏", "디테일", "detail", "details",
    "decoration", "장식", "texture", "조직감", "length", "기장",
})


def is_design_attribute_name(name: str) -> bool:
    return name.strip().casefold() in DESIGN_ATTRIBUTE_NAMES


def _input_usable(context: ProductPlanningContext, input_name: str) -> bool:
    return context.input_statuses.get(input_name) in {"ok", "partial"}


def usable_trend_candidates(context: ProductPlanningContext) -> tuple[TrendCandidate, ...]:
    """Return named, evidenced trends that match the normalized request."""
    if not (
        _input_usable(context, "trend_result")
        and _input_usable(context, "planning_request")
    ):
        return ()
    return tuple(
        candidate
        for candidate in context.trends.candidates
        if candidate.name.strip()
        and candidate.evidence_ids
        and not dimension_mismatches(context.request, candidate)
    )


def design_attributes(candidate: TrendCandidate) -> tuple[AttributeSignal, ...]:
    """The candidate's evidence-linked design attributes, in input order (rule key 1)."""
    return tuple(
        signal for signal in candidate.attributes
        if signal.value is not None and signal.evidence_ids and is_design_attribute_name(signal.name)
    )


def trend_evidence_ids(candidate: TrendCandidate) -> tuple[str, ...]:
    """Candidate, description and attribute Evidence IDs, first occurrence order (rule key 2)."""
    return tuple(dict.fromkeys((
        *candidate.evidence_ids,
        *candidate.description_evidence_ids,
        *(evidence_id for signal in candidate.attributes for evidence_id in signal.evidence_ids),
    )))


def _primary(candidates: tuple[TrendCandidate, ...]) -> TrendCandidate | None:
    if not candidates:
        return None
    # max() returns the first of several maximal items, so ties go to the earliest input.
    return max(candidates, key=lambda candidate: (
        len(design_attributes(candidate)), len(trend_evidence_ids(candidate)),
    ))


def select_primary_trend(context: ProductPlanningContext) -> TrendCandidate | None:
    """Return the primary trend of this request, or None when no usable trend exists."""
    return _primary(usable_trend_candidates(context))


def build_trend_basis(context: ProductPlanningContext) -> TrendBasis | None:
    """Return the Draft's ``trend_basis`` record, or None when no usable trend exists."""
    candidates = usable_trend_candidates(context)
    primary = _primary(candidates)
    if primary is None:
        return None
    return TrendBasis(
        source_style_id=primary.source_style_id,
        name=primary.name,
        selection_rule=TREND_SELECTION_RULE,
        evidence_ids=trend_evidence_ids(primary),
        design_attributes=tuple(
            TrendBasisAttribute(signal.name.strip(), signal.value, signal.evidence_ids)
            for signal in design_attributes(primary)
        ),
        candidates_considered=len(candidates),
    )
