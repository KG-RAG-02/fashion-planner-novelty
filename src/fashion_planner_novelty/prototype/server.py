"""Project_08-facing planning API server; stdlib HTTP adapter."""

from __future__ import annotations

import base64
import json
import hmac
import hashlib
import os
import re
import ssl
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from threading import BoundedSemaphore
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from ..adapters.draft_inputs import WorkflowInputError, normalize_workflow_inputs
from ..domain.generator import RuleBasedConceptGenerator
from ..settings import load_settings
from ..sources.openai_text_provider import OpenAIResponsesTextProvider
from ..workflows.planning_draft import (
    _analyze_planning_inputs, _is_recovered_category_lookup_warning, _stock_article_id,
)
from ..workflows.text_concept_generation import PromptedConceptGenerator
from ..workflows.draft_artifacts import (
    DraftArtifactStore,
    ImageRunAlreadyClaimed,
    OpenAIDraftImageProvider,
    RequestReplayConflict,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MAX_RUN_BODY_BYTES = 1_000_000
IMAGE_REQUEST_SLOT = BoundedSemaphore(1)
IMAGE_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="p06-image")


def _env_flag(name: str, *, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _build_concept_generator() -> PromptedConceptGenerator:
    """Build the opt-in text generator used by the active /runs route."""
    fallback = RuleBasedConceptGenerator()
    if not _env_flag("VOGUE_TEXT_GENERATION_ENABLED", default=True):
        return PromptedConceptGenerator(enabled=False, fallback=fallback)

    settings = load_settings()
    provider = None
    if settings.image_generation_api_key:
        provider = OpenAIResponsesTextProvider(
            settings.image_generation_api_key,
            model=os.getenv("VOGUE_TEXT_GENERATION_MODEL", "gpt-6-luna"),
        )
    return PromptedConceptGenerator(provider=provider, enabled=True, fallback=fallback)


def _safe_image_error_code(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    if isinstance(code, str) and re.fullmatch(r"[A-Z0-9_]{1,64}", code):
        return code
    return "IMAGE_GENERATION_FAILED"


def _timed_image_call(provider, kind: str, profile: dict, request_id: str,
                      reference_image: bytes | None = None,
                      companion: dict | None = None) -> tuple[bytes | None, int, str | None]:
    started = time.perf_counter()
    try:
        if reference_image is None:
            image_bytes = provider.generate(kind, profile, request_id)
        elif companion is None:
            image_bytes = provider.generate(kind, profile, request_id, reference_image=reference_image)
        else:
            image_bytes = provider.generate(kind, profile, request_id, reference_image=reference_image,
                                            companion=companion)
        return image_bytes, round((time.perf_counter() - started) * 1000), None
    except Exception as exc:
        return None, round((time.perf_counter() - started) * 1000), _safe_image_error_code(exc)


_COMPANION_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
_COMPANION_IMAGE_MAX_BYTES = 4 * 1024 * 1024


def _companion_photo(stock_payload: object, companion) -> tuple[bytes | None, str | None]:
    """The stock item's photo from the received stock result: its own entry first, else the first entry of the
    same style_id that still carries one (P08's p06-input/2 view sends each product's photo once)."""
    products = stock_payload.get("products") if isinstance(stock_payload, dict) else None
    if companion is None or not isinstance(products, list):
        return None, None
    own = [products[companion.product_index]] if 0 <= companion.product_index < len(products) else []
    same_style = [item for item in products
                  if isinstance(item, dict) and companion.style_id and item.get("style_id") == companion.style_id]
    for item in (*own, *same_style):
        image = item.get("image") if isinstance(item, dict) else None
        if not isinstance(image, dict) or not isinstance(image.get("data"), str):
            continue
        media_type = image.get("media_type")
        if media_type not in _COMPANION_IMAGE_TYPES or image.get("encoding", "base64") != "base64":
            continue
        try:
            data = base64.b64decode(image["data"], validate=True)
        except (ValueError, TypeError):
            continue
        if data and len(data) <= _COMPANION_IMAGE_MAX_BYTES:
            return data, media_type
    return None, None


def _safe_completion_log(request_id: str, status: str, issues: list[dict], visuals: dict, timings: dict) -> None:
    event = {
        "event": "p06_draft_completed",
        "request_id": request_id,
        "status": status,
        "partial_issue_codes": sorted({item.get("code") for item in issues if isinstance(item.get("code"), str)}),
        "visuals": {kind: {"status": item.get("status"), "provider_calls": item.get("provider_calls"),
                           "error_code": item.get("error_code")} for kind, item in visuals.items()},
        "timings_ms": timings,
    }
    print(json.dumps(event, ensure_ascii=False, separators=(",", ":")), file=sys.stderr, flush=True)


def _canonical_sha(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _image_profile_from_draft(draft: dict) -> dict[str, object]:
    """Project only image-usable claims from the analyzed product profile."""
    profile = draft.get("product_profile")
    if not isinstance(profile, dict):
        return {}
    allowed_kinds = {"user_requested", "evidence_observation", "proposal"}
    image_profile: dict[str, object] = {
        key: claim["value"]
        for key, claim in profile.items()
        if key in {"category", "product_type", "gender", "season", "material", "silhouette", "color"}
        and isinstance(claim, dict)
        and claim.get("kind") in allowed_kinds
        and isinstance(claim.get("value"), str)
        and claim["value"].strip()
    }
    details = profile.get("details")
    # The analyzed Draft is built with dataclasses.asdict, which keeps ProductProfile.details a tuple; only the
    # later JSON round trip turns it into a list. Accept both so details always reach the image specification.
    if isinstance(details, (list, tuple)):
        usable_details = [
            item["value"] for item in details
            if isinstance(item, dict)
            and item.get("kind") in allowed_kinds
            and isinstance(item.get("value"), str)
            and item["value"].strip()
        ]
        if usable_details:  # no empty key: a profile without usable details keeps its previous specification
            image_profile["details"] = usable_details
    return image_profile


def _build_handoff_run(payload: object) -> dict:
    """Handle P08's vogue-handoff/0.3 native P06 planning-draft request."""
    total_started = time.perf_counter()
    timings: dict[str, int] = {}
    validation_started = time.perf_counter()
    if not isinstance(payload, dict) or set(payload) != {"contract_version", "request_id", "input"}:
        raise ValueError("요청 envelope에는 contract_version, request_id, input만 있어야 합니다.")
    if payload.get("contract_version") != "vogue-handoff/0.3":
        raise ValueError("지원하지 않는 contract_version입니다.")
    request_id = payload.get("request_id")
    if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", request_id):
        raise ValueError("request_id 형식이 올바르지 않습니다.")
    normalized = normalize_workflow_inputs(request_id, payload.get("input"))
    timings["input_validation_and_normalization"] = round((time.perf_counter() - validation_started) * 1000)
    source_sha = _canonical_sha(payload)
    store = DraftArtifactStore(os.getenv("VOGUE_DRAFT_ARTIFACT_DIR", str(REPOSITORY_ROOT / "data/local/p06-artifacts")))
    cached = store.replay(request_id, source_sha)
    if cached is not None:
        return cached

    analysis_input = {"request_id": request_id, **normalized.normalized_inputs}
    analysis_started = time.perf_counter()
    result = _analyze_planning_inputs(analysis_input, concept_generator=_build_concept_generator(),
                                      include_outfit_companion=True)
    companion = result.pop("outfit_companion", None)
    timings["planning_draft_analysis"] = round((time.perf_counter() - analysis_started) * 1000)
    source_limitations = tuple(result["limitations"])
    # Keep exact received upstream bytes and schema versions beside the internal normalized model.
    for name, source in normalized.source_inputs.items():
        evidence = result["input_evidence"][name]
        evidence["payload"] = source
        evidence["source_schema_version"] = source.get("schema_version")
        evidence["internal_schema_version"] = normalized.normalized_inputs[name].get("schema_version")
    result["compatibility"] = normalized.provenance

    analysis_was_partial = result["status"] == "partial"
    draft = result["draft"]
    draft["review_status"] = "md_review_required"
    draft["limitations"] = list(dict.fromkeys([*draft.get("limitations", []), *result["limitations"]]))
    result["limitations"] = draft["limitations"]
    image_profile = _image_profile_from_draft(draft)

    provider_name = os.getenv("VOGUE_DRAFT_IMAGE_PROVIDER", "").strip().lower()
    visuals: dict[str, dict] = {}
    image_timings: dict[str, int] = {}
    artifact_timings: dict[str, int] = {}
    image_model = os.getenv("VOGUE_DRAFT_IMAGE_MODEL", "gpt-image-2.5-sunburst").strip() or "gpt-image-2.5-sunburst"
    image_specification_sha256 = _canonical_sha(image_profile)
    if not image_profile.get("category"):
        visuals = {kind: {"status": "skipped", "artifact": None, "provider_calls": 0,
                          "model": None, "prompt_version": OpenAIDraftImageProvider.prompt_version,
                          "reason": "product category is unresolved", "error_code": "PRODUCT_CATEGORY_UNRESOLVED"}
                   for kind in ("product", "outfit")}
    elif provider_name == "openai":
        settings = load_settings()
        if settings.image_generation_api_key:
            try:
                timeout_seconds = int(os.getenv("VOGUE_DRAFT_IMAGE_TIMEOUT_SECONDS", "180"))
            except ValueError:
                timeout_seconds = 180
            timeout_seconds = max(5, min(timeout_seconds, 300))
            provider = OpenAIDraftImageProvider(settings.image_generation_api_key, image_model, timeout_seconds)
            if not IMAGE_REQUEST_SLOT.acquire(blocking=False):
                for kind in ("product", "outfit"):
                    visuals[kind] = {"status": "failed", "artifact": None, "provider_calls": 0,
                                     "model": image_model, "prompt_version": provider.prompt_version,
                                     "reason": "image generation capacity is busy", "error_code": "IMAGE_CAPACITY_BUSY"}
            else:
                try:
                    store.claim_image_run(request_id, source_sha)
                except ImageRunAlreadyClaimed:
                    IMAGE_REQUEST_SLOT.release()
                    # The original request may have committed after the first
                    # replay lookup but before this paid-work claim.
                    cached = store.replay(request_id, source_sha)
                    if cached is not None:
                        return cached
                    raise
                except Exception:
                    IMAGE_REQUEST_SLOT.release()
                    raise
                image_started = time.perf_counter()
                try:
                    def call_image(kind: str, reference_image: bytes | None = None,
                                   companion_input: dict | None = None) -> tuple[bytes | None, str | None]:
                        call_started = time.perf_counter()
                        future = IMAGE_EXECUTOR.submit(
                            _timed_image_call, provider, kind, image_profile, request_id, reference_image,
                            companion_input,
                        )
                        try:
                            image_bytes, image_timings[kind], error_code = future.result(timeout=timeout_seconds + 10)
                        except FutureTimeoutError:
                            future.cancel()
                            image_bytes, error_code = None, "IMAGE_API_TIMEOUT"
                            image_timings[kind] = round((time.perf_counter() - call_started) * 1000)
                        return image_bytes, error_code

                    def record_visual(kind: str, image_bytes: bytes | None, error_code: str | None) -> None:
                        if image_bytes is None:
                            visuals[kind] = {"status": "failed", "artifact": None, "provider_calls": 1,
                                             "model": image_model, "prompt_version": provider.prompt_version,
                                             "reason": error_code or "IMAGE_GENERATION_FAILED", "error_code": error_code or "IMAGE_GENERATION_FAILED"}
                            return
                        artifact_started = time.perf_counter()
                        try:
                            artifact = store.put(request_id, kind, image_bytes)
                            visuals[kind] = {"status": "generated", "artifact": artifact, "provider_calls": 1,
                                             "model": image_model, "prompt_version": provider.prompt_version, "reason": None}
                        except Exception:
                            visuals[kind] = {"status": "failed", "artifact": None, "provider_calls": 1,
                                             "model": image_model, "prompt_version": provider.prompt_version,
                                             "reason": "ARTIFACT_PERSISTENCE_FAILED", "error_code": "ARTIFACT_PERSISTENCE_FAILED"}
                        artifact_timings[kind] = round((time.perf_counter() - artifact_started) * 1000)

                    # Sequential, never concurrent (VOGUE decision 2026-11-17): the outfit edits the generated product
                    # image, so it starts only after that image exists and is stored. Without it the outfit could show
                    # a different garment, so it is skipped instead of being generated from text alone.
                    product_bytes, product_error = call_image("product")
                    record_visual("product", product_bytes, product_error)
                    if visuals["product"]["status"] == "generated":
                        # The outfit pairs the new product with one stock item (VOGUE decision 2026-11-17).
                        companion_image, companion_media_type = _companion_photo(
                            normalized.source_inputs.get("inventory_product_result"), companion)
                        companion_input = None if companion is None else {
                            "specification": companion.specification(), "role": companion.role,
                            "image": companion_image, "media_type": companion_media_type,
                        }
                        outfit_bytes, outfit_error = call_image("outfit", product_bytes, companion_input)
                        record_visual("outfit", outfit_bytes, outfit_error)
                        visuals["outfit"]["reference_image_sha256"] = visuals["product"]["artifact"]["sha256"]
                        visuals["outfit"]["companion"] = None if companion is None else {
                            "stock_product_id": companion.style_id, "category": companion.category,
                            "trend_style_id": companion.trend_style_id, "rank": companion.rank,
                            "role": companion.role, "selection_rule": companion.selection_rule,
                            "image_sha256": hashlib.sha256(companion_image).hexdigest() if companion_image else None,
                            "image_media_type": companion_media_type,
                        }
                    else:
                        visuals["outfit"] = {"status": "skipped", "artifact": None, "provider_calls": 0,
                                             "model": image_model, "prompt_version": provider.prompt_version,
                                             "reason": "the product image was not generated, so its outfit edit was not requested",
                                             "error_code": "OUTFIT_REFERENCE_UNAVAILABLE"}
                    timings["image_generation_wall"] = round((time.perf_counter() - image_started) * 1000)
                finally:
                    IMAGE_REQUEST_SLOT.release()
        else:
            visuals = {kind: {"status": "failed", "artifact": None, "provider_calls": 0,
                              "model": image_model, "prompt_version": OpenAIDraftImageProvider.prompt_version,
                              "reason": "image provider credentials are unavailable", "error_code": "IMAGE_API_KEY_MISSING"}
                       for kind in ("product", "outfit")}
    else:
        not_configured = not provider_name
        visuals = {kind: {
            "status": "skipped" if not_configured else "failed",
            "artifact": None,
            "provider_calls": 0,
            "model": None,
            "prompt_version": OpenAIDraftImageProvider.prompt_version,
            "reason": "real image provider is not configured" if not_configured else "configured image provider is unsupported",
            "error_code": "IMAGE_PROVIDER_NOT_CONFIGURED" if not_configured else "IMAGE_PROVIDER_UNSUPPORTED",
        } for kind in ("product", "outfit")}
    for visual in visuals.values():
        visual["product_specification_sha256"] = image_specification_sha256
        visual["specification_alignment"] = "same_product_profile"
        visual["visual_consistency"] = "not_automatically_verified"
    draft["visuals"] = visuals
    visual_limitations = []
    if any(item["status"] != "generated" for item in visuals.values()):
        visual_limitations.append("product/outfit 시각자료를 모두 실제 이미지 provider로 생성하지 못했습니다.")
    visual_limitations.append("outfit 이미지는 먼저 생성한 product 이미지를 참조 입력으로 편집해 같은 상품을 착장으로 표현하지만, 두 이미지의 시각적 동일성은 자동 검증하지 않습니다.")
    draft["limitations"] = list(dict.fromkeys([*draft["limitations"], *visual_limitations]))
    result["limitations"] = draft["limitations"]
    # Deliverable-based status (VOGUE integration decision 2026-11-13, reapplied 2026-11-16): ok when the Draft and
    # both visuals were produced and every upstream input was ok. Analysis gaps and upstream limitation notes stay
    # in limitations and validation_issues; they no longer turn a complete deliverable into partial.
    if result["status"] in {"ok", "partial"}:
        produced = all(item["status"] == "generated" for item in visuals.values())
        upstream_ok = all(status == "ok" for status in result["input_statuses"].values())
        result["status"] = "ok" if produced and upstream_ok else "partial"

    issues = result["validation_issues"]
    for input_name, input_status in result["input_statuses"].items():
        if input_status != "ok":
            issues.append({"path": f"input_statuses.{input_name}", "code": f"UPSTREAM_{str(input_status).upper()}",
                           "message": f"{input_name} returned status {input_status}."})
    for input_name, evidence in result["input_evidence"].items():
        if evidence.get("errors"):
            issues.append({"path": f"input_evidence.{input_name}.errors", "code": "UPSTREAM_ERRORS_PRESENT",
                           "message": f"{input_name} contains upstream errors; see preserved input evidence."})
        if evidence.get("missing_data"):
            issues.append({"path": f"input_evidence.{input_name}.missing_data", "code": "UPSTREAM_DATA_MISSING",
                           "message": f"{input_name} reports missing data; see preserved input evidence."})
    if result["conflicts"]:
        issues.append({"path": "conflicts", "code": "INPUT_CONFLICTS_PRESENT",
                       "message": "Conflicting input claims were retained; see conflicts."})
    if any(not _is_recovered_category_lookup_warning(item) for item in source_limitations):
        issues.append({"path": "limitations", "code": "INPUT_LIMITATION_PRESENT",
                       "message": "An unresolved input limitation may affect the draft; see limitations and source input evidence."})
    if analysis_was_partial:
        issues.append({"path": "limitations", "code": "PLANNING_ANALYSIS_PARTIAL",
                       "message": "Planning output has a material input, mapping, conflict, required-field, or validation issue; inspect the other validation issue codes."})
    for kind, visual in visuals.items():
        error_code = visual.get("error_code")
        if visual["status"] in {"failed", "skipped"}:
            error_code = error_code or ("IMAGE_CAPACITY_BUSY" if visual["provider_calls"] == 0 else "IMAGE_GENERATION_FAILED")
            visual["error_code"] = error_code
            issues.append({"path": f"draft.visuals.{kind}", "code": error_code,
                           "message": f"{kind} image was not generated; inspect the safe error code and use a new request ID to retry a completed request."})
            result["limitations"].append(f"{kind} image unavailable ({error_code}).")
    result["limitations"] = list(dict.fromkeys(result["limitations"]))
    draft["limitations"] = result["limitations"]
    result["generation_metadata"]["image_provider"] = provider_name or "none"
    result["generation_metadata"]["image_model"] = image_model if provider_name == "openai" else None
    result["generation_metadata"]["image_specification_sha256"] = image_specification_sha256
    result["generation_metadata"]["image_call_policy"] = (
        "sequential: product generation, then outfit edit of the product image; no automatic retry")
    result["generation_metadata"]["timings_ms"] = {
        **timings,
        "product_image_generation": image_timings.get("product", 0),
        "outfit_image_generation": image_timings.get("outfit", 0),
        "image_generation_wall": timings.get("image_generation_wall", 0),
        "product_artifact_persistence": artifact_timings.get("product", 0),
        "outfit_artifact_persistence": artifact_timings.get("outfit", 0),
    }

    result["planning_analysis"] = {
        "interpretations": [claim for claim in [draft.get("opportunity"), draft.get("target_customer")] if claim],
        "proposals": [draft.get("product_definition")] if draft.get("product_definition") else [],
        "unresolved_questions": result["questions_for_validation"],
        "limitations": result["limitations"],
    }
    result["image"] = visuals["product"]
    result["outfit_image"] = visuals["outfit"]
    result["planning_board"] = None  # Board composition belongs to P08.
    response = {"contract_version": "vogue-handoff/0.3", "request_id": request_id,
                "producer": {"agent_id": "new-product-agent", "schema_version": "1.0"},
                "status": result["status"], "result": result}
    serialization_started = time.perf_counter()
    # Validate serializability and measure it without materializing a second copy
    # of the full response. The artifact cache and HTTP adapter serialize it later.
    json.dumps(response, ensure_ascii=False)
    timings["response_serialization"] = round((time.perf_counter() - serialization_started) * 1000)
    timings["total_processing"] = round((time.perf_counter() - total_started) * 1000)
    result["generation_metadata"]["timings_ms"].update(timings)
    # Keep the returned object identical to its JSON wire representation (e.g. tuples become arrays).
    response = json.loads(json.dumps(response, ensure_ascii=False))
    cache_started = time.perf_counter()
    response = store.save_response(request_id, source_sha, response)
    timings["response_cache_persistence"] = round((time.perf_counter() - cache_started) * 1000)
    timings["total_processing_including_cache"] = round((time.perf_counter() - total_started) * 1000)
    _safe_completion_log(request_id, result["status"], result["validation_issues"], visuals,
                         {**result["generation_metadata"]["timings_ms"], **timings})
    return response


class PrototypeHandler(BaseHTTPRequestHandler):
    server_version = "VOGUEPlanningWorkflow/1.0"

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
        serialization_started = time.perf_counter()
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        serialization_ms = round((time.perf_counter() - serialization_started) * 1000)
        producer = payload.get("producer") if isinstance(payload, dict) else None
        if (isinstance(producer, dict) and producer.get("agent_id") == "new-product-agent"
                and isinstance(payload.get("request_id"), str)):
            event = {
                "event": "p06_http_response_serialized",
                "request_id": payload["request_id"],
                "status": payload.get("status"),
                "http_status": status,
                "http_response_serialization_ms": serialization_ms,
            }
            print(json.dumps(event, ensure_ascii=False, separators=(",", ":")), file=sys.stderr, flush=True)
        self._send(status, content, "application/json; charset=utf-8")

    def _error(self, status: int, code: str, message: str) -> None:
        self._json(status, {"error": {"code": code, "message": message}})

    def _authorized_service_request(self) -> bool:
        mode = os.getenv("VOGUE_HTTP_MODE", "")
        if mode not in {"local", "service", "private"}:
            return False
        if mode == "local":
            try:
                if self.client_address[0] not in {"127.0.0.1", "::1"}:
                    return False
            except (AttributeError, IndexError):
                return False
        expected = os.getenv("VOGUE_AGENT_SERVICE_BEARER_TOKEN", "")
        supplied = self.headers.get("Authorization", "")
        return bool(expected) and hmac.compare_digest(supplied, f"Bearer {expected}")

    def do_GET(self) -> None:
        if os.getenv("VOGUE_HTTP_MODE") in {"service", "private"} and not self._authorized_service_request():
            self._error(401, "UNAUTHORIZED", "인증이 필요합니다.")
            return
        if urlparse(self.path).path != "/api/health":
            self._error(404, "NOT_FOUND", "Not found")
            return
        self._json(200, {"ok": True, "mode": "new-product-planning"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/v1/agents/new-product-agent/runs":
            self._handle_handoff_run()
            return
        self._error(404, "NOT_FOUND", "Not found")

    def _handle_handoff_run(self) -> None:
        if os.getenv("VOGUE_HTTP_MODE") in {"service", "private"} and not self._authorized_service_request():
            self._error(401, "UNAUTHORIZED", "인증이 필요합니다.")
            return
        if self.headers.get_content_type() != "application/json":
            self._error(415, "UNSUPPORTED_MEDIA_TYPE", "Content-Type application/json이 필요합니다.")
            return
        raw_length = self.headers.get("Content-Length", "")
        if not raw_length.isdigit() or int(raw_length) > MAX_RUN_BODY_BYTES:
            self._error(413 if raw_length.isdigit() else 400, "PAYLOAD_TOO_LARGE" if raw_length.isdigit() else "INVALID_CONTENT_LENGTH", "요청 본문 크기 또는 Content-Length가 올바르지 않습니다.")
            return
        try:
            payload = json.loads(self.rfile.read(int(raw_length)))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._error(400, "INVALID_JSON", "JSON 요청 본문을 읽을 수 없습니다.")
            return
        try:
            response = _build_handoff_run(payload)
        except ImageRunAlreadyClaimed:
            self._error(409, "IMAGE_REQUEST_IN_PROGRESS_OR_OUTCOME_UNKNOWN",
                        "이 request_id의 이미지 요청이 처리 중이거나 결과를 확인할 수 없습니다. 중복 과금을 막기 위해 다시 호출하지 않았습니다.")
            return
        except RequestReplayConflict:
            self._error(409, "REQUEST_ID_REUSED", "같은 request_id가 다른 입력 payload에 이미 사용됐습니다.")
            return
        except WorkflowInputError as exc:
            self._error(422, exc.code, exc.safe_message)
            return
        except ValueError as exc:
            self._error(422, "INVALID_INPUT", str(exc))
            return
        except Exception:
            self._error(500, "INTERNAL_ERROR", "요청을 처리하지 못했습니다.")
            return
        self._json(200, response)

def main() -> None:
    host = os.getenv("VOGUE_HOST", "127.0.0.1")
    port = int(os.getenv("VOGUE_PORT", "8767"))
    mode = os.getenv("VOGUE_HTTP_MODE", "")
    if mode == "local":
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise RuntimeError("VOGUE_HTTP_MODE=local은 loopback host만 허용합니다.")
    elif mode in {"service", "private"}:
        if not os.getenv("VOGUE_AGENT_SERVICE_BEARER_TOKEN"):
            raise RuntimeError(f"{mode} mode requires VOGUE_AGENT_SERVICE_BEARER_TOKEN.")
    if mode == "service":
        cert_file = os.getenv("VOGUE_TLS_CERT_FILE")
        key_file = os.getenv("VOGUE_TLS_KEY_FILE")
        if not cert_file or not key_file:
            raise RuntimeError("service mode requires TLS certificate and key files.")
    elif mode not in {"local", "private"}:
        raise RuntimeError("Set VOGUE_HTTP_MODE=local, private, or service.")
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


if __name__ == "__main__":
    main()
