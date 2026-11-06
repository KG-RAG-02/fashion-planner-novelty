"""Evidence-aware product concept image prompts and opt-in image providers."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from ..domain.concept import ProductConceptDraft, ValidationIssue
from ..domain.context import ProductPlanningContext
from ..domain.generator import RuleBasedConceptGenerator
from ..domain.analysis import dimension_mismatches
from ..domain.styling import StylingRelationship, display_inventory_label


ImageStatus = Literal["not_requested", "ready", "generated", "blocked", "failed"]
PROMPT_VERSION = "product-concept-image-prompt-v2-designer"
DEFAULT_IMAGE_MODEL = "gpt-image-2.5-sunburst"
DEFAULT_IMAGE_DIR = Path("data/local/generated_images")
IMAGE_DESIGNER_SYSTEM_PROMPT = """역할: 당신은 의류 브랜드의 시니어 패션 디자이너이자 상품기획 협업자입니다.
요청 상품의 용도와 카테고리를 먼저 파악하고, 입력된 사용자 조건과 근거가 확인된 디자인 정보를 중심으로 검토 가능한 상품 콘셉트 이미지를 설계합니다.

작업 원칙:
- 디자인 요소를 색상, 패턴, 실루엣, 소재, 디테일, 비례와 배치로 나누어 생각하고, 서로 어울리는 하나의 일관된 디자인 방향으로 구성합니다.
- 입력 근거가 뒷받침하는 속성은 해당 범위 안에서 반영합니다. 트렌드명만으로 구체적인 소재, 핏, 장식, 고객 특성이나 기능을 추론하지 않습니다.
- 근거로 확인된 정보, 사용자가 지정한 조건, 디자이너의 시각화 제안을 구분합니다. 근거가 없는 세부 디자인은 창의적으로 제안할 수 있지만 검토용 가설로 취급하며 사실이나 확정 사양처럼 표현하지 않습니다.
- 근거가 여러 디자인 요소를 제시하면 우선순위와 시각적 강약을 판단해 과도하게 나열하지 말고, 상품의 용도에 맞는 균형 잡힌 시안을 만듭니다.
- 재고 상품은 요청 상품과 별도 상품으로 유지하고, 입력에 코디 관계가 있으면 착장 맥락으로만 표현합니다. 재고 소진, 수요, 매출 효과를 암시하지 않습니다.
- 결과는 실제 상품 사진, 확정 디자인, 생산 지시가 아닌 MD와 디자이너가 검토할 수 있는 전문적인 콘셉트 시안입니다.
- 이미지 안에 읽을 수 있는 문구, 로고, 브랜드명, 워터마크를 임의로 만들지 않습니다."""
_DESIGN_ATTRIBUTE_NAMES = {
    "color", "colour", "color_group", "colour_group", "색상", "컬러",
    "pattern", "print", "패턴", "프린트", "silhouette", "shape", "실루엣",
    "material", "fabric", "소재", "원단", "fit", "핏", "디테일", "detail",
    "decoration", "장식", "texture", "조직감", "length", "기장",
}


@dataclass(frozen=True)
class ImageGenerationRequest:
    request_id: str
    season: str | None
    category: str | None
    prompt: str
    prompt_version: str
    prompt_sha256: str
    evidence_ids: tuple[str, ...]
    proposal_fields: tuple[str, ...]
    limitations: tuple[str, ...]
    conflicts: tuple[str, ...]
    styling_relationships: tuple[StylingRelationship, ...] = ()
    system_prompt: str = IMAGE_DESIGNER_SYSTEM_PROMPT
    purpose: str = "MD/디자이너 검토용 상품 콘셉트 시안"


@dataclass(frozen=True)
class GeneratedImage:
    image_bytes: bytes
    mime_type: str
    provider: str
    model: str


@dataclass(frozen=True)
class ImageGenerationResult:
    status: ImageStatus
    request: ImageGenerationRequest
    provider: str | None = None
    model: str | None = None
    image_id: str | None = None
    image_path: str | None = None
    limitations: tuple[str, ...] = ()
    error_code: str | None = None
    review_only: bool = True


@dataclass(frozen=True)
class ConceptImageWorkflowResult:
    draft: ProductConceptDraft
    validation_issues: tuple[ValidationIssue, ...]
    image: ImageGenerationResult


class ImageGenerationProvider(Protocol):
    """A provider that returns one image for a reviewed concept request."""

    def generate(self, request: ImageGenerationRequest) -> GeneratedImage: ...


def build_image_generation_request(
    context: ProductPlanningContext,
    draft: ProductConceptDraft,
) -> ImageGenerationRequest:
    """Build a prompt that separates user scope, evidence, and visual proposals."""
    evidence: list[str] = []
    used_evidence_ids: list[str] = []
    user_scope: list[str] = []
    proposals: list[str] = []
    for attribute in draft.attributes:
        if attribute.value is None:
            continue
        if attribute.name.strip().casefold() not in _DESIGN_ATTRIBUTE_NAMES:
            continue
        item = f"{attribute.name}={attribute.value}"
        if attribute.kind == "evidence_observation" and attribute.evidence_ids:
            ids = ", ".join(attribute.evidence_ids)
            evidence.append(f"- {item} [Evidence: {ids}]")
            used_evidence_ids.extend(attribute.evidence_ids)
        elif attribute.kind == "user_requested":
            user_scope.append(f"- {item} (사용자가 지정한 조건)")
        elif attribute.kind in {"proposal", "hypothesis", "to_validate", "interpretation"}:
            proposals.append(f"- {item} (확정 사실이 아닌 시각화 제안/가설)")

    trend_terms = [candidate.name.strip() for candidate in context.trends.candidates if candidate.name.strip()]
    trend_input_usable = context.input_statuses.get("trend_result") in {"ok", "partial"}
    request_input_usable = context.input_statuses.get("planning_request") in {"ok", "partial"}
    usable_candidates = tuple(
        candidate for candidate in context.trends.candidates
        if trend_input_usable and request_input_usable and candidate.name.strip()
        and candidate.evidence_ids and not dimension_mismatches(context.request, candidate)
    )
    verified_trends = [candidate.name.strip() for candidate in usable_candidates]
    unverified_trends = [name for name in trend_terms if name not in verified_trends]
    if context.request.original_query:
        user_scope.insert(0, f"- 원문 요청: {context.request.original_query}")
    if context.request.season:
        origin = context.request.field_origins.get("season", "unknown")
        user_scope.append(f"- 시즌: {context.request.season} (출처: {origin})")
    if context.request.category:
        origin = context.request.field_origins.get("category", "unknown")
        user_scope.append(f"- 카테고리: {context.request.category} (출처: {origin})")
    if verified_trends:
        evidence.append("- 근거 연결 트렌드명: " + ", ".join(dict.fromkeys(verified_trends)))
        used_evidence_ids.extend(evidence_id for candidate in usable_candidates for evidence_id in candidate.evidence_ids)

    styling_sections: list[str] = []
    for relation in context.styling_relationships:
        if relation.inventory_product_index >= len(context.inventory.products):
            continue
        product = context.inventory.products[relation.inventory_product_index]
        target_role = "상의" if relation.requested_role == "upper_body" else "하의"
        companion_role = "상의" if relation.inventory_role == "upper_body" else "하의"
        item_label = display_inventory_label(product)
        lines = [
            f"- 요청 신상품: {context.request.category or '미분류'} {target_role}",
            f"- 함께 코디할 재고 맥락: {item_label} ({companion_role})",
            f"- 연결 방식: {relation.rule_version} ({relation.request_role_source}; {relation.inventory_role_source})",
            "- 이 코디 관계는 분류 규칙 기반 제안이며 구매 선호·재고 소진·매출 효과의 증거가 아님",
        ]
        if product.note:
            lines.append(
                f"- 사용자 제공 미확인 재고 메모: ‘{product.note}’; 수량, 기준일 및 실제 재고 상태를 추정하지 않음"
            )
        if relation.inventory_evidence_ids:
            lines.append(
                "- 연결된 재고 Evidence (재고 상품 기록만 지지하며 코디 효과를 입증하지 않음): "
                + ", ".join(relation.inventory_evidence_ids)
            )
        evidenced_companion_attrs = [
            signal for signal in product.attributes
            if signal.value is not None and signal.origin == "evidence_observation" and signal.evidence_ids
        ]
        for signal in evidenced_companion_attrs:
            lines.append(
                f"- 재고 상품의 관찰 속성 (상의 속성이 아님): {signal.name}={signal.value} "
                f"[Evidence: {', '.join(signal.evidence_ids)}]"
            )
            used_evidence_ids.extend(signal.evidence_ids)
        used_evidence_ids.extend(relation.inventory_evidence_ids)
        styling_sections.append("\n".join(lines))

    limitations = list(draft.limitations)
    if unverified_trends:
        limitations.append("근거 ID가 없는 트렌드명은 시각적 사실이나 디자인 지시로 사용하지 않음: " + ", ".join(dict.fromkeys(unverified_trends)))
    if not evidence:
        limitations.append("이미지 프롬프트에 반영할 근거 연결 디자인 속성이 없음.")
    if not proposals:
        proposals.append("- 색상·소재·실루엣·패턴·디테일은 미확정이며, 이미지 모델이 선택하는 경우 모두 시각화 제안으로 취급")
    if styling_sections:
        proposals.append("- 요청 상의와 연결된 하의 재고 맥락을 함께 보여주는 코디 구성 (재고 소진 효과는 주장하지 않음)")

    conflict_text = tuple(
        f"{conflict.field}: {conflict.message} ({dict(conflict.values)!r})"
        for conflict in context.conflicts
    )
    prompt_sections = [
        "상품기획 검토용 콘셉트 이미지 1장을 생성합니다. 완성 상품, 실제 상품 사진, 승인된 디자인 또는 생산 지시가 아닙니다.",
        "사용자가 지정한 범위 (사실로 고정):\n" + ("\n".join(user_scope) if user_scope else "- 미제공"),
        "근거로 확인된 디자인 관찰 (표시된 Evidence 범위 안에서만 반영):\n" + ("\n".join(evidence) if evidence else "- 없음"),
        "시각화 제안 (사실이 아닌 탐색용 가설):\n" + "\n".join(proposals),
        "미확인·제외 조건:\n- 소재 성능, 실제 핏, 수요, 고객 선호, 생산 가능성을 주장하지 않음.\n- 근거 없는 트렌드 의미나 재고 효과를 만들지 않음.\n- 로고, 문구, 워터마크를 추가하지 않음.\n- 임의로 정한 시각 요소는 모두 검토용 제안임을 전제로 함.",
    ]
    if styling_sections:
        prompt_sections.insert(
            3,
            "코디 맥락 (요청 상품과 재고 상품을 구분):\n" + "\n".join(styling_sections),
        )
    if conflict_text:
        prompt_sections.append("해결되지 않은 입력 충돌 (임의로 해소하지 말 것):\n" + "\n".join(f"- {item}" for item in conflict_text))
    prompt = "\n\n".join(prompt_sections)
    digest = hashlib.sha256((IMAGE_DESIGNER_SYSTEM_PROMPT + "\n\n" + prompt).encode("utf-8")).hexdigest()
    return ImageGenerationRequest(
        request_id=context.request_id,
        season=draft.season,
        category=draft.category,
        prompt=prompt,
        prompt_version=PROMPT_VERSION,
        prompt_sha256=digest,
        evidence_ids=tuple(dict.fromkeys(used_evidence_ids)),
        proposal_fields=tuple(dict.fromkeys(proposals)),
        limitations=tuple(dict.fromkeys(limitations)),
        conflicts=conflict_text,
        styling_relationships=context.styling_relationships,
        system_prompt=IMAGE_DESIGNER_SYSTEM_PROMPT,
    )


def run_image_generation(
    request: ImageGenerationRequest,
    *,
    provider: ImageGenerationProvider | None = None,
    enabled: bool = False,
    confirmed: bool = False,
    output_dir: Path = DEFAULT_IMAGE_DIR,
) -> ImageGenerationResult:
    """Generate only after both runtime activation and an explicit confirmation."""
    if request.conflicts:
        return ImageGenerationResult(
            status="blocked", request=request,
            limitations=("입력 충돌을 MD가 확인하기 전까지 이미지 생성을 보류했습니다.",),
        )
    if not request.season or not request.category:
        return ImageGenerationResult(
            status="blocked", request=request,
            limitations=("시즌과 카테고리가 확인되기 전까지 이미지 생성을 보류했습니다.",),
        )
    if not confirmed and enabled:
        return ImageGenerationResult(
            status="ready", request=request,
            limitations=("프롬프트가 준비됐습니다. 이 실행에서 실제 생성하려면 호출별 확인이 필요합니다.",),
        )
    if not enabled:
        return ImageGenerationResult(
            status="blocked" if confirmed else "not_requested", request=request,
            limitations=("이미지 공급자가 비활성 상태입니다. 실제 생성에는 설정 활성화와 호출별 확인이 모두 필요합니다.",),
        )
    if provider is None:
        return ImageGenerationResult(
            status="failed", request=request, error_code="IMAGE_PROVIDER_NOT_CONFIGURED",
            limitations=("이미지 공급자가 설정되지 않아 프롬프트만 보존했습니다.",),
        )
    try:
        generated = provider.generate(request)
        if not generated.image_bytes:
            raise ValueError("Provider returned an empty image")
        extension = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}.get(generated.mime_type)
        if extension is None:
            raise ValueError("Provider returned an unsupported image type")
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", request.request_id)[:80] or "concept"
        image_id = "IMG-" + uuid.uuid4().hex[:12].upper()
        image_path = output_dir / f"{safe_id}-{request.prompt_sha256[:12]}-{image_id}{extension}"
        image_path.write_bytes(generated.image_bytes)
        return ImageGenerationResult(
            status="generated", request=request, provider=generated.provider,
            model=generated.model, image_id=image_id, image_path=str(image_path),
            limitations=("생성 결과는 검토용 시안이며 정확한 상품 사양이나 생산 가능성을 보증하지 않습니다.",),
        )
    except Exception as exc:  # Provider errors should not discard the planning draft.
        code = "IMAGE_GENERATION_FAILED"
        if isinstance(exc, ImageProviderError):
            code = exc.code
        return ImageGenerationResult(
            status="failed", request=request, provider=getattr(provider, "provider_name", None),
            model=getattr(provider, "model", None), error_code=code,
            limitations=("이미지 생성이 실패했으며 기획 초안과 프롬프트는 유지됩니다. 오류 본문이나 비밀값은 노출하지 않았습니다.",),
        )


def run_concept_to_image(
    context: ProductPlanningContext,
    *,
    provider: ImageGenerationProvider | None = None,
    image_generation_enabled: bool = False,
    confirm_image_generation: bool = False,
    output_dir: Path = DEFAULT_IMAGE_DIR,
) -> ConceptImageWorkflowResult:
    """Run the current concept generator, then prepare and optionally create an image."""
    draft, issues = RuleBasedConceptGenerator().generate(context)
    image_request = build_image_generation_request(context, draft)
    image_result = run_image_generation(
        image_request,
        provider=provider,
        enabled=image_generation_enabled,
        confirmed=confirm_image_generation,
        output_dir=output_dir,
    )
    return ConceptImageWorkflowResult(draft=draft, validation_issues=issues, image=image_result)


class ImageProviderError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class OpenAIImageProvider:
    """Minimal OpenAI Images API adapter; never logs credentials or response bodies."""

    api_key: str = field(repr=False)
    model: str = DEFAULT_IMAGE_MODEL
    timeout_seconds: int = 180
    endpoint: str = "https://api.openai.com/v1/images/generations"
    provider_name: str = "OpenAI Images API"

    def generate(self, request: ImageGenerationRequest) -> GeneratedImage:
        if not self.api_key.strip():
            raise ImageProviderError("IMAGE_API_KEY_MISSING")
        full_prompt = (
            "SYSTEM INSTRUCTIONS (follow throughout):\n"
            + request.system_prompt
            + "\n\nUSER DESIGN BRIEF:\n"
            + request.prompt
        )
        body = json.dumps({"model": self.model, "prompt": full_prompt, "n": 1}, ensure_ascii=False).encode("utf-8")
        http_request = urllib.request.Request(
            self.endpoint, data=body, method="POST",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise ImageProviderError(f"IMAGE_API_HTTP_{exc.code}") from None
        except (urllib.error.URLError, TimeoutError):
            raise ImageProviderError("IMAGE_API_UNAVAILABLE") from None
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ImageProviderError("IMAGE_API_INVALID_RESPONSE") from None
        try:
            encoded = payload["data"][0]["b64_json"]
            image_bytes = base64.b64decode(encoded, validate=True)
        except (KeyError, IndexError, TypeError, ValueError):
            raise ImageProviderError("IMAGE_API_IMAGE_MISSING") from None
        return GeneratedImage(image_bytes=image_bytes, mime_type="image/png", provider=self.provider_name, model=self.model)
