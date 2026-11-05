"""Contract-neutral normalization for New Product Planning inputs.

These types are internal domain models, not the shared wire contract. A transport
adapter should map the agreed PlanningRequest, TrendResult, and
InventoryProductResult schemas into these models after those schemas are
available and synchronized across repositories.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping, Sequence


InputStatus = Literal["ok", "partial", "no_results", "error"]
AttributeOrigin = Literal[
    "user_requested",
    "evidence_observation",
    "agent_proposal",
    "unknown",
]


class InputConsistencyError(ValueError):
    """Raised when inputs cannot safely be combined into one planning request."""


@dataclass(frozen=True)
class AgentResult:
    """Common metadata for one upstream agent result."""

    agent_id: str
    request_id: str
    schema_version: str
    status: InputStatus
    evidence_ids: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class AttributeSignal:
    """A normalized attribute value and its provenance."""

    name: str
    value: str | int | float | bool | None
    origin: AttributeOrigin
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlanningRequest:
    result: AgentResult
    season: str | None = None
    market: tuple[str, ...] = ()
    channel: tuple[str, ...] = ()
    category: str | None = None
    requested_attributes: tuple[AttributeSignal, ...] = ()
    missing_fields: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()


@dataclass(frozen=True)
class TrendCandidate:
    name: str
    qualification: str
    season: str | None = None
    market: tuple[str, ...] = ()
    channel: tuple[str, ...] = ()
    category: str | None = None
    attributes: tuple[AttributeSignal, ...] = ()
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class TrendResult:
    result: AgentResult
    candidates: tuple[TrendCandidate, ...] = ()


@dataclass(frozen=True)
class InventoryProduct:
    style_id: str | None
    sku_ids: tuple[str, ...]
    season: str | None = None
    category: str | None = None
    market: tuple[str, ...] = ()
    channel: tuple[str, ...] = ()
    attributes: tuple[AttributeSignal, ...] = ()
    quantity: int | float | None = None
    unit: str | None = None
    inventory_definition: str | None = None
    as_of: str | None = None
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class InventoryProductResult:
    result: AgentResult
    products: tuple[InventoryProduct, ...] = ()


@dataclass(frozen=True)
class PlanningInputs:
    request: PlanningRequest
    trend: TrendResult
    inventory: InventoryProductResult


@dataclass(frozen=True)
class ContextConflict:
    field: str
    values: Mapping[str, object]
    message: str


@dataclass(frozen=True)
class ProductPlanningContext:
    """Evidence-preserving context prepared for a future concept generator.

    This is deliberately not serialized as ProductConcept. The shared output
    contract and model/provider boundary still require team agreement.
    """

    request_id: str
    schema_version: str
    request: PlanningRequest
    trends: TrendResult
    inventory: InventoryProductResult
    input_statuses: Mapping[str, InputStatus]
    conflicts: tuple[ContextConflict, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    questions_for_validation: tuple[str, ...] = ()


def _unique(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def _comparable_context(inputs: PlanningInputs) -> Mapping[str, Mapping[str, object]]:
    request = inputs.request
    trends = inputs.trend.candidates
    products = inputs.inventory.products

    values: dict[str, dict[str, object]] = {
        "season": {},
        "category": {},
        "market": {},
        "channel": {},
    }
    if request.season is not None:
        values["season"]["request"] = request.season
    if request.category is not None:
        values["category"]["request"] = request.category
    if request.market:
        values["market"]["request"] = request.market
    if request.channel:
        values["channel"]["request"] = request.channel

    trend_seasons = _unique([candidate.season for candidate in trends if candidate.season])
    trend_categories = _unique(
        [candidate.category for candidate in trends if candidate.category]
    )
    trend_markets = _unique(
        [market for candidate in trends for market in candidate.market]
    )
    trend_channels = _unique(
        [channel for candidate in trends for channel in candidate.channel]
    )
    inventory_seasons = _unique([product.season for product in products if product.season])
    inventory_categories = _unique(
        [product.category for product in products if product.category]
    )
    inventory_markets = _unique(
        [market for product in products for market in product.market]
    )
    inventory_channels = _unique(
        [channel for product in products for channel in product.channel]
    )

    if trend_seasons:
        values["season"]["trend"] = trend_seasons
    if inventory_seasons:
        values["season"]["inventory"] = inventory_seasons
    if trend_categories:
        values["category"]["trend"] = trend_categories
    if inventory_categories:
        values["category"]["inventory"] = inventory_categories
    if trend_markets:
        values["market"]["trend"] = trend_markets
    if inventory_markets:
        values["market"]["inventory"] = inventory_markets
    if trend_channels:
        values["channel"]["trend"] = trend_channels
    if inventory_channels:
        values["channel"]["inventory"] = inventory_channels

    request_attributes: dict[str, set[object]] = {}
    for signal in request.requested_attributes:
        if signal.value is not None:
            request_attributes.setdefault(signal.name.strip().casefold(), set()).add(
                signal.value
            )
    trend_attributes: dict[str, set[object]] = {}
    for candidate in trends:
        for signal in candidate.attributes:
            if signal.value is not None:
                trend_attributes.setdefault(signal.name.strip().casefold(), set()).add(
                    signal.value
                )
    inventory_attributes: dict[str, set[object]] = {}
    for product in products:
        for signal in product.attributes:
            if signal.value is not None:
                inventory_attributes.setdefault(signal.name.strip().casefold(), set()).add(
                    signal.value
                )
    for name, requested_values in request_attributes.items():
        field_name = f"attribute:{name}"
        values[field_name] = {
            "request": tuple(sorted(requested_values, key=str))
        }
        if name in trend_attributes:
            values[field_name]["trend"] = tuple(sorted(trend_attributes[name], key=str))
        if name in inventory_attributes:
            values[field_name]["inventory"] = tuple(
                sorted(inventory_attributes[name], key=str)
            )
    return values


def _conflicts(inputs: PlanningInputs) -> tuple[ContextConflict, ...]:
    conflicts: list[ContextConflict] = []
    for field_name, sources in _comparable_context(inputs).items():
        normalized = {key: value for key, value in sources.items() if value not in (None, (), [])}
        if len(normalized) < 2:
            continue

        source_values = {
            source: set(value if isinstance(value, tuple) else (value,))
            for source, value in normalized.items()
        }
        source_names = tuple(source_values)
        has_disjoint_pair = any(
            source_values[left].isdisjoint(source_values[right])
            for index, left in enumerate(source_names)
            for right in source_names[index + 1 :]
        )
        if has_disjoint_pair:
            conflicts.append(
                ContextConflict(
                    field=field_name,
                    values=normalized,
                    message=(
                        f"Input {field_name} values differ; do not combine claims "
                        "that depend on this field without resolving the mismatch."
                    ),
                )
            )
    return tuple(conflicts)


def build_planning_context(inputs: PlanningInputs) -> ProductPlanningContext:
    """Validate shared request metadata and assemble an evidence-aware context.

    The function does not generate or rank product concepts, interpret inventory
    as demand, query sources, invoke an LLM, or serialize the shared output
    schema. Those are separate decisions and responsibilities.
    """

    results = (
        inputs.request.result,
        inputs.trend.result,
        inputs.inventory.result,
    )
    request_ids = {result.request_id for result in results}
    if len(request_ids) != 1 or not next(iter(request_ids), ""):
        raise InputConsistencyError("Inputs must share one non-empty request_id.")

    schema_versions = {result.schema_version for result in results}
    if len(schema_versions) != 1 or not next(iter(schema_versions), ""):
        raise InputConsistencyError(
            "Inputs must use one non-empty, compatible schema_version."
        )

    statuses: dict[str, InputStatus] = {}
    for result in results:
        if result.status not in {"ok", "partial", "no_results", "error"}:
            raise InputConsistencyError(
                f"Unsupported upstream status '{result.status}' from {result.agent_id}."
            )
        if not result.agent_id:
            raise InputConsistencyError("Each upstream result must include an agent_id.")
        if result.agent_id in statuses:
            raise InputConsistencyError(f"Duplicate upstream agent_id: {result.agent_id}")
        statuses[result.agent_id] = result.status

    evidence_ids = _unique(
        [
            *inputs.request.result.evidence_ids,
            *inputs.trend.result.evidence_ids,
            *inputs.inventory.result.evidence_ids,
            *(evidence_id for candidate in inputs.trend.candidates for evidence_id in candidate.evidence_ids),
            *(evidence_id for product in inputs.inventory.products for evidence_id in product.evidence_ids),
            *(evidence_id for attr in inputs.request.requested_attributes for evidence_id in attr.evidence_ids),
            *(evidence_id for candidate in inputs.trend.candidates for attr in candidate.attributes for evidence_id in attr.evidence_ids),
            *(evidence_id for product in inputs.inventory.products for attr in product.attributes for evidence_id in attr.evidence_ids),
        ]
    )

    limitations = _unique(
        [
            *inputs.request.result.limitations,
            *inputs.trend.result.limitations,
            *inputs.inventory.result.limitations,
            *(
                f"Upstream result from {result.agent_id} has status '{result.status}'."
                for result in results
                if result.status != "ok"
            ),
        ]
    )
    questions = _unique(
        [
            f"Confirm missing planning input: {field_name}."
            for field_name in inputs.request.missing_fields
        ]
    )
    conflicts = _conflicts(inputs)
    questions = _unique(
        [
            *questions,
            *(
                f"Resolve the {conflict.field} mismatch across input sources."
                for conflict in conflicts
            ),
        ]
    )

    return ProductPlanningContext(
        request_id=next(iter(request_ids)),
        schema_version=next(iter(schema_versions)),
        request=inputs.request,
        trends=inputs.trend,
        inventory=inputs.inventory,
        input_statuses=statuses,
        conflicts=conflicts,
        evidence_ids=evidence_ids,
        limitations=limitations,
        questions_for_validation=questions,
    )
