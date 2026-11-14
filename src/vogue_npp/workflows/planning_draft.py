"""Convert P08 producer inputs into the evidence-aware P06 planning draft."""
from __future__ import annotations

from ..domain.context import (
    AgentResult,
    AttributeSignal,
    InventoryProduct,
    InventoryProductResult,
    InventoryTrendResult,
    PlanningInputs,
    PlanningRequest,
    TrendCandidate,
    TrendResult,
    build_planning_context,
)
from ..domain.generator import ConceptGenerator, RuleBasedConceptGenerator


def _is_recovered_category_lookup_warning(value: object) -> bool:
    """Recognize only an explicitly recovered find_categories rule violation."""
    if not isinstance(value, str):
        return False
    message = value.casefold()
    recovered = (
        "recovered", "retry succeeded", "reselected successfully", "re-selection completed",
        "재시도 성공", "재선택 완료", "재선택 성공",
    )
    return "find_categories" in message and "rule_violation" in message and any(
        marker in message for marker in recovered
    )


def _stock_article_id(item: dict) -> str | None:
    """Resolve an article ID from the explicit field or numeric stock SKU."""
    explicit = item.get("article_id")
    if explicit is not None and str(explicit).isdigit():
        return str(explicit)
    sku_ids = item.get("sku_ids", ())
    if isinstance(sku_ids, (list, tuple)):
        return next((str(value) for value in sku_ids if value is not None and str(value).isdigit()), None)
    return None


