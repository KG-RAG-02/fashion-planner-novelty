"""Deterministic size budget for the text-planning LLM input data.

build_planning_prompt serializes the planning data with
serialize_untrusted_prompt_data. When the encoded data is longer than
PROMPT_DATA_MAX_CHARS, that serializer replaces it with a short preview string:
the preview carries no parseable Evidence IDs, so the allowed-ID set becomes
empty and every citation in the model output is rejected after a paid call.

This module shrinks the data only when it would not fit, without any model
call. It applies one step at a time, re-measures after each step and stops as
soon as the data fits:

T1  drop `limitations` lines that the trend/inventory lists already show
T2  group limitation lines that differ only in reference tokens and digits
T3  compact inventory products and trend candidates without dropping values
T4  replace Evidence IDs by short aliases, mapped back after the model call
T5  lossy trimming, one unit at a time

The length is measured exactly as the serializer emits the data before its
preview collapse. The step functions change the given data in place;
reduce_prompt_data works on a copy. No I/O and no randomness, so the same input
always gives the same prompt.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

from . import prompt_safety


BUDGET_VERSION = "p06-prompt-budget/1"
LADDER = ("T1", "T2", "T3", "T4", "T5")
EVIDENCE_ID_KEYS = frozenset({"evidence_id", "evidence_ids", "description_evidence_ids"})
LIMITATION_KEYS = ("trend_limitations", "inventory_limitations", "limitations")

# T5 parameters (lossy trimming limits).
KEEP_INVENTORY_PRODUCTS = 3
TREND_DESCRIPTION_CHARS = 160
KEEP_TREND_CANDIDATES = 3

# Bounds that prompt_safety.serialize_untrusted_prompt_data hard-codes. They
# are mirrored so the measured length is exactly what the serializer emits.
_MAX_DEPTH = 8
_MAX_ITEMS = 100
_MAX_KEY_CHARS = 200

_MAPPING_PREFIX = "Stock trend mapping: "
_REFERENCE_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*:[^\s,()]+")
_NUMBER = re.compile(r"\d[\d,.]*")
GROUPED_LINES_NOTE = "같은 형식의 항목 {count}건 더 있음: 참조 ID·수치만 다름"
_GROUPED_LINES_NOTE_PATTERN = re.compile(r"같은 형식의 항목 \d+건 더 있음: 참조 ID·수치만 다름")
# T2 appends the note in parentheses to a real upstream line: " (같은 형식의 항목 N건 …)".
_GROUPED_LINES_NOTE_SUFFIX = re.compile(r"\s*\(" + _GROUPED_LINES_NOTE_PATTERN.pattern + r"\)")
# Aliases are an uppercase prefix plus digits (E12, EV3); ASCII-only edges so a
# Korean particle right after an alias ("E12의") still counts as a boundary.
_ALIAS_TOKEN = re.compile(r"(?<![0-9A-Za-z_])[A-Z]+[0-9]+(?![0-9A-Za-z_])")
# Model-output fields that are never free text.
_NON_TEXT_OUTPUT_KEYS = frozenset({"request_id", "kind", "evidence_ids"})


# ---------------------------------------------------------------- measurement
def encode_prompt_data(value: object) -> str:
    """Return the JSON text serialize_untrusted_prompt_data emits before its preview collapse.

    Same field bounds and the same {"truncated": true, "data": ...} wrapper as
    the serializer, which stays unchanged as the last line of defence. Only the
    collapse is left out, because it is exactly what this budget avoids.
    tests/test_prompt_budget.py pins this mirror to the real serializer.
    """
    truncated = False
    field_max_chars = prompt_safety.PROMPT_DATA_FIELD_MAX_CHARS

    def bound(item: object, depth: int = 0) -> object:
        nonlocal truncated
        if depth > _MAX_DEPTH:
            truncated = True
            return "[nested data truncated]"
        if isinstance(item, str):
            if len(item) > field_max_chars:
                truncated = True
                return item[:field_max_chars] + "…[truncated]"
            return item
        if item is None or isinstance(item, (bool, int, float)):
            return item
        if isinstance(item, dict):
            result = {}
            for index, (key, child) in enumerate(item.items()):
                if index >= _MAX_ITEMS:
                    truncated = True
                    break
                safe_key = str(key)
                if len(safe_key) > _MAX_KEY_CHARS:
                    safe_key = safe_key[:_MAX_KEY_CHARS] + "…"
                    truncated = True
                result[safe_key] = bound(child, depth + 1)
            return result
        if isinstance(item, (list, tuple)):
            values = list(item)
            if len(values) > _MAX_ITEMS:
                truncated = True
                values = values[:_MAX_ITEMS]
            return [bound(child, depth + 1) for child in values]
        return bound(str(item), depth + 1)

    bounded = bound(value)
    if truncated:
        bounded = {"truncated": True, "data": bounded}
    return json.dumps(bounded, ensure_ascii=False, separators=(",", ":"))


def prompt_data_chars(value: object) -> int:
    return len(encode_prompt_data(value))


# ---------------------------------------------------------------- T1
def drop_duplicate_limitations(data: dict[str, Any]) -> int:
    """T1: keep only the `limitations` lines that the prompt does not already show.

    `limitations` is context.limitations, which repeats every trend and
    inventory limitation and adds "Stock trend mapping: X" next to X. The Draft
    keeps every line because parse_concept_output re-merges context.limitations.
    """
    if not isinstance(data.get("limitations"), list):
        return 0
    shown = {line for key in ("trend_limitations", "inventory_limitations")
             for line in data.get(key) or () if isinstance(line, str)}
    lines = data["limitations"]
    present = shown | {line for line in lines if isinstance(line, str)}

    def duplicate(line: object) -> bool:
        if not isinstance(line, str):
            return False
        if line in shown:
            return True
        return line.startswith(_MAPPING_PREFIX) and line[len(_MAPPING_PREFIX):] in present

    data["limitations"] = [line for line in lines if not duplicate(line)]
    return len(lines) - len(data["limitations"])


# ---------------------------------------------------------------- T2
def _line_shape(line: str) -> str:
    return _NUMBER.sub("#", _REFERENCE_TOKEN.sub("@", line))


def group_repeated_limitations(data: dict[str, Any]) -> int:
    """T2: per limitation list, lines differing only in reference tokens and digits
    become the first such line plus a note with the number of other lines."""
    grouped = 0
    for key in LIMITATION_KEYS:
        lines = data.get(key)
        if not isinstance(lines, list) or len(lines) < 2:
            continue
        kept: list[object] = []
        others: list[int] = []
        first_of_shape: dict[str, int] = {}
        for line in lines:
            if isinstance(line, str):
                shape = _line_shape(line)
                if shape in first_of_shape:
                    others[first_of_shape[shape]] += 1
                    continue
                first_of_shape[shape] = len(kept)
            kept.append(line)
            others.append(0)
        data[key] = [f"{line} ({GROUPED_LINES_NOTE.format(count=count)})" if count else line
                     for line, count in zip(kept, others)]
        grouped += sum(others)
    return grouped


# ---------------------------------------------------------------- T3
def _without_empty(item: dict[str, Any], keep: Iterable[str]) -> dict[str, Any]:
    """Drop null and empty fields (absent reads the same as null to the model)."""
    keep = set(keep)
    return {key: value for key, value in item.items()
            if key in keep or not (value is None or value == "" or value == [] or value == {})}


def _hoist_common(items: list[dict[str, Any]], keys: Iterable[str]) -> dict[str, Any]:
    """Move scalar fields that have one identical value on every item into one object."""
    if len(items) < 2:
        return {}
    common: dict[str, Any] = {}
    for key in keys:
        if key not in items[0]:
            continue
        value = items[0][key]
        if isinstance(value, (dict, list)):
            continue
        if all(key in item and type(item[key]) is type(value) and item[key] == value for item in items[1:]):
            common[key] = value
    for item in items:
        for key in common:
            del item[key]
    return common


def _insert_before(data: dict[str, Any], anchor: str, key: str, value: object) -> None:
    """Place `key` right before `anchor`, so shared fields read before the list they describe."""
    entries = [(name, item) for name, item in data.items() if name != key]
    data.clear()
    for name, item in entries:
        if name == anchor:
            data[key] = value
        data[name] = item
    data.setdefault(key, value)


def _compact_inventory(data: dict[str, Any]) -> list[int]:
    """Return, per remaining product, how many original entries were merged into it."""
    products = data.get("inventory_products")
    if not isinstance(products, list) or not products:
        return []
    origin_defaulted = False
    for product in products:
        attributes = []
        for attr in product.get("attributes") or ():
            if not isinstance(attr, dict):
                attributes.append(attr)
                continue
            if attr.get("value") is None and not attr.get("evidence_ids"):
                continue  # null value and no evidence: nothing to show or cite
            if attr.get("origin") == "unknown" and not attr.get("evidence_ids"):
                attributes.append({"name": attr.get("name"), "value": attr.get("value")})
                origin_defaulted = True
            else:
                attributes.append(attr)
        product["attributes"] = attributes

    # Stock returns the same style once per linked trend; such entries differ
    # only in evidence_ids. Merge them, keeping the IDs in their first order.
    merged: list[dict[str, Any]] = []
    linked: list[int] = []
    open_entry: dict[str, int] = {}
    for product in products:
        ids = list(product.get("evidence_ids") or ())
        content = json.dumps({key: value for key, value in product.items() if key != "evidence_ids"},
                             ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        index = open_entry.get(content)
        if index is not None:
            union = list(dict.fromkeys([*merged[index]["evidence_ids"], *ids]))
            if len(union) <= _MAX_ITEMS:
                merged[index]["evidence_ids"] = union
                linked[index] += 1
                continue
        # First entry of its kind, or the union would pass the serializer's
        # 100-item array bound and silently lose IDs: start a new entry.
        open_entry[content] = len(merged)
        merged.append({**product, "evidence_ids": ids})
        linked.append(1)

    compacted = [_without_empty(product, keep=("evidence_ids",)) for product in merged]
    common = _hoist_common(compacted, [key for key in compacted[0]
                                       if key not in {"style_id", "evidence_ids", "attributes"}])
    if origin_defaulted:
        common["attribute_origin"] = "unknown"
    data["inventory_products"] = compacted
    if common:
        _insert_before(data, "inventory_products", "inventory_common", common)
    return linked


def _compact_trends(data: dict[str, Any]) -> None:
    candidates = data.get("trend_candidates")
    if not isinstance(candidates, list) or not candidates:
        return
    origin_defaulted = False
    for candidate in candidates:
        for attr in candidate.get("attributes") or ():
            if isinstance(attr, dict) and attr.get("origin") == "evidence_observation" and attr.get("evidence_ids"):
                del attr["origin"]
                origin_defaulted = True
    compacted = [_without_empty(candidate, keep=("name", "evidence_ids")) for candidate in candidates]
    common = _hoist_common(compacted, ["qualification"])
    if origin_defaulted:
        common["attribute_origin"] = "evidence_observation"
    data["trend_candidates"] = compacted
    if common:
        _insert_before(data, "trend_candidates", "trend_common", common)


def compact_structure(data: dict[str, Any]) -> list[int]:
    """T3: lossless structural compaction of inventory products and trend candidates.

    Inventory: null attributes without evidence are dropped, attributes with
    origin unknown and no evidence keep only name and value, entries that differ
    only in evidence_ids are merged, and scalars shared by every entry move to
    inventory_common. Trends: null/empty fields are dropped, a qualification
    shared by every candidate moves to trend_common, and origin
    evidence_observation is omitted on evidenced attributes. Returns the merge
    count per remaining inventory product (T5 drops the least linked first).
    """
    linked = _compact_inventory(data)
    _compact_trends(data)
    return linked


# ---------------------------------------------------------------- T4
def _map_evidence_ids(value: object, convert: Callable[[str], str]) -> None:
    """Apply `convert` to string IDs under the keys build_planning_prompt collects."""
    if isinstance(value, dict):
        for key, child in value.items():
            if key in EVIDENCE_ID_KEYS:
                if isinstance(child, str):
                    value[key] = convert(child)
                elif isinstance(child, list):
                    value[key] = [convert(item) if isinstance(item, str) else item for item in child]
            else:
                _map_evidence_ids(child, convert)
    elif isinstance(value, list):
        for child in value:
            _map_evidence_ids(child, convert)


def _alias_shaped_tokens(value: object, into: set[str]) -> set[str]:
    """Every token of the data's text (keys and values, IDs included) that restore_model_text could rewrite."""
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(key, str):
                into.update(_ALIAS_TOKEN.findall(key))
            _alias_shaped_tokens(child, into)
    elif isinstance(value, list):
        for child in value:
            _alias_shaped_tokens(child, into)
    elif isinstance(value, str):
        into.update(_ALIAS_TOKEN.findall(value))
    return into


