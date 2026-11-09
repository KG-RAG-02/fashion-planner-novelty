"""Local-only web prototype server; stdlib only, no external provider calls."""

from __future__ import annotations

import json
import mimetypes
import os
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import repository
from ..domain.context import (
    AgentResult, AttributeSignal, InventoryProduct, InventoryProductResult, InventoryTrendResult,
    PlanningInputs, PlanningRequest, TrendCandidate, TrendResult,
    build_planning_context,
)
from ..domain.generator import RuleBasedConceptGenerator
from ..domain.retrieval import KnowledgeRetriever, RetrievalSourcePolicy
from ..settings import load_settings
from ..workflows.image_generation import (
    DEFAULT_IMAGE_DIR, DEFAULT_IMAGE_MODEL, OpenAIImageEditProvider,
    OpenAIImageProvider, run_concept_to_image,
)
from ..workflows.planning_retrieval import retrieve_planning_knowledge


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
WEB_ROOT = REPOSITORY_ROOT / "web" / "prototype"
GENERATED_IMAGE_ROOT = REPOSITORY_ROOT / DEFAULT_IMAGE_DIR
TREND_DEMO_JSON = REPOSITORY_ROOT / "examples" / "fixtures" / "ss-mens-shorts-trend-planning-demo.json"
TREND_DEMO_IMAGE = WEB_ROOT / "ss-mens-shorts-trend-planning-demo.png"
MAX_BODY_BYTES = 1_000_000
COMPARISON_IMAGE_MODELS = (
    "gpt-image-2.5-sunburst",
    "gpt-image-2.5-flare",
    "gpt-image-2",
)


