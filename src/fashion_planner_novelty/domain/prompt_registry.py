"""Load immutable, versioned prompt assets from the repository prompt tree."""

from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Mapping


PROMPT_ROOT = Path(__file__).resolve().parents[3] / "prompts"
_PLACEHOLDER = re.compile(r"\{\{([A-Z0-9_]+)\}\}")


@lru_cache(maxsize=1)
def _manifest() -> dict:
    try:
        value = json.loads((PROMPT_ROOT / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Prompt manifest is unavailable or invalid.") from exc
    if not isinstance(value, dict):
        raise RuntimeError("Prompt manifest must be a JSON object.")
    return value


def prompt_version_id(component: str) -> str:
    entry = _manifest().get(component)
    if not isinstance(entry, dict) or not isinstance(entry.get("version_id"), str):
        raise RuntimeError(f"Prompt component is not registered: {component}")
    return entry["version_id"]


@lru_cache(maxsize=32)
def load_prompt(component: str, part: str) -> str:
    if part not in {"system", "user"}:
        raise ValueError("prompt part must be 'system' or 'user'")
    entry = _manifest().get(component)
    directory = entry.get("directory") if isinstance(entry, dict) else None
    if not isinstance(directory, str):
        raise RuntimeError(f"Prompt component is not registered: {component}")
    root = (PROMPT_ROOT / directory).resolve()
    if PROMPT_ROOT.resolve() not in root.parents:
        raise RuntimeError("Prompt directory must remain inside prompts/.")
    suffix = "system_template.md" if part == "system" else "user_template.md"
    path = root / suffix
    try:
        content = path.read_text(encoding="utf-8").rstrip("\n")
    except OSError as exc:
        raise RuntimeError(f"Prompt asset is missing: {component}/{part}") from exc
    return content


def prompt_sha256(component: str, *extra_parts: str) -> str:
    """프롬프트 템플릿 내용의 SHA-256. 순번 대신 이 해시로 어떤 템플릿을 썼는지 식별한다.

    구성 요소의 system·user 템플릿(있는 것만)과, 코드에 있는 추가 지시문 조각을 정해진 순서로 해시한다.
    """
    digest = hashlib.sha256()
    for part in ("system", "user"):
        try:
            text = load_prompt(component, part)
        except RuntimeError:
            continue
        digest.update(f"{part}\0{text}\0".encode("utf-8"))
    for text in extra_parts:
        digest.update(f"code\0{text}\0".encode("utf-8"))
    return digest.hexdigest()


def render_prompt(component: str, part: str, values: Mapping[str, str]) -> str:
    template = load_prompt(component, part)
    expected = set(_PLACEHOLDER.findall(template))
    if expected != set(values):
        raise ValueError(f"Prompt template values do not match placeholders for {component}/{part}.")
    rendered = _PLACEHOLDER.sub(lambda match: values[match.group(1)], template)
    if _PLACEHOLDER.search(rendered):
        raise ValueError(f"Unresolved prompt placeholder in {component}/{part}.")
    return rendered