def alias_evidence_ids(data: dict[str, Any]) -> dict[str, str]:
    """T4: replace Evidence IDs by E1..En in first-appearance order; return alias -> real.

    Only values under evidence_id / evidence_ids / description_evidence_ids
    change; free text is untouched. restore_model_text later rewrites alias
    tokens anywhere in the model's text, so no token already in the data may
    look like an alias: if a real ID or any free text (a user query, a trend
    description) holds E12, the prefix becomes EV (EVV if EV12 exists too, and
    so on).
    """
    reals: dict[str, None] = {}

    def remember(real: str) -> str:
        reals.setdefault(real, None)
        return real

    _map_evidence_ids(data, remember)
    taken = _alias_shaped_tokens(data, set(reals))
    prefix = "E"
    while any(re.fullmatch(re.escape(prefix) + r"\d+", token) for token in taken):
        prefix += "V"
    alias_of = {real: f"{prefix}{number}" for number, real in enumerate(reals, start=1)}
    _map_evidence_ids(data, alias_of.__getitem__)
    return {alias: real for real, alias in alias_of.items()}


def resolve_output_aliases(output: object, alias_to_real: Mapping[str, str]) -> object:
    """Map aliases in the model output's evidence_ids lists back to the real IDs.

    Values that are not aliases stay as they are, so the allowed-ID check in
    text_concept_generation still rejects unknown or invented IDs.
    """
    if isinstance(output, dict):
        return {key: ([alias_to_real.get(item, item) if isinstance(item, str) else item for item in child]
                      if key == "evidence_ids" and isinstance(child, list)
                      else resolve_output_aliases(child, alias_to_real))
                for key, child in output.items()}
    if isinstance(output, list):
        return [resolve_output_aliases(child, alias_to_real) for child in output]
    return output