class PrototypeHandler(BaseHTTPRequestHandler):
    server_version = "VOGUEPrototype/0.1"

    def log_message(self, fmt: str, *args: object) -> None:
        # Keep local query terms, brief text, and review content out of logs.
        return

    def _send(self, status: int, content: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(content)

    def _json(self, status: int, payload: object) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("잘못된 요청 크기입니다.") from exc
        if length < 0 or length > MAX_BODY_BYTES:
            raise ValueError("요청 본문은 1MB 이하여야 합니다.")
        payload = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(payload, dict):
            raise ValueError("JSON 객체 형태의 요청이 필요합니다.")
        return payload

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        try:
            if path == "/api/health":
                repository.initialize()
                self._json(200, {"ok": True, "mode": "new-product-planning"})
            elif path == "/api/trend-planning-demo":
                if not TREND_DEMO_JSON.is_file():
                    self._json(404, {"error": "트렌드 기획 데모 데이터를 찾을 수 없습니다."})
                else:
                    self._json(200, json.loads(TREND_DEMO_JSON.read_text(encoding="utf-8")))
            elif path == "/api/trend-planning-demo/image":
                if not TREND_DEMO_IMAGE.is_file():
                    self._json(404, {"error": "트렌드 기획 데모 이미지를 찾을 수 없습니다."})
                else:
                    self._send(200, TREND_DEMO_IMAGE.read_bytes(), "image/png")
            elif path == "/api/image-generation-status":
                settings = load_settings()
                self._json(200, {
                    "api_key_present": bool(settings.image_generation_api_key),
                    "enabled": settings.image_generation_enabled,
                    "model": DEFAULT_IMAGE_MODEL,
                    "comparison_models": list(COMPARISON_IMAGE_MODELS),
                })
            elif path.startswith("/api/generated-images/"):
                filename = Path(path.removeprefix("/api/generated-images/")).name
                target = (GENERATED_IMAGE_ROOT / filename).resolve()
                if GENERATED_IMAGE_ROOT.resolve() not in target.parents or not target.is_file():
                    self._json(404, {"error": "생성 이미지를 찾을 수 없습니다."})
                else:
                    mime, _ = mimetypes.guess_type(target.name)
                    self._send(200, target.read_bytes(), mime or "application/octet-stream")
            elif path == "/api/bootstrap":
                self._json(200, {
                    "brief": repository.get_brief(),
                    "brief_versions": repository.list_brief_versions(),
                    "variants": repository.list_variants(), "evaluations": repository.list_evaluations(),
                })
            elif path.startswith("/api/variants/") and path.endswith(".svg"):
                variant_id = path.removeprefix("/api/variants/").removesuffix(".svg")
                image = repository.get_variant_image(variant_id)
                if image is None:
                    self._json(404, {"error": "시안을 찾을 수 없습니다."})
                else:
                    self._send(200, image.encode("utf-8"), "image/svg+xml; charset=utf-8")
            elif path == "/" or path.startswith("/assets/"):
                relative = "index.html" if path == "/" else path.removeprefix("/assets/")
                target = (WEB_ROOT / relative).resolve()
                if WEB_ROOT.resolve() not in target.parents and target != WEB_ROOT.resolve():
                    self._json(404, {"error": "Not found"})
                    return
                if not target.is_file():
                    self._json(404, {"error": "Not found"})
                    return
                mime, _ = mimetypes.guess_type(target.name)
                charset = "; charset=utf-8" if mime and (mime.startswith("text/") or mime in {"application/javascript", "application/json"}) else ""
                self._send(200, target.read_bytes(), (mime or "application/octet-stream") + charset)
            else:
                self._json(404, {"error": "Not found"})
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self._json(500, {"error": str(exc)})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            payload = self._body()
            if path == "/api/planning-draft":
                self._json(200, _build_planning_draft_response(payload))
            elif path == "/api/concept-image":
                if payload.get("confirm_image_generation") is not True:
                    raise ValueError("실제 OpenAI 이미지 생성을 확인하려면 확인란을 체크해 주세요.")
                models = payload.get("models")
                if not isinstance(models, list) or not models:
                    raise ValueError("비교할 이미지 모델을 하나 이상 선택해 주세요.")
                models = list(dict.fromkeys(str(model) for model in models))
                if len(models) > len(COMPARISON_IMAGE_MODELS) or any(model not in COMPARISON_IMAGE_MODELS for model in models):
                    raise ValueError("지원하지 않는 비교 모델이 포함되어 있습니다.")
                settings = load_settings()
                if not settings.image_generation_enabled:
                    raise ValueError("이미지 생성 기능이 비활성 상태입니다. 서버를 VOGUE_IMAGE_GENERATION_ENABLED=true로 실행해 주세요.")
                if not settings.image_generation_api_key:
                    raise ValueError("OPENAI_API_KEY가 설정되지 않았습니다.")
                request_id = "ui-outdoor-jeans-" + os.urandom(4).hex()
                schema = "internal-prototype-0"
                query = str(payload.get("original_query", "")).strip()[:500]
                season = str(payload.get("season", "")).strip()[:40]
                category = str(payload.get("category", "")).strip()[:80]
                trend_name = str(payload.get("trend_name", "")).strip()[:160]
                color = str(payload.get("trend_color", "")).strip()[:100]
                pattern = str(payload.get("trend_pattern", "")).strip()[:120]
                color_evidence = str(payload.get("color_evidence_id", "")).strip()[:160]
                pattern_evidence = str(payload.get("pattern_evidence_id", "")).strip()[:160]
                inventory_note = str(payload.get("inventory_note", "")).strip()[:300]
                inventory_evidence = str(payload.get("inventory_evidence_id", "")).strip()[:160]
                try:
                    quantity = int(payload.get("inventory_quantity"))
                except (ValueError, TypeError) as exc:
                    raise ValueError("재고 시연 수량은 정수로 입력해 주세요.") from exc
                as_of = str(payload.get("inventory_as_of", "")).strip()[:40]
                if not all((query, season, category, trend_name, color, pattern, color_evidence, pattern_evidence, inventory_note, inventory_evidence, as_of)):
                    raise ValueError("예시의 요청·트렌드·Evidence·재고 입력값을 모두 채워 주세요.")
                trend_ids = (color_evidence, pattern_evidence)
                request = PlanningRequest(
                    result=AgentResult("user-request", request_id, schema, "ok"),
                    original_query=query, season=season, category=category,
                    field_origins={"season": "user", "category": "user"},
                )
                trend = TrendResult(
                    result=AgentResult("query-trend-agent", request_id, schema, "ok", evidence_ids=trend_ids),
                    candidates=(TrendCandidate(
                        name=trend_name, qualification="candidate", season=season, category=category,
                        attributes=(
                            AttributeSignal("color", color, "evidence_observation", (color_evidence,)),
                            AttributeSignal("pattern", pattern, "evidence_observation", (pattern_evidence,)),
                        ), evidence_ids=trend_ids,
                    ),),
                )
                inventory = InventoryProductResult(
                    result=AgentResult(
                        "own-product-inventory-agent", request_id, schema, "partial",
                        evidence_ids=(inventory_evidence,),
                        limitations=("재고 수량·기준일·Evidence ID는 UI 시연용 가정이며 실제 재고가 아닙니다.",),
                    ),
                    products=(InventoryProduct(
                        style_id="TEST-JEAN-STYLE-001", sku_ids=("TEST-JEAN-SKU-001",),
                        category="denim", product_role="lower_body", quantity=quantity,
                        unit="pieces", inventory_definition="available_to_sell", as_of=as_of,
                        evidence_ids=(inventory_evidence,), note=inventory_note, note_origin="user",
                    ),),
                )
                context = build_planning_context(PlanningInputs(request, trend, inventory))
                results = []
                for model in models:
                    workflow = run_concept_to_image(
                        context,
                        provider=OpenAIImageProvider(api_key=settings.image_generation_api_key, model=model),
                        image_generation_enabled=settings.image_generation_enabled,
                        confirm_image_generation=True,
                    )
                    image_path = Path(workflow.image.image_path) if workflow.image.image_path else None
                    image_name = image_path.name if image_path else None
                    image_url = f"/api/generated-images/{image_name}" if image_name else None
                    variant = None
                    if workflow.image.status == "generated" and image_url and workflow.image.image_id:
                        variant = repository.save_generated_image_variant(
                            variant_id=workflow.image.image_id,
                            image_type="lookbook",
                            title=f"{season} 아웃도어 상의 × 청바지 · {workflow.image.model}",
                            image_url=image_url,
                            prompt=(
                                "SYSTEM INSTRUCTIONS:\n" + workflow.image.request.system_prompt
                                + "\n\nUSER DESIGN BRIEF:\n" + workflow.image.request.prompt
                            ),
                            model=workflow.image.model or model,
                            evidence_ids=list(workflow.image.request.evidence_ids),
                            prompt_version=workflow.image.request.prompt_version,
                            review_only=workflow.image.review_only,
                        )
                    results.append({
                        "status": workflow.image.status,
                        "provider": workflow.image.provider,
                        "model": workflow.image.model or model,
                        "image_id": workflow.image.image_id,
                        "image_url": image_url,
                        "image_name": image_name,
                        "variant": variant,
                        "review_only": workflow.image.review_only,
                        "prompt_version": workflow.image.request.prompt_version,
                        "prompt_sha256": workflow.image.request.prompt_sha256,
                        "evidence_ids": list(workflow.image.request.evidence_ids),
                        "limitations": list(workflow.image.limitations),
                        "error_code": workflow.image.error_code,
                    })
                successes = sum(result["status"] == "generated" for result in results)
                status = "generated" if successes == len(results) else "partial" if successes else "failed"
                failed_models = [
                    f"{result['model']}: {result['error_code'] or result['status']}"
                    for result in results if result["status"] != "generated"
                ]
                self._json(200 if successes else 502, {
                    "status": status,
                    "error": None if successes else "이미지 생성에 실패했습니다. " + "; ".join(failed_models),
                    "requested_models": models,
                    "results": results,
                    "conflicts": [conflict.message for conflict in context.conflicts],
                    "limitations": [limit for result in results for limit in result["limitations"]],
                })
            elif path == "/api/brief":
                self._json(201, repository.save_brief(payload))
            elif path == "/api/variants":
                brief = repository.get_brief()
                requested_version = payload.get("brief_version")
                if requested_version != brief["version"]:
                    raise ValueError("브리프가 변경되었습니다. 최신 버전을 저장한 뒤 시안을 만들어 주세요.")
                self._json(201, {"variants": repository.generate_variant(payload, str(payload.get("image_type", "product")), int(payload.get("count", 3)))})
            elif path == "/api/evaluations":
                self._json(201, repository.save_evaluation(payload))
            else:
                self._json(404, {"error": "Not found"})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._json(400, {"error": str(exc)})
        except OSError as exc:
            self._json(500, {"error": str(exc)})


def main() -> None:
    repository.initialize()
    host = os.getenv("VOGUE_HOST", "127.0.0.1")
    port = int(os.getenv("VOGUE_PORT", "8765"))
    server = ThreadingHTTPServer((host, port), PrototypeHandler)
    display_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    print(f"VOGUE planning prototype running at http://{display_host}:{port} (local only)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping local prototype.")
    finally:
        server.server_close()


def _build_planning_draft_response(
    payload: dict,
    *,
    knowledge_retriever: KnowledgeRetriever | None = None,
    retrieval_policy: RetrievalSourcePolicy | None = None,
) -> dict:
    """Build a readable draft from the four upstream planning inputs."""
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

    def context_origin(value) -> str:
        source = value.get("source") if isinstance(value, dict) else None
        return source if source in {"user", "inferred"} else "unknown"

    def attribute_signal(item: dict, *, requested: bool = False) -> AttributeSignal:
        evidence_ids = tuple(item.get("evidence_ids", ()))
        raw_origin = item.get("origin")
        if requested:
            origin = "user_requested" if item.get("source") == "user" else "unknown"
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
            raise ValueError(f"지원하지 않는 입력 상태: {status}")
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
            key: context_origin(raw_context.get(key, request_payload.get(key)))
            for key in ("season", "category", "target_customer")
            if raw_context.get(key, request_payload.get(key)) is not None
        } | request_payload.get("field_origins", {}),
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
        allowed = {
            "style_id": item.get("style_id", item.get("product_id")),
            "sku_ids": tuple(item.get("sku_ids", ())),
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
    sales = payload.get("sales_market_result")
    if sales is not None and not isinstance(sales, dict):
        raise ValueError("sales_market_result는 JSON 객체여야 합니다.")
    context = build_planning_context(PlanningInputs(request, trend, inventory, sales))
    planning_knowledge = retrieve_planning_knowledge(
        context, retriever=knowledge_retriever, policy=retrieval_policy,
    )
    context = replace(
        context,
        planning_knowledge=planning_knowledge,
        limitations=tuple(dict.fromkeys((*context.limitations, *planning_knowledge.limitations))),
    )
    draft, issues = RuleBasedConceptGenerator().generate(context)
    from dataclasses import asdict

    input_sources = {
        "planning_request": request_payload,
        "trend_result": trend_payload,
        "inventory_product_result": inventory_payload,
        "sales_market_result": sales,
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
        else:
            # Project_07 is an opaque handoff: expose only its agreed envelope
            # metadata and keep its full body byte-for-byte equivalent as JSON.
            metadata = {
                "producer_id": source.get("agent_id") if isinstance(source, dict) else None,
                "producer_id_origin": "payload" if isinstance(source, dict) and "agent_id" in source else "absent",
                "source_schema_version": source.get("schema_version") if isinstance(source, dict) else None,
                "schema_version_origin": "payload" if isinstance(source, dict) and "schema_version" in source else "absent",
                "status_origin": "payload" if isinstance(source, dict) and "status" in source else "absent",
            }
        input_evidence[name] = {
            "status": context.input_statuses[name],
            **metadata,
            "evidence_ids": evidence_ids_in(source) if source is not None else [],
            "payload": source,
        }

    draft_data = asdict(draft)
    draft_data["limitations"] = list(dict.fromkeys((
        *draft_data.get("limitations", ()), *planning_knowledge.limitations,
    )))
    draft_data["title"] = f"{draft.season or '시즌 미정'} {draft.category or '카테고리 미정'} 신제품 기획 초안"
    draft_data["review_status"] = "md_review_required"
    image_result = None
    planning_board_result = None
    if payload.get("generate_image") is True:
        image_model = str(payload.get("image_model", "gpt-image-2.5-flare"))
        if image_model not in COMPARISON_IMAGE_MODELS:
            raise ValueError("지원하지 않는 이미지 모델입니다.")
        settings = load_settings()
        workflow = run_concept_to_image(
            context,
            provider=(OpenAIImageProvider(
                api_key=settings.image_generation_api_key or "",
                model=image_model,
            ) if settings.image_generation_api_key else None),
            image_generation_enabled=settings.image_generation_enabled,
            confirm_image_generation=True,
        )
        image_path = Path(workflow.image.image_path) if workflow.image.image_path else None
        image_name = image_path.name if image_path else None
        image_result = {
            "status": workflow.image.status,
            "model": workflow.image.model or image_model,
            "image_url": f"/api/generated-images/{image_name}" if image_name else None,
            "evidence_ids": list(workflow.image.request.evidence_ids),
            "limitations": list(workflow.image.limitations),
            "error_code": workflow.image.error_code,
            "review_only": workflow.image.review_only,
        }
        if payload.get("generate_planning_board") is True:
            board_model = str(payload.get("planning_board_model", "gpt-image-2.5-sunburst"))
            if board_model not in COMPARISON_IMAGE_MODELS:
                raise ValueError("지원하지 않는 기획안 보드 이미지 모델입니다.")
            if workflow.image.status != "generated" or not image_path or not image_path.is_file():
                planning_board_result = {
                    "status": "blocked",
                    "model": board_model,
                    "image_url": None,
                    "limitations": ("신제품 예시 이미지가 생성되지 않아 기획안 보드 생성을 건너뛰었습니다.",),
                }
            else:
                try:
                    board_prompt = _build_planning_board_prompt(context, draft, image_path)
                    board_generated = OpenAIImageEditProvider(
                        api_key=settings.image_generation_api_key or "",
                        model=board_model,
                    ).generate_from_reference(
                        board_prompt,
                        image_path.read_bytes(),
                        mime_type="image/png",
                        size="1536x1024",
                    )
                    board_name = f"{image_path.stem}-planning-board.png"
                    board_path = GENERATED_IMAGE_ROOT / board_name
                    board_path.parent.mkdir(parents=True, exist_ok=True)
                    board_path.write_bytes(board_generated.image_bytes)
                    planning_board_result = {
                        "status": "generated",
                        "model": board_generated.model,
                        "image_url": f"/api/generated-images/{board_name}",
                        "reference_image_url": image_result["image_url"],
                        "evidence_ids": list(dict.fromkeys((
                            *context.evidence_ids,
                            *(item.evidence_id for item in planning_knowledge.evidence),
                        ))),
                        "limitations": ["별도 이미지 모델이 만든 시각 요약 보드이며 텍스트 기획서와 MD 검토를 대체하지 않습니다."],
                        "review_only": True,
                    }
                except Exception as exc:
                    error_code = getattr(exc, "code", "PLANNING_BOARD_GENERATION_FAILED")
                    planning_board_result = {
                        "status": "failed",
                        "model": board_model,
                        "image_url": None,
                        "error_code": error_code,
                        "limitations": ["기획안 보드 이미지 생성에 실패했습니다. 신제품 이미지와 텍스트 초안은 유지됩니다."],
                        "review_only": True,
                    }
    return {
        "status": "partial" if context.limitations or context.conflicts or context.input_statuses.get("sales_market_result") != "ok" else "ok",
        "request_id": context.request_id,
        "input_statuses": dict(context.input_statuses),
        "draft": draft_data,
        "planning_knowledge": _planning_knowledge_payload(planning_knowledge),
        "input_evidence": input_evidence,
        "stock_trend_results": [asdict(item) for item in inventory.trend_results],
        "image": image_result,
        "planning_board": planning_board_result,
        "validation_issues": [asdict(issue) for issue in issues],
        "evidence_ids": list(context.evidence_ids),
        "limitations": list(context.limitations),
        "conflicts": [asdict(conflict) for conflict in context.conflicts],
        "questions_for_validation": list(context.questions_for_validation),
    }


def _planning_knowledge_payload(knowledge) -> dict:
    """Serialize permitted retrieval references without leaking date objects."""
    return {
        "by_purpose": [
            {
                "purpose": result.purpose,
                "status": result.status,
                "query_plan_version": result.query_plan_version,
                "limitations": list(result.limitations),
                "index_version": result.index_version,
                "retrieval_run_id": result.retrieval_run_id,
                "evidence": [
                    {
                        "evidence_id": item.evidence_id,
                        "source_id": item.source_id,
                        "source_type": item.source_type,
                        "source_name": item.source_name,
                        "locator": item.locator,
                        "quote": item.quote,
                        "source_date": item.source_date.isoformat() if item.source_date else None,
                        "permission_status": item.permission_status,
                        "permitted_uses": list(item.permitted_uses),
                        "content_hash": item.content_hash,
                        "matched_by": item.matched_by,
                        "verified": item.verified,
                    }
                    for item in result.evidence
                ],
                "kg_paths": [
                    {
                        "nodes": list(path.nodes),
                        "relationships": list(path.relationships),
                        "taxonomy_version": path.taxonomy_version,
                        "evidence_ids": list(path.evidence_ids),
                    }
                    for path in result.kg_paths
                ],
            }
            for result in knowledge.by_purpose
        ],
        "evidence_ids": [item.evidence_id for item in knowledge.evidence],
        "limitations": list(knowledge.limitations),
    }


def _build_planning_board_prompt(context, draft, product_image_path: Path) -> str:
    """Create a concise image-edit prompt for the separate one-page visual brief."""
    trend_names = [
        f"{candidate.name} [Evidence: {', '.join(candidate.evidence_ids) or 'Evidence 미연결'}]"
        for candidate in context.trends.candidates if candidate.name.strip()
    ]
    evidenced_attributes = [
        f"{item.name}={item.value} [Evidence: {', '.join(item.evidence_ids)}]"
        for item in draft.attributes
        if item.value is not None and item.evidence_ids
    ]
    requested_attributes = [
        f"{item.name}={item.value}"
        for item in context.request.requested_attributes
        if item.value is not None
    ]
    inventory = [
        f"{claim.value} [Evidence: {', '.join(claim.evidence_ids) or '없음'}]"
        for claim in draft.relation_to_own_products
        if claim.value and claim.kind == "evidence_observation"
    ]
    market_usable = context.input_statuses.get("sales_market_result") in {"ok", "partial"}
    sales_status = context.input_statuses.get("sales_market_result", "not_provided")
    planning_reference_lines = {}
    if context.planning_knowledge is not None:
        for result in context.planning_knowledge.by_purpose:
            if result.purpose not in {"planning_reference", "precedent", "taxonomy"}:
                continue
            for reference in result.evidence:
                if reference.quote:
                    planning_reference_lines.setdefault(
                        reference.evidence_id,
                        f"{reference.source_name or reference.source_id}: {reference.quote} "
                        f"[Evidence: {reference.evidence_id}]",
                    )
    return f"""Create a polished 16:10 landscape merchandising proposal board in Korean using the supplied image as the exact new-product visual. Keep the garment in the reference image recognizable and unchanged. The reference image must appear prominently in the right third of the board as the new-product example; include a smaller detail crop beside or below it. Do not invent a different garment.

Visual direction based on the provided reference: premium fashion merchandising presentation, white cards on a pale gray canvas, deep forest-green header, fine separators, restrained editorial typography, compact evidence cards. Build a clear three-column grid: left column for request and trend, center column for stock/market implications and decisions, right column for the product image. Add a slim top process strip labelled ISSUE → INSIGHT → PROPOSAL. Keep labels short and legible. No brand logos or fabricated retailer logos.

Use only these supplied planning facts and keep numbers exact:
- Title: {context.request.season or '시즌 미정'} {context.request.category or '카테고리 미정'} 신상품 기획안
- Request: {context.request.original_query or '요청 미제공'}
- Target: {context.request.target_customer or '미정'}
- Trend input: {', '.join(trend_names) or '없음'}
- Evidence-backed design observations: {'; '.join(evidenced_attributes) or '미제공'}
- User-requested attributes: {'; '.join(requested_attributes) or '미제공'}
- Inventory relationship facts: {'; '.join(inventory) or '재고 관계 미제공'}
- Sales/market input status: {sales_status}
- Sales/market interpretation: 상세 필드는 이 이미지 프롬프트에서 해석하지 않음. 전체 전달값과 Evidence는 원문 payload에서 확인.
- Approved planning references: {'; '.join(planning_reference_lines.values()) or '검색 결과 없음'}
- Evidence instruction: render each Evidence ID beside only the exact observation or upstream result where it appears above. Do not imply a detached Evidence ID supports unrelated facts.

Separate observations from proposals. Add a small note: MD 검토용 초안 · 자동 승인 아님. Do not convert inventory into demand, sales observations into forecasts, or test values into real business facts. Preserve all numbers exactly as provided. Avoid adding any unsupported product attributes. Use Korean labels, but if exact long text cannot fit, prioritize concise headings and Evidence IDs over decorative copy."""


if __name__ == "__main__":
    main()
