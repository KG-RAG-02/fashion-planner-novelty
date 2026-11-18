"""OpenAI Images API 어댑터와 이미지 요청 모델.

상품·착장 이미지 호출은 workflows/draft_artifacts.py의 OpenAIDraftImageProvider가 이 어댑터로 한다.
"""

from __future__ import annotations

import base64
import json
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from ..domain.prompt_registry import load_prompt


DEFAULT_IMAGE_MODEL = "gpt-image-2.5-sunburst"
IMAGE_DESIGNER_SYSTEM_PROMPT = load_prompt("concept_image", "system")


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
    system_prompt: str = IMAGE_DESIGNER_SYSTEM_PROMPT
    purpose: str = "MD/디자이너 검토용 상품 콘셉트 시안"


@dataclass(frozen=True)
class GeneratedImage:
    image_bytes: bytes
    mime_type: str
    provider: str
    model: str


class ImageProviderError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _full_image_prompt(request: ImageGenerationRequest) -> str:
    return (
        "SYSTEM INSTRUCTIONS (follow throughout):\n"
        + request.system_prompt
        + "\n\nUSER DESIGN BRIEF:\n"
        + request.prompt
    )


def _post_images_api(endpoint: str, api_key: str, body: dict, timeout_seconds: int) -> dict:
    """POST one JSON body to an OpenAI Images endpoint; failures become safe codes without bodies or secrets."""
    http_request = urllib.request.Request(
        endpoint, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(http_request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ImageProviderError(f"IMAGE_API_HTTP_{exc.code}") from None
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, TimeoutError):
            raise ImageProviderError("IMAGE_API_TIMEOUT") from None
        if isinstance(reason, OSError) and getattr(reason, "errno", None) in {-2, 8}:
            raise ImageProviderError("IMAGE_API_DNS_FAILURE") from None
        if isinstance(reason, ssl.SSLError):
            raise ImageProviderError("IMAGE_API_TLS_FAILURE") from None
        raise ImageProviderError("IMAGE_API_UNAVAILABLE") from None
    except TimeoutError:
        raise ImageProviderError("IMAGE_API_TIMEOUT") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ImageProviderError("IMAGE_API_INVALID_RESPONSE") from None


def _first_image_bytes(payload: dict) -> bytes:
    try:
        encoded = payload["data"][0]["b64_json"]
        return base64.b64decode(encoded, validate=True)
    except (KeyError, IndexError, TypeError, ValueError):
        raise ImageProviderError("IMAGE_API_IMAGE_MISSING") from None


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
        payload = _post_images_api(self.endpoint, self.api_key,
                                   {"model": self.model, "prompt": _full_image_prompt(request), "n": 1},
                                   self.timeout_seconds)
        return GeneratedImage(image_bytes=_first_image_bytes(payload), mime_type="image/png",
                              provider=self.provider_name, model=self.model)


@dataclass
class OpenAIImageEditProvider:
    """OpenAI Images Edit API adapter: one new image from a prompt plus reference images.

    Each reference travels as a base64 data URL in the JSON body (``images[].image_url``), in order: the main
    reference first (input image 1), then ``extra_images`` (input image 2, ...). ``input_fidelity`` is not sent:
    the API reference says to omit it for the gpt-image-2 family, which processes image inputs at high
    fidelity. Never logs credentials or response bodies.
    """

    api_key: str = field(repr=False)
    model: str = DEFAULT_IMAGE_MODEL
    timeout_seconds: int = 180
    endpoint: str = "https://api.openai.com/v1/images/edits"
    provider_name: str = "OpenAI Images Edit API"

    def edit(self, request: ImageGenerationRequest, reference_image: bytes, *,
             mime_type: str = "image/png",
             extra_images: tuple[tuple[bytes, str], ...] = ()) -> GeneratedImage:
        if not self.api_key.strip():
            raise ImageProviderError("IMAGE_API_KEY_MISSING")
        images = []
        for data, media_type in ((reference_image, mime_type), *extra_images):
            if not data:
                raise ImageProviderError("IMAGE_API_REFERENCE_MISSING")
            if media_type not in {"image/png", "image/jpeg", "image/webp"}:
                raise ImageProviderError("IMAGE_API_REFERENCE_FORMAT_UNSUPPORTED")
            images.append({"image_url": f"data:{media_type};base64," + base64.b64encode(data).decode("ascii")})
        payload = _post_images_api(self.endpoint, self.api_key, {
            "model": self.model,
            "images": images,
            "prompt": _full_image_prompt(request),
            "n": 1,
        }, self.timeout_seconds)
        return GeneratedImage(image_bytes=_first_image_bytes(payload), mime_type="image/png",
                              provider=self.provider_name, model=self.model)
