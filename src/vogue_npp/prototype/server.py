"""Project_08-facing planning API server; stdlib HTTP adapter."""

from __future__ import annotations

import json
import hmac
import mimetypes
import os
import re
import ssl
import urllib.error
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from threading import BoundedSemaphore
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from ..adapters.handoff import (
    CONTRACT_VERSION as HANDOFF_CONTRACT_VERSION,
    INPUT_KEYS as HANDOFF_INPUT_KEYS,
    AdapterCompatibilityError as HandoffCompatibilityError,
    normalize_handoff_inputs,
)
from ..domain.context import (
    AgentResult, AttributeSignal, InventoryProduct, InventoryProductResult, InventoryTrendResult,
    PlanningInputs, PlanningRequest, TrendCandidate, TrendResult,
    build_planning_context,
)
from ..domain.generator import ConceptGenerator
from ..domain.prompt_safety import serialize_untrusted_prompt_data
from ..settings import load_settings
from ..sources.r2_product_images import R2ProductImageSettings, R2ProductImageStore
from ..workflows.image_generation import DEFAULT_IMAGE_DIR, DEFAULT_IMAGE_MODEL, OpenAIImageProvider, run_concept_to_image
from ..workflows.text_concept_generation import PromptedConceptGenerator


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
GENERATED_IMAGE_ROOT = REPOSITORY_ROOT / DEFAULT_IMAGE_DIR
MAX_BODY_BYTES = 1_000_000
HANDOFF_RESULT_SCHEMA_VERSION = "1.0"
HANDOFF_REQUEST_TIMEOUT_SECONDS = 60
HANDOFF_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="project06-handoff")
HANDOFF_SLOTS = BoundedSemaphore(4)
COMPARISON_IMAGE_MODELS = (
    "gpt-image-2.5-sunburst",
    "gpt-image-2.5-flare",
    "gpt-image-2",
)
P06_REVIEW_BRIDGE_CONTRACT_VERSION = "vogue-sales-market-review/0.1-proposal"
P07_SALES_REVIEW_CONTRACT_VERSION = "vogue-sales-market-review/0.2-proposal"


def _build_sales_market_review_payload(payload: dict) -> dict:
    """Validate the P06 draft and build the P07 request for Project_08 to call."""
    if set(payload) != {"contract_version", "request_id", "input"}:
        raise ValueError("review envelope fields are invalid")
    request_id = payload.get("request_id")
    review_input = payload.get("input")
    if payload.get("contract_version") != P06_REVIEW_BRIDGE_CONTRACT_VERSION:
        raise ValueError("unsupported sales-market review contract")
    if not isinstance(request_id, str) or not request_id.strip() or not isinstance(review_input, dict):
        raise ValueError("review request_id and input are required")
    if review_input.get("request_id") != request_id or set(review_input) != {"request_id", "planning_draft"}:
        raise ValueError("review input does not match the request envelope")
    source_draft = review_input.get("planning_draft")
    if (not isinstance(source_draft, dict) or source_draft.get("schema_version") != "1.0"
            or source_draft.get("request_id") != request_id):
        raise ValueError("planning_draft schema_version 1.0 and matching request_id are required")
    draft_body = source_draft.get("draft")
    if not isinstance(draft_body, dict):
        raise ValueError("new-product-agent result must include its PlanningDraft body")
    profile = draft_body.get("product_profile")
    if not isinstance(profile, dict):
        raise ValueError("PlanningDraft product_profile is required for post-planning review")
    known_evidence_ids = source_draft.get("evidence_ids")
    if not isinstance(known_evidence_ids, list) or any(not isinstance(item, str) for item in known_evidence_ids):
        raise ValueError("PlanningDraft evidence_ids are invalid")
    known_evidence_ids = set(known_evidence_ids)

    def profile_value(field: str) -> str | None:
        claim = profile.get(field)
        if not isinstance(claim, dict) or set(claim) != {"value", "kind", "evidence_ids"}:
            raise ValueError(f"PlanningDraft product_profile.{field} is invalid")
        value, kind, evidence_ids = claim["value"], claim["kind"], claim["evidence_ids"]
        if (kind not in {"user_requested", "evidence_observation", "proposal", "hypothesis", "unknown", "to_validate", "interpretation"}
                or not isinstance(evidence_ids, list)
                or any(not isinstance(item, str) or item not in known_evidence_ids for item in evidence_ids)):
            raise ValueError(f"PlanningDraft product_profile.{field} is invalid")
        if value is None or kind not in {"user_requested", "evidence_observation"}:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"PlanningDraft product_profile.{field} is invalid")
        return value.strip()

    category = profile_value("category")
    if not category or category != draft_body.get("category"):
        raise ValueError("PlanningDraft product_profile category is required and must match draft category")
    product = {"category": category}
    for field in ("product_type", "gender", "season", "material"):
        value = profile_value(field)
        if field == "gender" and value is not None and value not in {"women", "men", "unisex", "unknown"}:
            raise ValueError("PlanningDraft product_profile gender is invalid")
        if value:
            product[field] = value
    return {
        "contract_version": P07_SALES_REVIEW_CONTRACT_VERSION,
        "request_id": request_id,
        "input": {"request_id": request_id, "product": product},
    }