def _restore_text(text: str, alias_to_real: Mapping[str, str]) -> str:
    if _GROUPED_LINES_NOTE_PATTERN.search(text):
        # Strip only the note: the line it was appended to is a real upstream line. Dropping the whole line
        # could leave a single-value claim empty, and EMPTY_CLAIM_VALUE would discard the run's LLM result.
        text = _GROUPED_LINES_NOTE_PATTERN.sub("", _GROUPED_LINES_NOTE_SUFFIX.sub("", text))
    if alias_to_real:
        text = _ALIAS_TOKEN.sub(lambda match: alias_to_real.get(match.group(0), match.group(0)), text)
    return text


def restore_model_text(output: object, alias_to_real: Mapping[str, str]) -> object:
    """Post-process model-written free text after a reduced prompt.

    Alias tokens copied from the prompt become the real Evidence IDs, and the
    T2 grouping note is stripped wherever the model copied it: the note only
    describes the prompt copy, while the Draft keeps the original lines through
    context.limitations. A list item left empty by that is removed.
    """
    if isinstance(output, dict):
        return {key: (child if key in _NON_TEXT_OUTPUT_KEYS else restore_model_text(child, alias_to_real))
                for key, child in output.items()}
    if isinstance(output, list):
        restored = []
        for item in output:
            if isinstance(item, str) and _GROUPED_LINES_NOTE_PATTERN.search(item):
                text = _restore_text(item, alias_to_real)
                if text.strip():
                    restored.append(text)
            else:
                restored.append(restore_model_text(item, alias_to_real))
        return restored
    if isinstance(output, str):
        return _restore_text(output, alias_to_real)
    return output


