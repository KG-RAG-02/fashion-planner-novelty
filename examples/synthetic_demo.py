"""Run the local draft flow with synthetic data only.

From the repository root:
    PYTHONPATH=src python3 examples/synthetic_demo.py

The identifiers and values below are invented for a software demonstration;
they are not VOGUE business data or approved shared-contract examples.
"""

from __future__ import annotations

import json
from dataclasses import asdict

from vogue_npp import (
    AgentResult,
    AttributeSignal,
    InventoryProduct,
    InventoryProductResult,
    PlanningInputs,
    PlanningRequest,
    TrendCandidate,
    TrendResult,
    build_planning_context,
    generate_concept_draft,
)


REQUEST_ID = "synthetic-request-001"
SCHEMA_VERSION = "internal-prototype-0"


def main() -> None:
    query_trend_agent = "query-trend-agent"
    request = PlanningRequest(
        result=AgentResult(
            agent_id=query_trend_agent,
            request_id=REQUEST_ID,
            schema_version=SCHEMA_VERSION,
            status="ok",
        ),
        original_query="(synthetic) 2027SS 여성 아우터 콘셉트 제안",
        season="2027SS",
        market=("KR",),
        channel=("online",),
        category="women_outerwear",
        requested_attributes=(
            AttributeSignal(
                name="color",
                value="olive",
                origin="user_requested",
            ),
        ),
        missing_fields=("target_customer", "target_price_range"),
        field_origins={
            "season": "inferred",
            "market": "user",
            "channel": "user",
            "category": "inferred",
        },
    )
    trend = TrendResult(
        result=AgentResult(
            agent_id=query_trend_agent,
            request_id=REQUEST_ID,
            schema_version=SCHEMA_VERSION,
            status="partial",
            evidence_ids=("query-trend:E-SYN-001",),
            limitations=("합성 시연용 트렌드 근거입니다.",),
        ),
        candidates=(
            TrendCandidate(
                name="urban utility (synthetic)",
                qualification="candidate",
                season="2027SS",
                market=("KR",),
                channel=("online",),
                category="women_outerwear",
                attributes=(
                    AttributeSignal(
                        name="silhouette",
                        value="relaxed",
                        origin="evidence_observation",
                        evidence_ids=("query-trend:E-SYN-001",),
                    ),
                ),
                evidence_ids=("query-trend:E-SYN-001",),
            ),
        ),
    )
    inventory = InventoryProductResult(
        result=AgentResult(
            agent_id="own-product-inventory-agent",
            request_id=REQUEST_ID,
            schema_version=SCHEMA_VERSION,
            status="partial",
            evidence_ids=("inventory:E-SYN-002",),
            limitations=("재고는 합성 시연용 현재 시점 스냅샷입니다.",),
        ),
        products=(
            InventoryProduct(
                style_id="SYNTHETIC-STYLE-001",
                sku_ids=("SYNTHETIC-SKU-001",),
                season="2027SS",
                category="women_outerwear",
                market=("KR",),
                channel=("online",),
                quantity=0,
                unit="pieces",
                inventory_definition="available_to_sell",
                as_of="2026-11-05T00:00:00+09:00",
                evidence_ids=("inventory:E-SYN-002",),
            ),
        ),
    )

    context = build_planning_context(
        PlanningInputs(request=request, trend=trend, inventory=inventory)
    )
    draft, validation_issues = generate_concept_draft(context)
    print("SYNTHETIC EXAMPLE ONLY — not project or business data")
    print(
        json.dumps(
            {
                "draft": asdict(draft),
                "validation_issues": [asdict(issue) for issue in validation_issues],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