def _build_handoff_result(request_id: str, inputs: dict) -> dict:
    """Validate the agreed producer matrix and normalize without mutating source payloads."""
    adapted = normalize_handoff_inputs(request_id, inputs)
    raw_inputs = adapted.source_inputs
    normalized = adapted.normalized_inputs
    draft = _build_planning_draft_response({"request_id": request_id, **normalized})
    trend_evidence = draft["input_evidence"]["trend_result"]
    trend_evidence["payload"] = raw_inputs["trend_result"]
    trend_evidence["internal_schema_version"] = "1.0"
    trend_evidence["source_schema_version"] = "1.1"
    draft["compatibility"] = adapted.provenance
    draft["request_id"] = request_id
    return draft


def _stock_article_id(item: dict) -> str | None:
    """Resolve an article ID from the explicit field or numeric stock SKU."""
    explicit = item.get("article_id")
    if explicit is not None and str(explicit).isdigit():
        return str(explicit)
    sku_ids = item.get("sku_ids", ())
    if isinstance(sku_ids, (list, tuple)):
        return next((str(value) for value in sku_ids if value is not None and str(value).isdigit()), None)
    return None


def load_r2_inventory_image(article_id: str) -> tuple[bytes, str]:
    """Serve one validated H&M image reference for the P08 visual-analysis path."""
    settings = R2ProductImageSettings.from_env()
    if settings is None:
        raise ValueError("R2 product images are not configured")
    try:
        return R2ProductImageStore(settings).load(article_id)
    except ValueError:
        raise ValueError("article_id is invalid") from None
    except Exception:
        raise OSError("R2 image is unavailable") from None


