"""Contract-neutral normalization for New Product Planning inputs.

These types are internal domain models, not the shared wire contract. A transport
adapter should map the agreed PlanningRequest, TrendResult, and
InventoryProductResult schemas into these models after those schemas are
available and synchronized across repositories. Local H&M sales observations
are deterministically adapted from the processed dataset.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Mapping, Sequence

if TYPE_CHECKING:
    from .styling import StylingRelationship


InputStatus = Literal["ok", "partial", "no_results", "error"]
ContextInputStatus = InputStatus | Literal["not_provided"]
ContextOrigin = Literal["user", "inferred", "unknown"]
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
    original_query: str | None = None
    season: str | None = None
    market: tuple[str, ...] = ()
    channel: tuple[str, ...] = ()
    category: str | None = None
    product_role: str | None = None
    requested_attributes: tuple[AttributeSignal, ...] = ()
    missing_fields: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    field_origins: Mapping[str, ContextOrigin] = field(default_factory=dict)


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
class SalesObservation:
    """A deterministic, period-bounded sales aggregate with normalized category."""

    category: str | None
    purchase_rows: int
    period_start: str
    period_end: str
    source_id: str
    evidence_ids: tuple[str, ...]
    product_code: str | None = None
    product_group: str | None = None
    season: str | None = None
    attributes: tuple[AttributeSignal, ...] = ()
    unit: str = "purchase_rows"
    source_channel_code: str | None = None


@dataclass(frozen=True)
class SalesAnalysisResult:
    """Legacy local sales input; proposed Project 07 results map here only temporarily.

    This compatibility model is not the agreed Project 07 wire contract.
    Project 06 does not query or own a sales source.
    """

    result: AgentResult
    observations: tuple[SalesObservation, ...] = ()
    category_mapping_version: str = "unversioned"
    dataset_label: str = "sales data"
    # Proposed Project 07 provenance fields. These remain optional until the
    # two owners agree on names and wire semantics.
    source: str | None = None
    locator: str | None = None
    geography: tuple[str, ...] = ()
    channel: tuple[str, ...] = ()
    product_mapping: str | None = None
    unit: str | None = None
    currency: str | None = None
    metric_definitions: tuple[str, ...] = ()
    calculation_references: tuple[str, ...] = ()
    missing_data: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    follow_up_questions: tuple[str, ...] = ()


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
    product_role: str | None = None
    note: str | None = None
    note_origin: ContextOrigin = "unknown"


@dataclass(frozen=True)
class InventoryProductResult:
    result: AgentResult
    products: tuple[InventoryProduct, ...] = ()


@dataclass(frozen=True, init=False)
class PlanningInputs:
    """Three shared inputs plus a compatibility slot for proposed sales results.

    Project 06 no longer owns a sales source. The optional slot only allows
    callers to pass a Project 07 result-shaped value while the teams agree on
    the wire schema; it is not an operational adapter.
    """

    request: PlanningRequest
    trend: TrendResult
    inventory: InventoryProductResult
    sales: SalesAnalysisResult | None = None

    def __init__(
        self,
        request: PlanningRequest,
        trend: TrendResult,
        *args: SalesAnalysisResult | InventoryProductResult,
        inventory: InventoryProductResult | None = None,
        sales: SalesAnalysisResult | None = None,
    ) -> None:
        if len(args) == 1:
            positional = args[0]
            if isinstance(positional, InventoryProductResult):
                if inventory is not None:
                    raise TypeError("InventoryProductResult was provided more than once.")
                inventory = positional
            elif isinstance(positional, SalesAnalysisResult):
                if sales is not None:
                    raise TypeError("SalesAnalysisResult was provided more than once.")
                sales = positional
            else:
                raise TypeError("Third positional input must be InventoryProductResult or SalesAnalysisResult.")
        elif len(args) == 2:
            if inventory is not None or sales is not None:
                raise TypeError("Do not mix positional sales/inventory inputs with their keywords.")
            sales, inventory = args
        elif len(args) > 2:
            raise TypeError("PlanningInputs accepts at most four positional inputs.")
        if inventory is None:
            raise InputConsistencyError("InventoryProductResult is required and must be normalized.")
        object.__setattr__(self, "request", request)
        object.__setattr__(self, "trend", trend)
        object.__setattr__(self, "inventory", inventory)
        object.__setattr__(self, "sales", sales)


@dataclass(frozen=True)
class ContextConflict:
    field: str
    values: Mapping[str, object]
    message: str


@dataclass(frozen=True)
class ProductPlanningContext:
    """Evidence-preserving context prepared for the internal concept generator.

    This is deliberately not serialized as ProductConcept. The shared output
    contract and model/provider boundary still require team agreement.
    """

    request_id: str
    schema_version: str
    request: PlanningRequest
    trends: TrendResult
    sales: SalesAnalysisResult
    inventory: InventoryProductResult
    input_statuses: Mapping[str, ContextInputStatus]
    styling_relationships: tuple[StylingRelationship, ...] = ()
    conflicts: tuple[ContextConflict, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    questions_for_validation: tuple[str, ...] = ()
    sales_market_result: SalesAnalysisResult | None = None


def _unique(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def _comparable_context(
    inputs: PlanningInputs,
    paired_inventory_indexes: frozenset[int] = frozenset(),
) -> Mapping[str, Mapping[str, object]]:
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

    sales_observations = inputs.sales.observations if inputs.sales else ()
    sales_seasons = _unique([item.season for item in sales_observations if item.season])
    sales_categories = _unique([item.category for item in sales_observations if item.category])
    if sales_seasons:
        values["season"]["sales"] = sales_seasons
    if sales_categories:
        values["category"]["sales"] = sales_categories

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
        [product.category for index, product in enumerate(products)
         if product.category and index not in paired_inventory_indexes]
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
    sales_attributes: dict[str, set[object]] = {}
    for observation in sales_observations:
        for signal in observation.attributes:
            if signal.value is not None:
                sales_attributes.setdefault(signal.name.strip().casefold(), set()).add(
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
        if name in sales_attributes:
            values[field_name]["sales"] = tuple(sorted(sales_attributes[name], key=str))
    return values


def _conflicts(
    inputs: PlanningInputs,
    paired_inventory_indexes: frozenset[int] = frozenset(),
) -> tuple[ContextConflict, ...]:
    conflicts: list[ContextConflict] = []
    for field_name, sources in _comparable_context(inputs, paired_inventory_indexes).items():
        normalized = {key: value for key, value in sources.items() if value not in (None, (), [])}
        if "request" not in normalized:
            continue

        def value_set(value: object) -> set[str]:
            items = value if isinstance(value, tuple) else (value,)
            return {str(item).strip().casefold() for item in items if item is not None}

        request_values = value_set(normalized["request"])
        for source, value in normalized.items():
            if source == "request" or not value_set(value):
                continue
            if request_values.isdisjoint(value_set(value)):
                conflicts.append(
                    ContextConflict(
                        field=field_name,
                        values={"request": normalized["request"], source: value},
                        message=(
                            f"Request {field_name} does not match the {source} result. "
                            "Keep both values and request review before using the "
                            "mismatched result as support."
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

    if not isinstance(inputs.request, PlanningRequest):
        raise InputConsistencyError("PlanningRequest is required and must be normalized.")
    if not isinstance(inputs.trend, TrendResult):
        raise InputConsistencyError("TrendResult is required and must be normalized.")
    if not isinstance(inputs.inventory, InventoryProductResult):
        raise InputConsistencyError("InventoryProductResult is required and must be normalized.")
    if inputs.sales is not None and not isinstance(inputs.sales, SalesAnalysisResult):
        raise InputConsistencyError("Optional SalesAnalysisResult must be normalized when provided.")
    if not isinstance(inputs.request.result, AgentResult):
        raise InputConsistencyError("PlanningRequest must contain a normalized AgentResult.")
    if not isinstance(inputs.trend.result, AgentResult):
        raise InputConsistencyError("TrendResult must contain a normalized AgentResult.")
    if inputs.sales is not None and not isinstance(inputs.sales.result, AgentResult):
        raise InputConsistencyError("SalesAnalysisResult must contain a normalized AgentResult.")
    if not isinstance(inputs.inventory.result, AgentResult):
        raise InputConsistencyError("InventoryProductResult must contain a normalized AgentResult.")

    results = [inputs.request.result, inputs.trend.result, inputs.inventory.result]
    if inputs.sales is not None:
        results.append(inputs.sales.result)
    request_ids = {result.request_id for result in results}
    if len(request_ids) != 1 or not next(iter(request_ids), ""):
        raise InputConsistencyError("Inputs must share one non-empty request_id.")

    schema_versions = {result.schema_version for result in results}
    if len(schema_versions) != 1 or not next(iter(schema_versions), ""):
        raise InputConsistencyError(
            "Inputs must use one non-empty, compatible schema_version."
        )

    statuses: dict[str, ContextInputStatus] = {}
    named_results = [
        ("planning_request", inputs.request.result),
        ("trend_result", inputs.trend.result),
        ("inventory_product_result", inputs.inventory.result),
    ]
    if inputs.sales is not None:
        named_results.append(("sales_analysis_result", inputs.sales.result))
    for input_name, result in named_results:
        if result.status not in {"ok", "partial", "no_results", "error"}:
            raise InputConsistencyError(
                f"Unsupported upstream status '{result.status}' from {result.agent_id}."
            )
        if not result.agent_id:
            raise InputConsistencyError("Each upstream result must include an agent_id.")
        statuses[input_name] = result.status
    if inputs.sales is None:
        statuses["sales_analysis_result"] = "not_provided"
    # Preserve the former read-only convenience shape for local callers. This
    # placeholder is not an upstream result: status stays not_provided and the
    # draft handoff slot remains None, so it cannot be rendered as a zero.
    sales_context = inputs.sales or SalesAnalysisResult(
        result=AgentResult(
            "not-provided",
            next(iter(request_ids)),
            next(iter(schema_versions)),
            "no_results",
            limitations=("Project_07 sales/market result was not provided; no sales source was queried.",),
        )
    )

    evidence_ids = _unique(
        [
            *inputs.request.result.evidence_ids,
            *inputs.trend.result.evidence_ids,
            *(inputs.sales.result.evidence_ids if inputs.sales else ()),
            *inputs.inventory.result.evidence_ids,
            *(evidence_id for observation in (inputs.sales.observations if inputs.sales else ()) for evidence_id in observation.evidence_ids),
            *(evidence_id for candidate in inputs.trend.candidates for evidence_id in candidate.evidence_ids),
            *(evidence_id for product in inputs.inventory.products for evidence_id in product.evidence_ids),
            *(evidence_id for attr in inputs.request.requested_attributes for evidence_id in attr.evidence_ids),
            *(evidence_id for candidate in inputs.trend.candidates for attr in candidate.attributes for evidence_id in attr.evidence_ids),
            *(evidence_id for observation in (inputs.sales.observations if inputs.sales else ()) for attr in observation.attributes for evidence_id in attr.evidence_ids),
            *(evidence_id for product in inputs.inventory.products for attr in product.attributes for evidence_id in attr.evidence_ids),
        ]
    )

    limitations = _unique(
        [
            *inputs.request.result.limitations,
            *inputs.trend.result.limitations,
            *(inputs.sales.result.limitations if inputs.sales else ()),
            *inputs.inventory.result.limitations,
            *(
                f"Inventory note ({product.note_origin}; not independently verified): {product.note}"
                for product in inputs.inventory.products
                if product.note and product.note.strip()
            ),
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
    from .styling import build_styling_relationships

    styling_relationships = build_styling_relationships(
        inputs.request, inputs.inventory.products
    ) if statuses["inventory_product_result"] in {"ok", "partial"} else ()
    paired_inventory_indexes = frozenset(
        relation.inventory_product_index for relation in styling_relationships
    )
    conflicts = _conflicts(inputs, paired_inventory_indexes)
    questions = _unique(
        [
            *questions,
            *(
                f"상의·하의 코디 관계는 {relation.rule_version} 규칙과 "
                f"{relation.request_role_source}, {relation.inventory_role_source} 분류로 연결했습니다. "
                "코디 적합성은 Evidence로 입증된 사실이 아니므로 MD 확인이 필요합니다."
                for relation in styling_relationships
            ),
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
        sales=sales_context,
        inventory=inputs.inventory,
        input_statuses=statuses,
        styling_relationships=styling_relationships,
        conflicts=conflicts,
        evidence_ids=evidence_ids,
        limitations=limitations,
        questions_for_validation=questions,
        sales_market_result=inputs.sales,
    )