# ---------------------------------------------------------------- T5
def _trend_priority(candidate: dict[str, Any], request_season: str | None) -> tuple[int, int, int]:
    """Higher keeps longer: exact requested season, then attribute and evidence counts."""
    season_match = 1 if request_season and candidate.get("season") == request_season else 0
    return (season_match, len(candidate.get("attributes") or ()), len(candidate.get("evidence_ids") or ()))


def trim_to_budget(
    data: dict[str, Any],
    fits: Callable[[dict[str, Any]], bool],
    *,
    linked: list[int] | None = None,
    request_season: str | None = None,
) -> dict[str, int]:
    """T5: lossy trimming one unit at a time, stopping as soon as `fits(data)` holds.

    a) inventory products down to 3, fewest linked trends first (ties: later first)
    b) trend descriptions over 160 chars cut to 160 chars plus an ellipsis, longest first
    c) trend candidates down to 3, lowest (exact requested season, attribute count,
       evidence count) first (ties: later first)
    d) inventory products down to 0, trend candidates down to 1, then each
       limitation list keeps its first line
    """
    trimmed = {"inventory": 0, "descriptions": 0, "trends": 0, "limitation_lines": 0}
    if fits(data):
        return trimmed
    products = data.get("inventory_products")
    products = products if isinstance(products, list) else []
    links = list(linked) if linked is not None and len(linked) == len(products) else [1] * len(products)
    candidates = data.get("trend_candidates")
    candidates = candidates if isinstance(candidates, list) else []

    def drop_products(floor: int) -> bool:
        while len(products) > floor:
            index = min(range(len(products)), key=lambda i: (links[i], -i))
            del products[index]
            del links[index]
            trimmed["inventory"] += 1
            if not products:
                data.pop("inventory_common", None)  # shared fields of no product
            if fits(data):
                return True
        return False

    def drop_trends(floor: int) -> bool:
        while len(candidates) > floor:
            index = min(range(len(candidates)),
                        key=lambda i: (_trend_priority(candidates[i], request_season), -i))
            del candidates[index]
            trimmed["trends"] += 1
            if fits(data):
                return True
        return False

    if drop_products(KEEP_INVENTORY_PRODUCTS):
        return trimmed

    def description_length(index: int) -> int:
        description = candidates[index].get("description")
        return len(description) if isinstance(description, str) else 0

    for index in sorted(range(len(candidates)), key=lambda i: -description_length(i)):
        if description_length(index) > TREND_DESCRIPTION_CHARS:
            candidates[index]["description"] = candidates[index]["description"][:TREND_DESCRIPTION_CHARS] + "…"
            trimmed["descriptions"] += 1
            if fits(data):
                return trimmed

    if drop_trends(KEEP_TREND_CANDIDATES) or drop_products(0) or drop_trends(1):
        return trimmed
    for key in ("limitations", "inventory_limitations", "trend_limitations"):
        lines = data.get(key)
        if isinstance(lines, list) and len(lines) > 1:
            trimmed["limitation_lines"] += len(lines) - 1
            data[key] = lines[:1]
            if fits(data):
                return trimmed
    return trimmed