class PrototypeHandler(BaseHTTPRequestHandler):
    server_version = "VOGUEPlanningAPI/0.1"

    def log_message(self, fmt: str, *args: object) -> None:
        # Keep planning requests and review content out of logs.
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

    def _handoff_error(self, status: int, code: str, message: str) -> None:
        self._json(status, {"error": {"code": code, "message": message}})

    def _authorized_handoff(self) -> bool:
        mode = os.getenv("VOGUE_HTTP_MODE", "")
        if mode not in {"local", "service"}:
            return False
        if mode == "local":
            try:
                if self.client_address[0] not in {"127.0.0.1", "::1"}:
                    return False
            except (AttributeError, IndexError):
                return False
        expected = (os.getenv("VOGUE_AGENT_SERVICE_BEARER_TOKEN", "")
                    or os.getenv("VOGUE_SERVICE_BEARER_TOKEN", ""))
        supplied = self.headers.get("Authorization", "")
        return bool(expected) and hmac.compare_digest(supplied, f"Bearer {expected}")

    def do_GET(self) -> None:
        if os.getenv("VOGUE_HTTP_MODE") == "service" and not self._authorized_handoff():
            self._handoff_error(401, "UNAUTHORIZED", "인증이 필요합니다.")
            return
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        try:
            if path == "/api/health":
                self._json(200, {"ok": True, "mode": "new-product-planning"})
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
            elif path.startswith("/api/hm-reference-images/"):
                filename = path.removeprefix("/api/hm-reference-images/")
                match = re.fullmatch(r"(\d{10})\.jpg", filename)
                if not match:
                    self._json(404, {"error": "참조 이미지를 찾을 수 없습니다."})
                else:
                    image, mime = load_r2_inventory_image(match.group(1))
                    self._send(200, image, mime)
            else:
                self._json(404, {"error": "Not found"})
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            if isinstance(exc, OSError):
                self._json(500, {"error": "요청을 처리하지 못했습니다.", "code": "INTERNAL_ERROR"})
                return
            self._json(500, {"error": str(exc)})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/v1/agents/new-product-agent/runs":
            self._handle_handoff()
            return
        if path == "/v1/agents/new-product-agent/sales-market-reviews":
            self._handle_sales_market_review()
            return
        if os.getenv("VOGUE_HTTP_MODE") == "service" and not self._authorized_handoff():
            self._handoff_error(401, "UNAUTHORIZED", "인증이 필요합니다.")
            return
        if path != "/api/planning-draft":
            self._json(404, {"error": "Not found"})
            return
        try:
            if self.headers.get_content_type() != "application/json":
                self._handoff_error(415, "UNSUPPORTED_MEDIA_TYPE", "Content-Type application/json이 필요합니다.")
                return
            payload = self._body()
            self._json(200, _build_planning_draft_response(payload))
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._json(400, {"error": str(exc)})
        except OSError:
            self._json(500, {"error": "요청을 처리하지 못했습니다.", "code": "INTERNAL_ERROR"})

    def _handle_sales_market_review(self) -> None:
        if not self._authorized_handoff():
            self._handoff_error(401, "UNAUTHORIZED", "인증이 필요합니다.")
            return
        if self.headers.get_content_type() != "application/json":
            self._handoff_error(415, "UNSUPPORTED_MEDIA_TYPE", "Content-Type application/json이 필요합니다.")
            return
        try:
            payload = self._body()
            result = _build_sales_market_review_payload(payload)
            self._json(200, result)
        except (ValueError, TypeError, KeyError) as exc:
            self._handoff_error(422, "INVALID_REVIEW_REQUEST", str(exc))

    def _handle_handoff(self) -> None:
        if not self._authorized_handoff():
            self._handoff_error(401, "UNAUTHORIZED", "인증이 필요합니다.")
            return
        if self.headers.get_content_type() != "application/json":
            self._handoff_error(415, "UNSUPPORTED_MEDIA_TYPE", "Content-Type application/json이 필요합니다.")
            return
        try:
            raw_length = self.headers.get("Content-Length")
            if raw_length is None or not raw_length.isdigit():
                self._handoff_error(400, "INVALID_CONTENT_LENGTH", "Content-Length가 필요합니다.")
                return
            length = int(raw_length)
            if length > MAX_BODY_BYTES:
                self._handoff_error(413, "PAYLOAD_TOO_LARGE", "요청 본문 크기 제한을 초과했습니다.")
                return
            self.connection.settimeout(60)
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._handoff_error(400, "INVALID_JSON", "JSON 요청 본문을 읽을 수 없습니다.")
                return
            if not isinstance(payload, dict):
                self._handoff_error(400, "INVALID_JSON", "JSON 객체 형태의 요청이 필요합니다.")
            elif set(payload) != {"contract_version", "request_id", "input"}:
                self._handoff_error(422, "INVALID_ENVELOPE", "필수 envelope 필드 또는 지원되지 않는 최상위 필드입니다.")
            elif payload.get("contract_version") != HANDOFF_CONTRACT_VERSION:
                self._handoff_error(422, "UNSUPPORTED_CONTRACT_VERSION", "지원하지 않는 contract_version입니다.")
            elif not isinstance(payload.get("request_id"), str) or not payload["request_id"].strip():
                self._handoff_error(422, "INVALID_REQUEST_ID", "request_id는 비어 있지 않은 문자열이어야 합니다.")
            elif not isinstance(payload.get("input"), dict) or set(payload["input"]) != HANDOFF_INPUT_KEYS:
                self._handoff_error(422, "INVALID_INPUT", "input에는 합의된 네 producer 입력 필드가 모두 필요합니다.")
            elif not HANDOFF_SLOTS.acquire(blocking=False):
                self._handoff_error(500, "SERVICE_BUSY", "현재 요청을 처리할 수 없습니다.")
            else:
                future = HANDOFF_EXECUTOR.submit(_build_handoff_result, payload["request_id"], payload["input"])
                future.add_done_callback(lambda _: HANDOFF_SLOTS.release())
                try:
                    result = future.result(timeout=HANDOFF_REQUEST_TIMEOUT_SECONDS)
                except FutureTimeoutError:
                    self._handoff_error(500, "REQUEST_TIMEOUT", "요청 처리 시간 제한을 초과했습니다.")
                    return
                self._json(200, {
                    "contract_version": HANDOFF_CONTRACT_VERSION,
                    "request_id": payload["request_id"],
                    "producer": {"agent_id": "new-product-agent", "schema_version": HANDOFF_RESULT_SCHEMA_VERSION},
                    "status": result["status"],
                    "result": result,
                })
        except HandoffCompatibilityError as exc:
            self._handoff_error(422, exc.code, exc.safe_message)
        except (ValueError, TypeError, KeyError, IndexError):
            self._handoff_error(422, "INVALID_PRODUCER_PAYLOAD", "지원된 입력 schema 구조를 처리할 수 없습니다.")
        except (TimeoutError, OSError):
            self._handoff_error(500, "INTERNAL_ERROR", "요청을 처리하지 못했습니다.")
        except Exception:
            self._handoff_error(500, "INTERNAL_ERROR", "요청을 처리하지 못했습니다.")



