"""Deterministic planning-brief assembly from a reviewed H&M opportunity."""

from __future__ import annotations

import hashlib
from typing import Any


def build_review_brief(payload: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    opportunity_id = str(payload.get("opportunity_id", "")).strip()
    opportunity = next((item for item in analysis.get("opportunity_candidates", []) if item.get("opportunity_id") == opportunity_id), None)
    if opportunity is None:
        raise ValueError("선택 후보가 현재 분석 버전에 없습니다.")
    request = payload.get("request") if isinstance(payload.get("request"), dict) else {}
    user_hypotheses = {
        "color_direction": str(request.get("color_hypothesis", "")).strip() or None,
        "silhouette": str(request.get("silhouette_hypothesis", "")).strip() or None,
        "material": str(request.get("material_hypothesis", "")).strip() or None,
        "price_position": str(request.get("price_hypothesis", "")).strip() or None,
        "design_constraints": str(request.get("design_constraints", "")).strip() or None,
    }
    evidence = opportunity["observations"]
    evidence_ids = [item["evidence_id"] for item in opportunity.get("evidence", []) if item.get("evidence_id")]
    observed_months = evidence.get("observed_month_peaks_by_week_start", [])
    colors = evidence.get("top_observed_colors", [])
    facts = {
        "product_group_name": opportunity["category"]["product_group_name"],
        "product_type_name": opportunity["category"]["product_type_name"],
        "purchase_rows": evidence["observed_purchase_rows"],
        "share_of_joined_purchase_rows": evidence["share_of_joined_purchase_rows"],
        "observation_period": analysis.get("observation_period"),
        "calendar_months_with_most_observed_rows": observed_months,
        "top_observed_colors": colors,
        "top_5_style_share": evidence.get("top_5_style_share"),
    }
    missing_inputs = [
        {"field": "trend_result", "status": "no_results", "question": "선택 시즌/시장에 적용 가능한 승인된 트렌드 Evidence가 있는가?"},
        {"field": "inventory_and_returns", "status": "no_results", "question": "현재 상품 구색·재고·반품 자료와 기준일은 무엇인가?"},
        {"field": "cost_and_margin", "status": "unknown", "question": "원가·마진·가격 기준과 통화가 확인되었는가?"},
        {"field": "customer_segments", "status": "unknown", "question": "확인된 고객/시장 근거가 있는가?"},
        {"field": "design_attributes", "status": "user_hypothesis" if any(user_hypotheses.values()) else "unknown", "question": "색상·실루엣·소재 가설을 MD가 검토했는가?"},
    ]
    prompt_package = {
        "brief_id": None,
        "evidence_based_inputs": [{"claim": f"{facts['product_type_name']}의 과거 구매 기록은 {facts['purchase_rows']:,}건입니다.", "evidence_ids": evidence_ids}],
        "observed_color_reference": colors,
        "observed_calendar_months_not_merchandising_season": observed_months,
        "md_hypotheses_not_facts": user_hypotheses,
        "unknowns_to_exclude_from_assertions": [item["field"] for item in missing_inputs if item["status"] in {"no_results", "unknown"}],
        "constraints": ["Do not claim future demand, customer preference, sales growth, or commercial viability.", "Do not infer material performance or manufacturing feasibility.", "Do not add logos or protected reference imagery without rights approval."],
        "reference_image_source": None,
        "reference_rights_status": "not supplied; rights review required before use",
    }
    return {
        "schema_version": "hm-planning-brief-1",
        "generator": "deterministic-evidence-template",
        "status": "partial",
        "opportunity_id": opportunity_id,
        "analysis_version": analysis.get("analysis_version"),
        "source_period": analysis.get("observation_period"),
        "source_grain": analysis.get("grain"),
        "target_season": str(request.get("target_season", "")).strip() or None,
        "market": str(request.get("market", "")).strip() or None,
        "channel": str(request.get("channel", "")).strip() or None,
        "facts": facts,
        "claims": [
            {"field": "historical_category_scale", "value": facts["purchase_rows"], "kind": "evidence_observation", "evidence_ids": evidence_ids},
            {"field": "target_customer", "value": None, "kind": "unknown", "evidence_ids": []},
            {"field": "color_direction", "value": user_hypotheses["color_direction"], "kind": "hypothesis" if user_hypotheses["color_direction"] else "unknown", "evidence_ids": []},
            {"field": "silhouette", "value": user_hypotheses["silhouette"], "kind": "hypothesis" if user_hypotheses["silhouette"] else "unknown", "evidence_ids": []},
            {"field": "material", "value": user_hypotheses["material"], "kind": "hypothesis" if user_hypotheses["material"] else "unknown", "evidence_ids": []},
            {"field": "price_position", "value": user_hypotheses["price_position"], "kind": "hypothesis" if user_hypotheses["price_position"] else "unknown", "evidence_ids": []},
        ],
        "request": {key: str(request.get(key, "")).strip() or None for key in ("design_constraints", "selection_reason", "counter_evidence", "unknowns_to_validate")},
        "missing_inputs": missing_inputs,
        "evidence_ids": evidence_ids,
        "image_prompt_package": prompt_package,
        "limitations": [
            "Kaggle 공개 과거 자료는 H&M 실시간 내부 실적이 아닙니다.",
            "구매 행은 미래 수요, 고유 주문 수 또는 고객 선호와 같지 않습니다.",
            "월 패턴은 월요일 주 시작일의 달력 월이며 MD 시즌이 아닙니다.",
            "트렌드·재고·반품·원가·마진·고객 데이터가 입력되지 않아 상품 사업성을 판단하지 않았습니다.",
            "LLM과 이미지 생성 모델은 연결되어 있지 않습니다. 결과는 검토용 구조화 초안과 프롬프트 입력입니다.",
        ],
    }