# ---------------------------------------------------------------- ladder
@dataclass(frozen=True)
class PromptReduction:
    """Reduced prompt data for one request and what it took to get there."""

    data: dict[str, Any]
    alias_to_real: Mapping[str, str]
    steps: tuple[str, ...]
    chars_before: int
    chars_after: int
    max_chars: int
    trimmed_inventory: int = 0
    trimmed_descriptions: int = 0
    trimmed_trends: int = 0
    trimmed_limitation_lines: int = 0

    @property
    def fits(self) -> bool:
        return self.chars_after <= self.max_chars

    def metadata(self, allowed_evidence_ids: int) -> dict[str, object]:
        """generation_metadata.prompt_reduction for a run whose data was reduced."""
        return {
            "version": BUDGET_VERSION,
            "cap": self.max_chars,
            "chars_before": self.chars_before,
            "chars_after": self.chars_after,
            "steps": list(self.steps),
            "aliased": bool(self.alias_to_real),
            "allowed_evidence_ids": allowed_evidence_ids,
            "trimmed": {
                "inventory": self.trimmed_inventory,
                "descriptions": self.trimmed_descriptions,
                "trends": self.trimmed_trends,
            },
        }

    def trimmed_limitation(self) -> str | None:
        """Draft limitation naming what T5 withheld from the LLM, or None when T5 removed nothing."""
        parts = []
        if self.trimmed_inventory:
            parts.append(f"재고 상품 {self.trimmed_inventory}개")
        if self.trimmed_descriptions:
            parts.append(f"트렌드 설명 {self.trimmed_descriptions}개의 {TREND_DESCRIPTION_CHARS}자 이후 부분")
        if self.trimmed_trends:
            parts.append(f"트렌드 후보 {self.trimmed_trends}개")
        if self.trimmed_limitation_lines:
            parts.append(f"한계 문구 {self.trimmed_limitation_lines}줄")
        if not parts:
            return None
        return (f"텍스트 LLM 입력이 한도({self.max_chars:,}자)를 넘어 다음 입력은 LLM에 보내지 않았습니다: "
                + ", ".join(parts) + ".")