def main() -> None:
    host = os.getenv("VOGUE_HOST", "127.0.0.1")
    port = int(os.getenv("VOGUE_PORT", "8767"))
    mode = os.getenv("VOGUE_HTTP_MODE", "")
    if mode == "local":
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise RuntimeError("VOGUE_HTTP_MODE=local은 loopback host만 허용합니다.")
    elif mode == "service":
        if not (os.getenv("VOGUE_AGENT_SERVICE_BEARER_TOKEN") or os.getenv("VOGUE_SERVICE_BEARER_TOKEN")):
            raise RuntimeError("service mode requires VOGUE_AGENT_SERVICE_BEARER_TOKEN.")
        cert_file = os.getenv("VOGUE_TLS_CERT_FILE")
        key_file = os.getenv("VOGUE_TLS_KEY_FILE")
        if not cert_file or not key_file:
            raise RuntimeError("service mode requires TLS certificate and key files.")
    else:
        raise RuntimeError("Set VOGUE_HTTP_MODE=local for loopback development or service for HTTPS service mode.")
    server = ThreadingHTTPServer((host, port), PrototypeHandler)
    if mode == "service":
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(os.environ["VOGUE_TLS_CERT_FILE"], os.environ["VOGUE_TLS_KEY_FILE"])
        server.socket = tls.wrap_socket(server.socket, server_side=True)
    display_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    scheme = "https" if mode == "service" else "http"
    print(f"VOGUE planning API running at {scheme}://{display_host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping local prototype.")
    finally:
        server.server_close()


