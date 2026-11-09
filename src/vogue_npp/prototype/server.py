"""Local-only web prototype server; stdlib only, no external provider calls."""

from __future__ import annotations

import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import repository
from ..domain.context import (
    AgentResult, AttributeSignal, InventoryProduct, InventoryProductResult,
    PlanningInputs, PlanningRequest, TrendCandidate, TrendResult,
    build_planning_context,
)
from ..domain.generator import RuleBasedConceptGenerator
from ..settings import load_settings
from ..workflows.image_generation import (
    DEFAULT_IMAGE_DIR, DEFAULT_IMAGE_MODEL, OpenAIImageProvider, run_concept_to_image,
)


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


def _build_planning_draft_response(payload: dict) -> dict:
    """Build a readable draft from the four upstream planning inputs."""
    request_id = str(payload.get("request_id", "")).strip()[:160]
    schema = str(payload.get("schema_version", "internal-prototype-0")).strip()[:80]
    if not request_id or not schema:
        raise ValueError("request_id와 schema_version을 입력해 주세요.")

    request_payload = payload.get("planning_request")
    trend_payload = payload.get("trend_result")
    inventory_payload = payload.get("inventory_product_result")
    if not all(isinstance(value, dict) for value in (request_payload, trend_payload, inventory_payload)):
        raise ValueError("planning_request, trend_result, inventory_product_result JSON 객체가 필요합니다.")

    def result_meta(data: dict, default_agent: str) -> AgentResult:
        status = data.get("status", "ok")
        if status not in {"ok", "partial", "no_results", "error"}:
            raise ValueError(f"지원하지 않는 입력 상태: {status}")
        return AgentResult(
            agent_id=str(data.get("agent_id", default_agent)),
            request_id=str(data.get("request_id", request_id)),
            schema_version=str(data.get("schema_version", schema)),
            status=status,
            evidence_ids=tuple(str(item) for item in data.get("evidence_ids", ())),
            limitations=tuple(str(item) for item in data.get("limitations", ())),
        )

    request = PlanningRequest(
        result=result_meta(request_payload, "user-request"),
        original_query=request_payload.get("original_query"),
        season=request_payload.get("season"),
        market=tuple(request_payload.get("market", ())),
        channel=tuple(request_payload.get("channel", ())),
        category=request_payload.get("category"),
        product_role=request_payload.get("product_role"),
        requested_attributes=tuple(AttributeSignal(**item) for item in request_payload.get("requested_attributes", ())),
        missing_fields=tuple(request_payload.get("missing_fields", ())),
        constraints=tuple(request_payload.get("constraints", ())),
        field_origins=request_payload.get("field_origins", {}),
    )
    trend = TrendResult(
        result=result_meta(trend_payload, "query-trend-agent"),
        candidates=tuple(TrendCandidate(
            name=item["name"], qualification=item.get("qualification", "candidate"),
            season=item.get("season"), market=tuple(item.get("market", ())),
            channel=tuple(item.get("channel", ())), category=item.get("category"),
            attributes=tuple(AttributeSignal(**signal) for signal in item.get("attributes", ())),
            evidence_ids=tuple(item.get("evidence_ids", ())),
        ) for item in trend_payload.get("candidates", ())),
    )
    inventory = InventoryProductResult(
        result=result_meta(inventory_payload, "own-product-inventory-agent"),
        products=tuple(InventoryProduct(
            **{**item,
               "sku_ids": tuple(item.get("sku_ids", ())),
               "market": tuple(item.get("market", ())),
               "channel": tuple(item.get("channel", ())),
               "attributes": tuple(AttributeSignal(**signal) for signal in item.get("attributes", ())),
               "evidence_ids": tuple(item.get("evidence_ids", ())) }
        ) for item in inventory_payload.get("products", ())),
    )
    sales = payload.get("sales_market_result")
    if sales is not None and not isinstance(sales, dict):
        raise ValueError("sales_market_result는 JSON 객체여야 합니다.")
    context = build_planning_context(PlanningInputs(request, trend, inventory, sales))
    draft, issues = RuleBasedConceptGenerator().generate(context)
    from dataclasses import asdict

    draft_data = asdict(draft)
    draft_data["title"] = f"{draft.season or '시즌 미정'} {draft.category or '카테고리 미정'} 신제품 기획 초안"
    draft_data["review_status"] = "md_review_required"
    return {
        "status": "partial" if context.limitations or context.conflicts or context.input_statuses.get("sales_market_result") != "ok" else "ok",
        "request_id": context.request_id,
        "input_statuses": dict(context.input_statuses),
        "draft": draft_data,
        "validation_issues": [asdict(issue) for issue in issues],
        "evidence_ids": list(context.evidence_ids),
        "limitations": list(context.limitations),
        "conflicts": [asdict(conflict) for conflict in context.conflicts],
        "questions_for_validation": list(context.questions_for_validation),
    }


if __name__ == "__main__":
    main()
