"""Local CLI for exploring the synthetic-only planning workbench dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = ROOT / "data/fixtures/synthetic_planning_workbench/dataset.json"
def load_dataset(path: Path = DEFAULT_DATASET) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get("data_nature") != "synthetic_only":
        raise ValueError("This workbench accepts datasets marked data_nature=synthetic_only only.")
    if not str(data.get("dataset_id", "")).startswith("SYNTHETIC-"):
        raise ValueError("Dataset ID must use the SYNTHETIC- prefix.")
    record_lists = ("taxonomy", "products", "inventory_snapshots", "documents", "evidence", "planning_inputs", "sales_market_handoffs")
    for collection in record_lists:
        rows = data.get(collection)
        if not isinstance(rows, list) or any(not isinstance(row, dict) or row.get("data_nature") != "synthetic_test" for row in rows):
            raise ValueError(f"Every {collection} record must be explicitly marked data_nature=synthetic_test.")
    return data, hashlib.sha256(raw).hexdigest()


def _run_id(snapshot: str, command: str, filters: dict[str, Any]) -> str:
    material = json.dumps({"snapshot": snapshot, "command": command, "filters": filters}, sort_keys=True)
    return "SYN-RUN-" + hashlib.sha256(material.encode()).hexdigest()[:16]


def _envelope(dataset: dict, snapshot: str, command: str, filters: dict, result: Any) -> dict:
    return {
        "run_id": _run_id(snapshot, command, filters),
        "dataset_id": dataset["dataset_id"],
        "snapshot_sha256": snapshot,
        "command": command,
        "filters": filters,
        "data_nature": "synthetic_only",
        "result": result,
    }


def _emit(payload: dict, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return
    print(f"run_id: {payload['run_id']}")
    print(f"dataset: {payload['dataset_id']} (synthetic_only)")
    result = payload["result"]
    if isinstance(result, str):
        print(result)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


def _matches_filters(item: dict, args) -> bool:
    for arg_name, field_name in (("season", "season"), ("category", "category_id"), ("channel", "channel"), ("status", "lifecycle_status"), ("document_type", "document_type")):
        expected = getattr(args, arg_name, None)
        if not expected:
            continue
        if arg_name == "status":
            value = item.get("status", item.get("lifecycle_status"))
        elif arg_name == "document_type" and "document_type" not in item:
            continue
        else:
            value = item.get(field_name)
        if arg_name == "channel" and value is None:
            value = item.get("channels")
        values = value if isinstance(value, list) else [value]
        if expected not in values and "all_synthetic" not in values:
            return False
    return True


def document_eligibility(dataset: dict, doc: dict) -> tuple[bool, list[str]]:
    reasons = []
    if doc.get("lifecycle_status") != "approved_example":
        reasons.append(f"lifecycle_status={doc.get('lifecycle_status')}")
    snapshot_date = dataset.get("snapshot_date")
    if doc.get("effective_from") and snapshot_date and doc["effective_from"] > snapshot_date:
        reasons.append("not_yet_effective_at_snapshot")
    if doc.get("effective_to") and snapshot_date and doc["effective_to"] < snapshot_date:
        reasons.append("expired_at_snapshot")
    evidence = {item.get("evidence_id"): item for item in dataset.get("evidence", [])}
    document_evidence = [evidence.get(evidence_id) for evidence_id in doc.get("evidence_ids", [])]
    if not document_evidence or any(item is None for item in document_evidence):
        reasons.append("missing_or_unresolved_evidence")
    elif any(item.get("verified") is not True or "product_planning" not in item.get("permitted_uses", []) for item in document_evidence):
        reasons.append("evidence_not_eligible_for_product_planning")
    return not reasons, reasons


def _visible_documents(dataset: dict, *, include_inactive: bool) -> list[dict]:
    docs = dataset.get("documents", [])
    if include_inactive:
        return docs
    return [doc for doc in docs if document_eligibility(dataset, doc)[0]]


def list_dataset(dataset: dict) -> dict:
    return {
        "notice": dataset["notice"],
        "generator_version": dataset["generator_version"],
        "seed": dataset["seed"],
        "counts": {key: len(dataset.get(key, [])) for key in ("products", "inventory_snapshots", "documents", "evidence", "planning_inputs", "sales_market_handoffs")},
        "document_types": dict(sorted({kind: sum(doc.get("document_type") == kind for doc in dataset.get("documents", [])) for kind in {doc.get("document_type", "unknown") for doc in dataset.get("documents", [])}}.items())),
        "document_lifecycle_states": dict(sorted({state: sum(doc.get("lifecycle_status") == state for doc in dataset.get("documents", [])) for state in {doc.get("lifecycle_status", "unknown") for doc in dataset.get("documents", [])}}.items())),
        "available_statuses": sorted({row.get("status") for row in dataset.get("inventory_snapshots", []) if row.get("status")} | {row.get("status") for row in dataset.get("sales_market_handoffs", []) if row.get("status")}),
        "quality_anomalies_intentionally_included": dataset.get("quality_anomalies_intentionally_included", []),
    }


def schema_summary(dataset: dict) -> dict:
    return {
        "dataset_metadata": ["dataset_id", "schema_version", "generator_version", "seed", "snapshot_date", "data_nature", "notice"],
        "entities": {
            "products": ["style_id", "brand_id", "line_id", "season", "market", "channels", "category_id", "product_role", "attributes", "skus", "evidence_ids"],
            "inventory_snapshots": ["style_id", "quantity", "unit", "as_of", "definition", "status", "evidence_ids"],
            "documents": ["document_id", "source_id", "document_type", "version", "lifecycle_status", "effective_from", "effective_to", "scope", "body", "evidence_ids"],
            "evidence": ["evidence_id", "source_id", "document_id", "locator", "supports", "permission_status", "permitted_uses", "verified"],
            "planning_inputs": ["request_id", "payload.planning_request", "payload.trend_result", "payload.inventory_product_result", "payload.sales_market_result"],
            "sales_market_handoffs": ["handoff_id", "producer_id", "status", "request_id", "scope", "findings", "limitations", "errors"],
        },
        "relationships": [
            "products.style_id -> inventory_snapshots.style_id",
            "products.evidence_ids -> evidence.evidence_id",
            "documents.document_id/source_id -> evidence.document_id/source_id",
            "documents.evidence_ids -> evidence.evidence_id",
            "planning_inputs.request_id -> every upstream payload request_id",
            "sales_market_handoffs.request_id -> planning_inputs.request_id",
        ],
        "invariants": ["all data_nature values identify synthetic test material", "Project_07 findings are opaque handoffs and are not recalculated by Project_06", "only approved_example documents are returned by search by default"],
    }


def search_dataset(dataset: dict, args) -> dict:
    query = args.query.casefold().strip()
    documents = _visible_documents(dataset, include_inactive=args.include_inactive)
    documents = [doc for doc in documents if _matches_filters(doc, args)]
    docs_found = []
    for doc in documents:
        searchable = " ".join((doc.get("title", ""), doc.get("body", ""), doc.get("document_id", ""), doc.get("document_type", ""))).casefold()
        if query in searchable:
            eligible, reasons = document_eligibility(dataset, doc)
            docs_found.append({**{key: doc.get(key) for key in ("document_id", "source_id", "document_type", "title", "version", "lifecycle_status", "season", "category_id", "channel", "effective_from", "effective_to", "evidence_ids", "body")}, "eligible_for_default_planning_search": eligible, "eligibility_reasons": reasons})
    products = []
    for item in dataset.get("products", []):
        if not _matches_filters(item, args):
            continue
        searchable = json.dumps(item, ensure_ascii=False, sort_keys=True).casefold()
        if query in searchable:
            products.append({key: item.get(key) for key in ("style_id", "season", "category_id", "product_role", "attributes", "lifecycle_status", "evidence_ids")})
    return {"query": args.query, "documents": docs_found, "products": products, "inactive_documents_excluded": not args.include_inactive}


def _find_product(dataset: dict, style_id: str) -> dict:
    product = next((item for item in dataset.get("products", []) if item.get("style_id") == style_id), None)
    if product is None:
        raise ValueError(f"Unknown synthetic style_id: {style_id}")
    return product


def compare_products(dataset: dict, style_ids: list[str]) -> dict:
    if len(style_ids) < 2:
        raise ValueError("compare requires at least two style IDs")
    products = [_find_product(dataset, style_id) for style_id in style_ids]
    names = sorted({name for product in products for name in product.get("attributes", {})})
    rows = []
    for name in names:
        values = {product["style_id"]: product.get("attributes", {}).get(name) for product in products}
        present = {str(value) for value in values.values() if value is not None}
        rows.append({"attribute": name, "values_by_style": values, "evidence_ids_by_style": {product["style_id"]: list(product.get("evidence_ids", [])) for product in products}, "has_missing_value": any(value is None for value in values.values()), "observed_values_differ": len(present) > 1})
    return {"styles": [{"style_id": product["style_id"], "season": product["season"], "category_id": product["category_id"], "product_role": product["product_role"], "sku_ids": [sku["sku_id"] for sku in product.get("skus", [])], "evidence_ids": product.get("evidence_ids", [])} for product in products], "attribute_comparison": rows, "interpretation": "Attribute differences are catalog observations only; no demand, preference, opportunity ranking, or product recommendation is inferred."}


def _related_evidence(dataset: dict, evidence_ids: list[str]) -> list[dict]:
    by_id = {item.get("evidence_id"): item for item in dataset.get("evidence", [])}
    result = []
    for evidence_id in evidence_ids:
        item = by_id.get(evidence_id)
        if item:
            result.append(item)
    return result


def inspect_entity(dataset: dict, entity_type: str, entity_id: str) -> dict:
    if entity_type == "style":
        item = _find_product(dataset, entity_id)
        snapshots = [row for row in dataset.get("inventory_snapshots", []) if row.get("style_id") == entity_id]
        return {"entity": item, "inventory_snapshots": snapshots, "evidence": _related_evidence(dataset, item.get("evidence_ids", [])), "documents": [doc for doc in dataset.get("documents", []) if entity_id in doc.get("body", "") or doc.get("document_id") in {ev.get("document_id") for ev in _related_evidence(dataset, item.get("evidence_ids", []))}]}
    if entity_type == "document":
        item = next((doc for doc in dataset.get("documents", []) if doc.get("document_id") == entity_id), None)
        if item is None:
            raise ValueError(f"Unknown synthetic document_id: {entity_id}")
        eligible, reasons = document_eligibility(dataset, item)
        return {"document": item, "eligible_for_default_planning_search": eligible, "eligibility_reasons": reasons, "evidence": _related_evidence(dataset, item.get("evidence_ids", []))}
    if entity_type == "evidence":
        item = next((ev for ev in dataset.get("evidence", []) if ev.get("evidence_id") == entity_id), None)
        if item is None:
            raise ValueError(f"Unknown synthetic evidence_id: {entity_id}")
        doc = next((doc for doc in dataset.get("documents", []) if doc.get("document_id") == item.get("document_id")), None)
        return {"evidence": item, "source_document": doc, "data_nature": "synthetic_only"}
    if entity_type == "handoff":
        item = next((row for row in dataset.get("sales_market_handoffs", []) if row.get("handoff_id") == entity_id), None)
        if item is None:
            raise ValueError(f"Unknown synthetic handoff_id: {entity_id}")
        return {"handoff": item, "owner": "Project_07", "connected_to_project06_draft": False}
    raise ValueError(f"Unsupported entity type: {entity_type}")


def quality_report(dataset: dict) -> dict:
    evidence_ids = {item.get("evidence_id") for item in dataset.get("evidence", [])}
    documents_by_id = {item.get("document_id"): item for item in dataset.get("documents", [])}
    sku_locations: dict[str, list[str]] = {}
    for product in dataset.get("products", []):
        for sku in product.get("skus", []):
            sku_locations.setdefault(sku.get("sku_id", ""), []).append(product["style_id"])
    issues = []
    for sku, owners in sku_locations.items():
        if sku and len(owners) > 1:
            issues.append({"code": "DUPLICATE_SKU_ID", "id": sku, "styles": owners, "severity": "error"})
    for product in dataset.get("products", []):
        for name, value in product.get("attributes", {}).items():
            if value is None or value == "":
                issues.append({"code": "MISSING_PRODUCT_ATTRIBUTE", "style_id": product["style_id"], "attribute": name, "severity": "warning"})
        for evidence_id in product.get("evidence_ids", []):
            if evidence_id not in evidence_ids:
                issues.append({"code": "UNKNOWN_PRODUCT_EVIDENCE", "style_id": product["style_id"], "evidence_id": evidence_id, "severity": "error"})
    for evidence_item in dataset.get("evidence", []):
        source_doc = documents_by_id.get(evidence_item.get("document_id"))
        if source_doc is None or source_doc.get("source_id") != evidence_item.get("source_id"):
            issues.append({"code": "EVIDENCE_SOURCE_DOCUMENT_MISMATCH", "evidence_id": evidence_item.get("evidence_id"), "document_id": evidence_item.get("document_id"), "severity": "error"})
    for doc in dataset.get("documents", []):
        for evidence_id in doc.get("evidence_ids", []):
            if evidence_id not in evidence_ids:
                issues.append({"code": "UNKNOWN_DOCUMENT_EVIDENCE", "document_id": doc["document_id"], "evidence_id": evidence_id, "severity": "error"})
        if doc.get("document_type") == "guideline" and doc.get("lifecycle_status") != "approved_example":
            issues.append({"code": "GUIDELINE_NOT_ACTIVE", "document_id": doc["document_id"], "lifecycle_status": doc.get("lifecycle_status"), "severity": "warning"})
    for snapshot in dataset.get("inventory_snapshots", []):
        if snapshot.get("status") in {"ok", "partial"}:
            if snapshot.get("quantity") is not None and not snapshot.get("unit"):
                issues.append({"code": "INVENTORY_UNIT_MISSING", "style_id": snapshot.get("style_id"), "severity": "warning"})
            if snapshot.get("quantity") is not None and not snapshot.get("as_of"):
                issues.append({"code": "INVENTORY_AS_OF_MISSING", "style_id": snapshot.get("style_id"), "severity": "warning"})
        if snapshot.get("status") == "no_results" and snapshot.get("quantity") == 0:
            issues.append({"code": "NO_RESULTS_MUST_NOT_BE_ZERO", "style_id": snapshot.get("style_id"), "severity": "error"})
    for row in dataset.get("inventory_snapshots", []):
        if row.get("status") in {"ok", "partial"} and row.get("quantity") == 0:
            issues.append({"code": "OBSERVED_ZERO_DISTINCT_FROM_NO_RESULTS", "style_id": row.get("style_id"), "unit": row.get("unit"), "as_of": row.get("as_of"), "severity": "info"})
    # The fixture embeds one intentionally conflicting draft spec alongside
    # the catalog record. Report it as a conflict to review, never as policy.
    for doc in dataset.get("documents", []):
        match = re.search(r"(SYN-STYLE-[A-Z]+-\d+)", doc.get("body", ""))
        if doc.get("document_type") == "product_specification" and match:
            style_id = match.group(1)
            if doc.get("lifecycle_status") != "approved_example":
                product = next((item for item in dataset.get("products", []) if item.get("style_id") == style_id), None)
                if product and "color=" in doc.get("body", ""):
                    issues.append({"code": "SPECIFICATION_VERSION_CONFLICT_REVIEW", "style_id": style_id, "document_id": doc["document_id"], "catalog_color": product.get("attributes", {}).get("color"), "document_lifecycle_status": doc.get("lifecycle_status"), "severity": "warning"})
    return {"issue_count": len(issues), "issues": issues, "interpretation": "Quality diagnostics flag fixture defects; they do not repair data or imply commercial risk."}


def list_handoffs(dataset: dict, status: str | None) -> dict:
    rows = dataset.get("sales_market_handoffs", [])
    if status:
        rows = [row for row in rows if row.get("status") == status]
    return {
        "owner": "Project_07",
        "notice": "These are standalone synthetic handoff fixtures. They are not connected to the synthetic Project_06 draft request or a live Project_07 API.",
        "results": rows,
    }


def render_draft(dataset: dict, request_id: str) -> str:
    fixture = next((row for row in dataset.get("planning_inputs", []) if row.get("request_id") == request_id), None)
    if fixture is None:
        raise ValueError(f"Unknown synthetic planning request_id: {request_id}")
    # Reuse Project_06's current internal request adapter, context, generator,
    # Evidence checks, and response assembly without adding an API contract.
    from .prototype.server import _build_planning_draft_response

    response = _build_planning_draft_response(fixture["payload"])
    draft = response.get("draft", {})
    docs_by_evidence: dict[str, list[dict]] = {}
    for evidence_item in dataset.get("evidence", []):
        docs_by_evidence.setdefault(evidence_item.get("evidence_id"), []).append(evidence_item)
    lines = [
        "# 합성 자료 기반 상품기획 검토 초안",
        "",
        "> 합성 데이터 전용 예시입니다. 실제 회사 자료·정책·시장 사실·수요를 나타내지 않습니다.",
        "> 검토용이며 자동 승인 또는 상품 채택 권고가 아닙니다.",
        "",
        f"- request_id: `{request_id}`",
        f"- dataset: `{dataset['dataset_id']}`",
        f"- result status: `{response.get('status')}`",
        "",
        "## 입력 상태",
        "",
    ]
    lines.extend(f"- `{name}`: `{status}`" for name, status in response.get("input_statuses", {}).items())
    lines += ["", "## 기획 초안", "", f"- 요약: {draft.get('opportunity', {}).get('value')}", f"- 대상 고객: {draft.get('target_customer', {}).get('value') or '미확정'}", f"- 상품 정의: {draft.get('product_definition', {}).get('value')}", "", "## 제안 속성", ""]
    for attribute in draft.get("attributes", []):
        ids = attribute.get("evidence_ids", [])
        lines.append(f"- `{attribute.get('name')}` = `{attribute.get('value')}` · `{attribute.get('kind')}` · Evidence: {', '.join(ids) if ids else '없음'}")
        for evidence_id in ids:
            for evidence in docs_by_evidence.get(evidence_id, []):
                lines.append(f"  - 출처 `{evidence.get('document_id')}` / `{evidence.get('locator')}` / {evidence.get('permission_status')}")
    lines += ["", "## 가이드 문서 상태", "", "- Project_06 기본 RAG는 `not_configured`이므로 이번 초안 생성에서 적용된 가이드 문서는 없습니다.", "- 다음은 범위가 맞는 허가 합성 문서 후보이며, 현재 생성기 입력으로 주입되지 않았습니다."]
    request_context = fixture["payload"]["planning_request"].get("context", {})
    request_season = (request_context.get("season") or {}).get("value") if isinstance(request_context.get("season"), dict) else request_context.get("season")
    request_category = (request_context.get("category") or {}).get("value") if isinstance(request_context.get("category"), dict) else request_context.get("category")
    eligible = [doc for doc in dataset.get("documents", []) if doc.get("document_type") == "guideline" and document_eligibility(dataset, doc)[0] and doc.get("season") in {"all_synthetic", request_season} and doc.get("category_id") in {"all_synthetic", request_category}]
    for doc in eligible:
        lines.append(f"- 후보 `{doc['document_id']}` v{doc['version']} · {doc['season']} / {doc['category_id']} / `{doc['lifecycle_status']}` · Evidence {', '.join(doc.get('evidence_ids', []))}")
    if not eligible:
        lines.append("- 적용 가능한 문서 없음")
    lines += ["", "## 미확정·제한사항", ""]
    lines.extend(f"- {item}" for item in draft.get("limitations", []))
    lines.extend(f"- MD 확인: {item}" for item in draft.get("questions_for_validation", []))
    lines += ["", "## 판매·시장 handoff", "", "Project_06은 upstream 결과를 재집계하지 않습니다. 이 합성 요청의 결과 상태·범위·제한은 원본 handoff를 확인하세요.", ""]
    sales = fixture["payload"].get("sales_market_result")
    if sales is None:
        lines.append("- status: `not_provided` · 이 draft fixture에는 Project_07 결과를 연결하지 않았습니다.")
    else:
        lines.append(f"- status: `{sales.get('status', 'unknown')}` · producer: `{sales.get('agent_id', 'unknown')}` · data_nature: `{sales.get('data_nature', 'unspecified')}`")
    lines += ["", "## 추적 메타데이터", "", f"- generation: `{response.get('generation_metadata', {})}`", f"- validation issues: `{response.get('validation_issues', [])}`", ""]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET, help="synthetic_only dataset JSON")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list dataset contents")
    sub.add_parser("schema", help="show schema and relationships")
    search = sub.add_parser("search", help="search products and eligible documents")
    search.add_argument("query")
    search.add_argument("--season")
    search.add_argument("--category")
    search.add_argument("--channel")
    search.add_argument("--status")
    search.add_argument("--document-type")
    search.add_argument("--include-inactive", action="store_true", help="include drafts/expired docs, visibly marked")
    compare = sub.add_parser("compare", help="compare catalog attributes without scoring")
    compare.add_argument("style_ids", nargs="+")
    show = sub.add_parser("show", help="inspect a style, document, or Evidence record")
    show.add_argument("entity_type", choices=("style", "document", "evidence", "handoff"))
    show.add_argument("entity_id")
    sub.add_parser("quality", help="find intentional data-quality issues")
    handoffs = sub.add_parser("handoffs", help="inspect standalone synthetic Project_07 status fixtures")
    handoffs.add_argument("--status", choices=("ok", "partial", "no_results", "error"))
    draft = sub.add_parser("draft", help="generate an internal draft from a synthetic request fixture")
    draft.add_argument("request_id")
    draft.add_argument("--output", type=Path)
    for command_parser in (sub.choices["list"], sub.choices["schema"], sub.choices["quality"], sub.choices["handoffs"], sub.choices["show"], sub.choices["compare"], sub.choices["draft"], sub.choices["search"]):
        command_parser.add_argument("--json", action="store_true", dest="as_json", help="print machine-readable JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        dataset, snapshot = load_dataset(args.dataset)
        filters: dict[str, Any] = {}
        if args.command == "list":
            result = list_dataset(dataset)
        elif args.command == "schema":
            result = schema_summary(dataset)
        elif args.command == "search":
            filters = {key: getattr(args, key) for key in ("query", "season", "category", "channel", "status", "document_type", "include_inactive")}
            result = search_dataset(dataset, args)
        elif args.command == "compare":
            filters = {"style_ids": args.style_ids}
            result = compare_products(dataset, args.style_ids)
        elif args.command == "show":
            filters = {"entity_type": args.entity_type, "entity_id": args.entity_id}
            result = inspect_entity(dataset, args.entity_type, args.entity_id)
        elif args.command == "quality":
            result = quality_report(dataset)
        elif args.command == "handoffs":
            filters = {"status": args.status}
            result = list_handoffs(dataset, args.status)
        elif args.command == "draft":
            filters = {"request_id": args.request_id}
            markdown = render_draft(dataset, args.request_id)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(markdown, encoding="utf-8")
                result = f"Wrote synthetic-only planning draft to {args.output}"
            else:
                result = markdown
        else:  # pragma: no cover - argparse enforces choices
            raise ValueError(f"Unsupported command: {args.command}")
        payload = _envelope(dataset, snapshot, args.command, filters, result)
        _emit(payload, as_json=getattr(args, "as_json", False))
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"synthetic planning workbench error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