def _build_planning_draft_response(
    payload: dict,
    *,
    concept_generator: ConceptGenerator | None = None,
) -> dict:
    """Build a draft from the planning request, trend, and inventory inputs."""
    settings = load_settings()  # Load .env before feature/source selection.
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
            key: context_origin(raw_context.get(key, request_payload.get(key)))
            for key in ("season", "category", "target_customer")
            if raw_context.get(key, request_payload.get(key)) is not None
        } | request_payload.get("field_origins", {}),
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
    # H&M image references are optional; synthetic catalog and guideline retrieval is removed.
    visual_references = None
    if request.category:
        from ..sources.hm_visual_references import analyze_hm_visual_references
        try:
            from ..sources.r2_hm_catalog import R2HMCatalogSettings, R2HMCatalogStore
            hm_catalog = R2HMCatalogStore(R2HMCatalogSettings.from_env())
        except Exception:
            hm_catalog = None
        if hm_catalog is not None:
            visual_references = analyze_hm_visual_references(
                hm_catalog, category=request.category,
                api_key=settings.image_generation_api_key,
                max_references=max(1, min(int(os.getenv("VOGUE_HM_IMAGE_REFERENCE_LIMIT", "3")), 3)),
            )
    if visual_references and visual_references.get("limitations"):
        draft_data_limitations = visual_references["limitations"]
    else:
        draft_data_limitations = []
    context = replace(context, hm_visual_references=visual_references)
    if concept_generator is None:
        text_provider = None
        text_api_key = getattr(settings, "llm_api_key", None) or getattr(settings, "image_generation_api_key", None)
        if settings.text_generation_enabled and text_api_key:
            from ..sources.openai_text_provider import OpenAIResponsesTextProvider
            text_provider = OpenAIResponsesTextProvider(
                text_api_key,
                model=os.getenv("VOGUE_TEXT_GENERATION_MODEL", "gpt-6-astra"),
            )
        generator = PromptedConceptGenerator(
            provider=text_provider,
            enabled=settings.text_generation_enabled,
        )
    else:
        generator = concept_generator
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
    # The planning endpoint requests one product image; provider activation
    # remains controlled by server settings.
    image_model = str(payload.get("image_model", "gpt-image-2.5-flare"))
    if image_model not in COMPARISON_IMAGE_MODELS:
        raise ValueError("지원하지 않는 이미지 모델입니다.")
    workflow = run_concept_to_image(
        context,
        draft=draft,
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
        "product_specification": asdict(workflow.image.request.product_profile)
            if workflow.image.request.product_profile else None,
        "specification_source": "draft.product_profile",
        "specification_shared_with_draft": workflow.image.request.product_profile == draft.product_profile,
        "rendered_image_consistency": "not_automatically_verified",
        "prompt_version": workflow.image.request.prompt_version,
        "prompt_sha256": workflow.image.request.prompt_sha256,
        "evidence_ids": list(workflow.image.request.evidence_ids),
        "evidence_uses": [asdict(item) for item in workflow.image.request.evidence_uses],
        "excluded_evidence": [asdict(item) for item in workflow.image.request.excluded_evidence],
        "limitations": list(workflow.image.limitations),
        "error_code": workflow.image.error_code,
        "review_only": workflow.image.review_only,
    }

    return {
        "schema_version": "1.0",
        "status": "partial" if context.limitations or context.conflicts else "ok",
        "request_id": context.request_id,
        "input_statuses": dict(context.input_statuses),
        "draft": draft_data,
        "generation_metadata": generation_metadata,
        "planning_analysis": _planning_analysis_payload(context, draft),
        "input_evidence": input_evidence,
        "stock_trend_results": [asdict(item) for item in inventory.trend_results],
        "image": image_result,
        "hm_visual_references": visual_references,
        "validation_issues": [asdict(issue) for issue in issues],
        "evidence_ids": list(context.evidence_ids),
        "limitations": list(context.limitations),
        "conflicts": [asdict(conflict) for conflict in context.conflicts],
        "questions_for_validation": list(context.questions_for_validation),
    }


def _planning_analysis_payload(context, draft) -> dict:
    """Expose only the supplied request/trend/inventory evidence and proposals."""
    visual_analysis = context.hm_visual_references or {}
    observations = []
    for reference in visual_analysis.get("references", []) if isinstance(visual_analysis, dict) else ():
        visual = reference.get("visual_observations") if isinstance(reference, dict) else None
        if isinstance(visual, dict):
            observations.append({
                "claim_type": "external_visual_reference",
                "purpose": "hm_visual_reference",
                "text": visual.get("visual_summary") or ", ".join(visual.get("visible_features", ())),
                "visible_colors": visual.get("visible_colors", []),
                "silhouette": visual.get("silhouette"),
                "visible_details": visual.get("visible_details", []),
                "reference_id": reference.get("reference_id"),
                "evidence_ids": [],
            })
    proposals = []
    for field_name, claim in (("opportunity", draft.opportunity), ("product_definition", draft.product_definition)):
        if claim.value:
            proposals.append({"claim_type": "design_proposal" if claim.kind == "proposal" else claim.kind,
                              "field": field_name, "text": claim.value, "evidence_ids": list(claim.evidence_ids)})
    proposals.extend({"claim_type": "design_proposal" if attribute.kind == "proposal" else attribute.kind,
                      "field": f"attributes.{attribute.name}", "text": str(attribute.value),
                      "evidence_ids": list(attribute.evidence_ids)}
                     for attribute in draft.attributes if attribute.value is not None)
    return {"observations": observations, "hm_visual_reference_analysis": visual_analysis,
            "interpretations": [], "proposals": proposals,
            "unresolved_questions": list(dict.fromkeys((*context.questions_for_validation, *draft.questions_for_validation))),
            "hm_visual_analysis_used": bool(visual_analysis.get("references")),
            "limitations": list(context.limitations)}


if __name__ == "__main__":
    main()