def reduce_prompt_data(
    prompt_data: Mapping[str, Any],
    *,
    max_chars: int | None = None,
    request_season: str | None = None,
) -> PromptReduction:
    """Apply T1..T5 in order, each only while the data is still over `max_chars`.

    The caller's data is not modified. `fits` on the result is False when even
    T5 could not bring the data under the budget; the caller must then not send it.
    """
    max_chars = prompt_safety.PROMPT_DATA_MAX_CHARS if max_chars is None else max_chars
    data = copy.deepcopy(dict(prompt_data))
    chars_before = chars = prompt_data_chars(data)
    steps: list[str] = []
    linked: list[int] | None = None
    alias_to_real: dict[str, str] = {}
    trimmed = {"inventory": 0, "descriptions": 0, "trends": 0, "limitation_lines": 0}
    for step in LADDER:
        if chars <= max_chars:
            break
        if step == "T1":
            drop_duplicate_limitations(data)
        elif step == "T2":
            group_repeated_limitations(data)
        elif step == "T3":
            linked = compact_structure(data)
        elif step == "T4":
            alias_to_real = alias_evidence_ids(data)
        else:
            trimmed = trim_to_budget(data, lambda value: prompt_data_chars(value) <= max_chars,
                                     linked=linked, request_season=request_season)
        steps.append(step)
        chars = prompt_data_chars(data)
    return PromptReduction(
        data=data,
        alias_to_real=alias_to_real,
        steps=tuple(steps),
        chars_before=chars_before,
        chars_after=chars,
        max_chars=max_chars,
        trimmed_inventory=trimmed["inventory"],
        trimmed_descriptions=trimmed["descriptions"],
        trimmed_trends=trimmed["trends"],
        trimmed_limitation_lines=trimmed["limitation_lines"],
    )