def _analyze_planning_inputs(
    payload: dict,
    *,
    concept_generator: ConceptGenerator | None = None,
) -> dict:
    """Build a draft from the planning request, trend, and inventory inputs."""
    request_payload = payload.get("planning_request")
    trend_payload = payload.get("trend_result")
    inventory_payload = payload.get("inventory_product_result")
    if not all(isinstance(value, dict) for value in (request_payload, trend_payload, inventory_payload)):
        raise ValueError("planning_request, trend_result, inventory_product_result JSON 객체가 필요합니다.")

    request_id = str(request_payload.get("request_id", payload.get("request_id", ""))).strip()[:160]
    schema = str(request_payload.get("schema_version", payload.get("schema_version", "1.0"))).strip()[:80]
    if not request_id or not schema:
        raise ValueError("planning_request.request_id와 schema_version이 필요합니다.")

    def evidence_ids_in(value) -> list[str]:
        found: list[str] = []
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "evidence_id" and isinstance(child, str) and child:
                    found.append(child)
                elif key in {"evidence_ids", "input_evidence_ids"}:
                    if isinstance(child, str) and child:
                        found.append(child)
                    elif isinstance(child, (list, tuple)):
                        found.extend(str(item) for item in child if item)
                else:
                    found.extend(evidence_ids_in(child))
        elif isinstance(value, (list, tuple)):
            for child in value:
                found.extend(evidence_ids_in(child))
        return list(dict.fromkeys(found))

    def envelope_evidence_ids(data: dict) -> tuple[str, ...]:
        return tuple(evidence_ids_in(data))

    def collect_list_values(data, keys: set[str]) -> tuple:
        found = []

        def visit(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key in keys and isinstance(child, (list, tuple)):
                        found.extend(child)
                    elif key in keys and child is not None:
                        found.append(child)
                    visit(child)
            elif isinstance(value, (list, tuple)):
                for child in value:
                    visit(child)

        visit(data)
        return tuple(found)

    def collect_limitations(data) -> tuple[str, ...]:
        return tuple(dict.fromkeys(
            str(item) for item in collect_list_values(data, {"limitations", "data_limitations"})
        ))

    def context_value(value):
        return value.get("value") if isinstance(value, dict) else value

    def context_origin(value, *, default: str = "unknown") -> str:
        source = None
        if isinstance(value, dict):
            source = value.get("source", value.get("origin", value.get("kind")))
        elif isinstance(value, str):
            candidate = value.strip().casefold().replace("-", "_")
            if candidate in {
                "user", "user_requested", "user_request", "request", "explicit",
                "inferred", "agent_inferred", "trend", "stock", "evidence_observation",
                "unknown", "unresolved", "to_validate",
            }:
                source = candidate
        if source is None:
            return default
        normalized = str(source).strip().casefold().replace("-", "_")
        if normalized in {"user", "user_requested", "user_request", "request", "explicit"}:
            return "user"
        if normalized in {"inferred", "agent_inferred", "trend", "stock", "evidence_observation"}:
            return "inferred"
        return "unknown"

    def request_field_origin(name: str) -> str:
        context_value_for_field = raw_context.get(name)
        if context_value_for_field is not None:
            detected = context_origin(context_value_for_field, default="user")
        else:
            detected = context_origin(request_payload.get(name))
        explicit_origins = request_payload.get("field_origins")
        explicit = explicit_origins.get(name) if isinstance(explicit_origins, dict) else None
        explicit = context_origin(explicit)
        # A concrete P08 context value with no provenance marker is a normalized
        # user request. A stale `unknown` override must not erase that provenance.
        return explicit if explicit != "unknown" else detected

    def attribute_signal(item: dict, *, requested: bool = False) -> AttributeSignal:
        evidence_ids = tuple(item.get("evidence_ids", ()))
        raw_origin = item.get("origin")
        if requested:
            source_origin = context_origin(item.get("source"))
            origin = "user_requested" if source_origin == "user" else (
                "evidence_observation" if source_origin == "inferred" and evidence_ids else "unknown"
            )
        else:
            origin = raw_origin if raw_origin in {"user_requested", "evidence_observation", "agent_proposal", "unknown"} else (
                "evidence_observation" if evidence_ids else "unknown"
            )
        return AttributeSignal(item["name"], item.get("value"), origin, evidence_ids)

    def attribute_signals(value, *, requested: bool = False) -> tuple[AttributeSignal, ...]:
        if isinstance(value, dict):
            normalized = []
            for name, item in value.items():
                if isinstance(item, dict):
                    normalized.append(attribute_signal({"name": name, **item}, requested=requested))
                elif isinstance(item, (list, tuple)):
                    normalized.extend(
                        attribute_signal({"name": name, "value": child}, requested=requested)
                        for child in item if child is not None
                    )
                else:
                    normalized.append(attribute_signal({"name": name, "value": item}, requested=requested))
            return tuple(normalized)
        return tuple(attribute_signal(item, requested=requested) for item in value or () if isinstance(item, dict))

    for name, data in (("trend_result", trend_payload), ("inventory_product_result", inventory_payload)):
        if data.get("request_id") != request_id:
            raise ValueError(f"{name}.request_id가 planning_request와 일치해야 합니다.")
        version = data.get("schema_version", schema)
        if version != schema:
            raise ValueError("입력 schema_version이 서로 일치해야 합니다.")

    def result_meta(data: dict, default_agent: str) -> AgentResult:
        status = data.get("status", "ok")
        if not isinstance(status, str) or status not in {"ok", "partial", "no_results", "error"}:
            raise ValueError("지원하지 않는 입력 상태입니다.")
        agent_id = data.get("agent_id", default_agent)
        if not isinstance(agent_id, str) or not agent_id.strip():
            raise ValueError("입력 producer agent_id가 비어 있거나 문자열이 아닙니다.")
        return AgentResult(
            agent_id=agent_id,
            request_id=str(data.get("request_id", request_id)),
            schema_version=str(data.get("schema_version", schema)),
            status=status,
            evidence_ids=envelope_evidence_ids(data),
            limitations=collect_limitations(data),
            producer_id_origin="payload" if "agent_id" in data else "adapter_assumption",
            source_schema_version=data.get("schema_version"),
            schema_version_origin="payload" if "schema_version" in data else "planning_request_fallback",
            status_origin="payload" if "status" in data else "adapter_default",
            errors=collect_list_values(data, {"errors"}),
            missing_data=collect_list_values(data, {"missing_data", "missing_fields", "missing_attributes"}),
        )

    raw_context = request_payload.get("context", {})
    raw_context = raw_context if isinstance(raw_context, dict) else {}
    request = PlanningRequest(
        result=result_meta(request_payload, "user-request"),
        original_query=request_payload.get("query", request_payload.get("original_query")),
        season=context_value(raw_context.get("season", request_payload.get("season"))),
        market=tuple(context_value(item) for item in raw_context.get("market", request_payload.get("market", ()))),
        channel=tuple(context_value(item) for item in raw_context.get("channel", request_payload.get("channel", ()))),
        category=context_value(raw_context.get("category", request_payload.get("category"))),
        product_role=context_value(raw_context.get("product_role", request_payload.get("product_role"))),
        target_customer=context_value(raw_context.get("target_customer", request_payload.get("target_customer"))),
        requested_attributes=attribute_signals(request_payload.get("requested_attributes", ()), requested=True),
        missing_fields=tuple(request_payload.get("missing_fields", ())),
        constraints=tuple(request_payload.get("constraints", ())),
        field_origins={
            key: request_field_origin(key)
            for key in ("season", "category", "target_customer")
            if raw_context.get(key, request_payload.get(key)) is not None
        },
        field_evidence_ids={
            key: tuple((raw_context.get(key, request_payload.get(key)) or {}).get("evidence_ids", ()))
            for key in ("season", "category", "target_customer")
            if isinstance(raw_context.get(key, request_payload.get(key)), dict)
            and (raw_context.get(key, request_payload.get(key)) or {}).get("evidence_ids")
        },
    )
    def normalize_trend_candidates(data: dict) -> tuple[TrendCandidate, ...]:
        candidates = data.get("trend_candidates", data.get("candidates"))
        if candidates is not None:
            return tuple(TrendCandidate(
                name=item["name"], qualification=item.get("qualification", "candidate"),
                season=item.get("season"), market=tuple(item.get("market", ())),
                channel=tuple(item.get("channel", ())), category=item.get("category"),
                attributes=attribute_signals(item.get("attributes", ())),
                evidence_ids=tuple(item.get("evidence_ids", ())),
                description=item.get("description"),
                description_evidence_ids=tuple(item.get("description_evidence_ids", ())),
                source_style_id=item.get("id", item.get("style_id")),
            ) for item in candidates if isinstance(item, dict) and item.get("name"))

        normalized = []
        for trend in data.get("trends", ()):
            if not isinstance(trend, dict):
                continue
            style = trend.get("style") or {}
            if not isinstance(style, dict) or not style.get("name"):
                continue
            descriptions = style.get("description", ())
            description_texts = []
            description_evidence = []
            for item in descriptions:
                if isinstance(item, dict) and item.get("text"):
                    description_texts.append(str(item["text"]))
                    description_evidence.extend(item.get("evidence_ids", ()))
            signals = []
            item_evidence = []
            for product in trend.get("items", ()):
                if not isinstance(product, dict):
                    continue
                refs = tuple(str(value) for value in product.get("evidence_ids", ()) if value)
                item_evidence.extend(refs)
                for field_name in ("colors", "materials", "patterns"):
                    label = {"colors": "color", "materials": "material", "patterns": "pattern"}[field_name]
                    for value in product.get(field_name, ()) or ():
                        signals.append(AttributeSignal(label, value, "evidence_observation" if refs else "unknown", refs))
                for field_name in ("fit", "shape", "length"):
                    value = product.get(field_name)
                    if value:
                        signals.append(AttributeSignal(field_name, value, "evidence_observation" if refs else "unknown", refs))
                for detail in product.get("details", ()) or ():
                    if isinstance(detail, dict):
                        value = detail.get("name") or detail.get("raw")
                        if value:
                            signals.append(AttributeSignal("detail", value, "evidence_observation" if refs else "unknown", refs))
            refs = tuple(dict.fromkeys((
                *style.get("focus_evidence_ids", ()), *description_evidence, *item_evidence,
            )))
            seasons = tuple(style.get("seasons", ()) or ())
            normalized.append(TrendCandidate(
                name=str(style["name"]), qualification="trend_analysis_result",
                season=seasons[0] if len(seasons) == 1 else None,
                attributes=tuple(signals), evidence_ids=refs,
                description="; ".join(dict.fromkeys(description_texts)) or None,
                description_evidence_ids=tuple(dict.fromkeys(description_evidence)),
                source_style_id=str(style["id"]) if style.get("id") is not None else None,
            ))
        return tuple(normalized)

    trend = TrendResult(
        result=result_meta(trend_payload, "trend-analysis-agent"),
        candidates=normalize_trend_candidates(trend_payload),
    )
    def normalize_inventory_product(item: dict, source_index: int, evidence_ids: tuple[str, ...]) -> InventoryProduct:
        stock = item.get("inventory") or {}
        # Accept the stock-agent response surface, while retaining the complete
        # original object in input_evidence for fields outside the internal model.
        raw_sku_ids = item.get("sku_ids", ())
        sku_ids = tuple(str(value) for value in raw_sku_ids if value is not None) if isinstance(raw_sku_ids, (list, tuple)) else ()
        article_id = _stock_article_id(item)
        allowed = {
            "style_id": item.get("style_id", item.get("product_id")),
            "sku_ids": sku_ids,
            "article_id": article_id,
            "season": item.get("season"), "category": item.get("category"),
            "market": tuple(item.get("market", ())), "channel": tuple(item.get("channel", ())),
            "attributes": attribute_signals(item.get("attributes", ())),
            "quantity": stock.get("quantity", item.get("quantity")),
            "unit": stock.get("unit", item.get("unit")),
            "as_of": stock.get("as_of", item.get("as_of")),
            "inventory_definition": stock.get("definition", item.get("inventory_definition")),
            "evidence_ids": tuple(dict.fromkeys((*item.get("evidence_ids", ()), *evidence_ids))),
            "product_role": item.get("product_role"),
            "note": item.get("note", item.get("reason")),
            "note_origin": "unknown",
            "source_product_index": source_index,
            "image_url": (
                item.get("image", {}).get("url")
                if isinstance(item.get("image"), dict)
                and isinstance(item.get("image", {}).get("url"), str)
                else None
            ),
        }
        return InventoryProduct(**allowed)

    def normalize_inventory_trend_results(data: dict, product_values: list) -> tuple[tuple[InventoryTrendResult, ...], tuple[str, ...]]:
        raw_results = data.get("trend_results", ())
        if not isinstance(raw_results, (list, tuple)):
            return (), ("stock-agent trend_results가 배열이 아니어서 per-trend 연결을 해석하지 않았습니다.",)
        root_evidence = data.get("evidence", ())
        root_evidence = root_evidence if isinstance(root_evidence, (list, tuple)) else ()
        upstream_style_ids = {item.source_style_id for item in trend.candidates if item.source_style_id}
        links: list[InventoryTrendResult] = []
        issues: list[str] = []
        for trend_index, item in enumerate(raw_results):
            if not isinstance(item, dict):
                issues.append(f"stock-agent trend_results[{trend_index}]가 객체가 아니어서 매핑하지 않았습니다.")
                continue
            style = item.get("style") if isinstance(item.get("style"), dict) else {}
            style_id = str(style["id"]) if style.get("id") is not None else None
            style_name = str(style["name"]) if style.get("name") is not None else None
            raw_index = item.get("product_index")
            product_index = raw_index if isinstance(raw_index, int) and not isinstance(raw_index, bool) else None
            matched_product = None
            if product_index is None:
                mapping_status = "invalid_index"
                issues.append(f"stock-agent trend_results[{trend_index}]에 유효한 product_index가 없어 상품 연결을 확인할 수 없습니다.")
            elif product_index < 0 or product_index >= len(product_values):
                mapping_status = "out_of_range"
                issues.append(f"stock-agent trend_results[{trend_index}].product_index={product_index}가 products 범위를 벗어납니다.")
            elif not isinstance(product_values[product_index], dict):
                mapping_status = "no_product"
            else:
                mapping_status = "linked"
                matched_product = product_values[product_index]

            raw_declared_ids = item.get("evidence_ids", ())
            declared_ids = tuple(str(value) for value in raw_declared_ids if value) if isinstance(raw_declared_ids, (list, tuple)) else ()
            root_ids = tuple(dict.fromkeys(
                str(ref["evidence_id"])
                for ref in root_evidence
                if isinstance(ref, dict) and ref.get("evidence_id")
                and style_id and ref.get("style_id") == style_id
            ))
            evidence_ids = declared_ids or root_ids
            evidence_source = "trend_result" if declared_ids else "root_evidence_by_style" if root_ids else "none"
            trend_input_match = (
                "style_id_missing" if not style_id else
                "trend_input_empty" if not upstream_style_ids else
                "matched" if style_id in upstream_style_ids else "no_matching_trend"
            )
            if style_id and upstream_style_ids and trend_input_match == "no_matching_trend":
                issues.append(f"stock-agent style_id '{style_id}'가 전달된 trend_result의 style ID와 일치하지 않습니다. 기존 mapping key는 다를 수 있으므로 확인이 필요합니다.")
            if matched_product is None and evidence_ids:
                issues.append(f"stock-agent trend_results[{trend_index}] Evidence는 보존했지만 product_index의 상품은 연결되지 않았습니다.")
            if matched_product is not None and not evidence_ids:
                issues.append(f"stock-agent trend_results[{trend_index}] 상품 연결은 확인했지만 연결된 Evidence가 없습니다.")
            links.append(InventoryTrendResult(
                trend_result_index=trend_index,
                style_id=style_id,
                style_name=style_name,
                status=item.get("status") if isinstance(item.get("status"), str) else None,
                product_index=product_index,
                mapping_status=mapping_status,
                trend_input_match=trend_input_match,
                product_style_id=matched_product.get("style_id") if matched_product else None,
                rank=item.get("rank") if isinstance(item.get("rank"), int) and not isinstance(item.get("rank"), bool) else None,
                summary=item.get("summary") if isinstance(item.get("summary"), str) else None,
                evidence_ids=evidence_ids,
                evidence_reference_source=evidence_source,
                limitations=collect_limitations(item),
                errors=collect_list_values(item, {"errors"}),
                missing_data=collect_list_values(item, {"missing_data", "missing_fields", "missing_attributes"}),
            ))
        return tuple(links), tuple(dict.fromkeys(issues))

    raw_products = inventory_payload.get("products", ())
    if not isinstance(raw_products, (list, tuple)):
        raw_products = ()
        mapping_issues = ("stock-agent products가 배열이 아니어서 상품을 정규화하지 않았습니다. 원본 payload는 보존했습니다.",)
    else:
        mapping_issues = ()
    inventory_trend_results, link_issues = normalize_inventory_trend_results(inventory_payload, list(raw_products))
    mapping_issues = tuple(dict.fromkeys((*mapping_issues, *link_issues)))
    evidence_by_product: dict[int, list[str]] = {}
    for link in inventory_trend_results:
        if link.mapping_status == "linked" and link.product_index is not None:
            evidence_by_product.setdefault(link.product_index, []).extend(link.evidence_ids)
    normalized_products = tuple(
        normalize_inventory_product(item, index, tuple(dict.fromkeys(evidence_by_product.get(index, ()))))
        for index, item in enumerate(raw_products) if isinstance(item, dict)
    )

    inventory = InventoryProductResult(
        result=result_meta(inventory_payload, "stock-agent"),
        products=normalized_products,
        trend_results=inventory_trend_results,
        mapping_issues=mapping_issues,
    )
    # Product planning/image generation deliberately excludes Project_07 data and
    # synthetic catalog/guideline RAG. Only the three declared inputs are used.
    context = build_planning_context(PlanningInputs(request, trend, inventory))
    draft_data_limitations = []
    # Keep this workflow deterministic and offline by default. Text-model
    # experimentation remains isolated behind the explicit generator port.
    generator = concept_generator or RuleBasedConceptGenerator()
    draft, issues = generator.generate(context)
    generation_metadata = getattr(generator, "generation_metadata", {
        "engine": "rule_based", "status": "generated", "prompt_version": None, "model": None,
    })
    from dataclasses import asdict

    input_sources = {
        "planning_request": request_payload,
        "trend_result": trend_payload,
        "inventory_product_result": inventory_payload,
    }
    normalized_results = {
        "planning_request": request.result,
        "trend_result": trend.result,
        "inventory_product_result": inventory.result,
    }
    input_evidence = {}
    for name, source in input_sources.items():
        if name in normalized_results:
            result_meta = normalized_results[name]
            metadata = {
                "producer_id": result_meta.agent_id,
                "producer_id_origin": result_meta.producer_id_origin,
                "source_schema_version": result_meta.source_schema_version,
                "schema_version_origin": result_meta.schema_version_origin,
                "internal_schema_version": result_meta.schema_version,
                "status_origin": result_meta.status_origin,
                "errors": list(result_meta.errors),
                "missing_data": list(result_meta.missing_data),
                "limitations": list(result_meta.limitations),
            }
        input_evidence[name] = {
            "status": context.input_statuses[name],
            **metadata,
            "evidence_ids": evidence_ids_in(source) if source is not None else [],
            "payload": source,
        }

    draft_data = asdict(draft)
    draft_data["limitations"] = list(dict.fromkeys((
        *draft_data.get("limitations", ()), *draft_data_limitations,
    )))
    draft_data["title"] = f"{draft.season or '시즌 미정'} {draft.category or '카테고리 미정'} 신제품 기획 초안"
    draft_data["review_status"] = "md_review_required"
    validation_issue_data = [asdict(issue) for issue in issues]
    if inventory.mapping_issues:
        validation_issue_data.append({
            "path": "stock_trend_results",
            "code": "INVENTORY_MAPPING_INCOMPLETE",
            "message": "One or more Stock product-to-trend links could not be verified; see limitations.",
        })
    material_limitations = tuple(
        limitation for limitation in context.limitations
        if not _is_recovered_category_lookup_warning(limitation)
    )
    return {
        "schema_version": "1.0",
        # Ignore only an explicitly recovered category-lookup warning. All
        # other limitations plus incomplete inputs, conflicts, required-field
        # gaps, and failed validation remain material partial-result reasons.
        "status": "partial" if (
            any(status != "ok" for status in context.input_statuses.values())
            or bool(material_limitations)
            or any(result.errors or result.missing_data for result in (
                request.result, trend.result, inventory.result,
            ))
            or bool(inventory.mapping_issues)
            or bool(context.conflicts)
            or bool(request.missing_fields)
            or not bool(draft.category)
            or any(issue.code != "TEXT_GENERATION_FALLBACK" for issue in issues)
        ) else "ok",
        "request_id": context.request_id,
        "input_statuses": dict(context.input_statuses),
        "draft": draft_data,
        "generation_metadata": generation_metadata,
        "input_evidence": input_evidence,
        "stock_trend_results": [asdict(item) for item in inventory.trend_results],
        "validation_issues": validation_issue_data,
        "evidence_ids": list(context.evidence_ids),
        "limitations": list(context.limitations),
        "conflicts": [asdict(conflict) for conflict in context.conflicts],
        "questions_for_validation": list(context.questions_for_validation),
    }
