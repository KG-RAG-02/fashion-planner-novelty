"""Text-LLM input budget: deterministic reduction instead of the preview collapse.

Offline only: scripted fake providers, no network.
"""
import copy
import json
import unittest
from decimal import Decimal
from unittest import mock

from fashion_planner_novelty.domain import prompt_budget as pb
from fashion_planner_novelty.domain.concept import base_product_profile
from fashion_planner_novelty.domain.context import (
    AgentResult,
    AttributeSignal,
    InventoryProduct,
    InventoryProductResult,
    PlanningInputs,
    PlanningRequest,
    TrendCandidate,
    TrendResult,
    build_planning_context,
)
from fashion_planner_novelty.domain.prompt_registry import render_prompt
from fashion_planner_novelty.domain.prompt_safety import PROMPT_DATA_MAX_CHARS, serialize_untrusted_prompt_data
from fashion_planner_novelty.workflows import text_concept_generation as tcg


RID = "budget-1"
MARKER = "UNTRUSTED_PLANNING_INPUT_JSON:\n"
GROUPED_NOTE = "같은 형식의 항목 {count}건 더 있음: 참조 ID·수치만 다름"
CLIP = ("무신사 스냅 착샷(musinsa_snap:{n}:아우터, 트렌드 아이템 재킷)과 소재·질감·디테일 유사도(CLIP, 흑백 이미지 + 소재·디테일, 색 제외)"
        "로 재고 색마다 유사도 상위 10%를 남겨 후보 {a:,}개 중 {b:,}개를 남겼습니다.")
CLIP_LINES = tuple(CLIP.format(n=i * 7, a=15_930 - i, b=1_604 + i) for i in range(90))


def make_context(*, trends=3, description="올리브 유틸리티 아우터가 늘었다.", ids_per_trend=2, id_tag="a1",
                 products=0, inventory_lines=(), constraints=()):
    schema = "1.0"
    request = PlanningRequest(AgentResult("user-request", RID, schema, "ok"), original_query="27SS 아우터 기획",
                              season="27SS", category="outerwear", constraints=tuple(constraints))
    candidates = tuple(TrendCandidate(
        name=f"트렌드 {i}", qualification="trend_analysis_result", season="27SS" if i % 2 == 0 else None,
        category="outerwear", description=description,
        evidence_ids=tuple(f"trend:{i}:{k}:{id_tag}" for k in range(ids_per_trend)),
        description_evidence_ids=(f"trend:{i}:0:{id_tag}",),
        attributes=(AttributeSignal("color", "olive", "evidence_observation", (f"trend:{i}:0:{id_tag}",)),),
    ) for i in range(trends))
    trend = TrendResult(AgentResult("trend-agent", RID, schema, "ok",
                                    limitations=("성별 필터는 정책이 정해지지 않아 적용하지 않았습니다.",)),
                        candidates=candidates)
    stock = tuple(InventoryProduct(
        style_id=f"{i:07d}", sku_ids=(), season="27SS", category="outerwear", quantity=10 + i, unit="pieces",
        inventory_definition="virtual_stock_v1", as_of="2020-09-22",
        evidence_ids=tuple(f"stock-agent:{i}-s0:E-00{k}" for k in range(1, 7)),
        attributes=(AttributeSignal("color", "블랙", "unknown"), AttributeSignal("fit", None, "unknown")),
    ) for i in range(products))
    inventory = InventoryProductResult(AgentResult("stock-agent", RID, schema, "ok" if stock else "no_results",
                                                   limitations=tuple(inventory_lines)), products=stock)
    return build_planning_context(PlanningInputs(request, trend, inventory))


def sample_data(*, trends=3, products=3, same_style=False, description="설명" * 40):
    """Prompt data in the shape build_planning_prompt produces."""
    candidates = [{
        "name": f"트렌드{i}", "qualification": "trend_analysis_result", "season": "2026FW" if i == 0 else None,
        "market": [], "channel": [], "category": None, "description": description,
        "evidence_ids": [f"trend:{i}:{k}:abcdef12" for k in range(4)],
        "description_evidence_ids": [f"trend:{i}:0:abcdef12"],
        "attributes": [{"name": "color", "value": "그레이", "origin": "evidence_observation",
                        "evidence_ids": [f"trend:{i}:3:abcdef12"]}],
    } for i in range(trends)]
    stock = [{
        "style_id": "0001" if same_style else f"{i:04d}", "category": "드레스", "season": "2026FW", "quantity": 10,
        "unit": "pieces", "inventory_definition": "virtual_stock_v1", "as_of": "2020-09-22",
        "evidence_ids": [f"stock-agent:{i}-s0:E-00{k}" for k in range(1, 7)],
        "attributes": [{"name": "color", "value": "블랙", "origin": "unknown", "evidence_ids": []},
                       {"name": "fit", "value": None, "origin": "unknown", "evidence_ids": []}],
    } for i in range(products)]
    trend_lines = ["성별 필터는 정책이 정해지지 않아 적용하지 않았습니다."]
    inventory_lines = ["재고·판매가는 가상 데이터(sample)입니다.", CLIP_LINES[0], CLIP_LINES[1],
                       "요청 성별(남)에 맞는 고객군(Menswear, Divided)에서 찾았습니다.",
                       "요청 성별(여)에 맞는 고객군(Ladieswear, Divided)에서 찾았습니다."]
    return {
        "request_id": "r-1", "input_statuses": {"planning_request": "ok"},
        "request": {"query": "q", "season": "2026FW", "evidence_ids": []},
        "trend_candidates": candidates, "trend_limitations": trend_lines,
        "inventory_products": stock, "inventory_limitations": inventory_lines, "conflicts": [],
        "limitations": [*trend_lines, *inventory_lines, "Upstream result from stock-agent has status 'partial'.",
                        "X 매핑 문제", "Stock trend mapping: X 매핑 문제", "Stock trend mapping: 다른 문제"],
        "questions_for_validation": [],
    }


def collect_ids(value, into=None):
    """The allowed-ID key rule of build_planning_prompt."""
    into = set() if into is None else into
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"evidence_id", "evidence_ids", "description_evidence_ids"}:
                if isinstance(child, str):
                    into.add(child)
                elif isinstance(child, list):
                    into.update(item for item in child if isinstance(item, str))
            else:
                collect_ids(child, into)
    elif isinstance(value, list):
        for child in value:
            collect_ids(child, into)
    return into


def prompt_data_of(context):
    """The data build_planning_prompt hands to the serializer first."""
    with mock.patch.object(tcg, "serialize_untrusted_prompt_data", wraps=serialize_untrusted_prompt_data) as spy:
        tcg.build_planning_prompt(context)
    return spy.call_args_list[0].args[0]


def shown_data(user_prompt):
    """The data part of the user prompt, inside the field-truncation wrapper if any."""
    shown = json.loads(user_prompt.split(MARKER, 1)[1])
    return shown["data"] if shown.get("truncated") is True and "data" in shown else shown


def answer(context, cite, *, opportunity="트렌드 관찰을 바탕으로 검토할 방향", limitations=("초안",),
           questions=("톤 범위 확인",)):
    """A valid model answer that cites `cite` exactly as written."""
    base = base_product_profile(context)

    def claim(value, kind, ids=()):
        return {"value": value, "kind": kind, "evidence_ids": list(ids)}

    def same(value):
        return {"value": value.value, "kind": value.kind, "evidence_ids": list(value.evidence_ids)}

    return {
        "request_id": context.request_id,
        "opportunity": claim(opportunity, "evidence_observation", cite),
        "target_customer": claim(None, "unknown"),
        "product_definition": claim("올리브 색상 아우터 콘셉트 제안", "proposal"),
        "product_profile": {
            "category": same(base.category), "season": same(base.season), "gender": claim("unknown", "proposal"),
            "product_type": claim("lightweight jacket", "proposal"), "material": claim("cotton blend", "proposal"),
            "silhouette": claim("relaxed", "proposal"), "color": claim("olive", "evidence_observation", cite),
            "details": [],
        },
        "attributes": [{"name": "color", "value": "olive", "kind": "evidence_observation", "evidence_ids": list(cite)}],
        "relation_to_own_products": [],
        "differentiation": [],
        "risks": [],
        "questions_for_validation": list(questions),
        "limitations": list(limitations),
    }


class ScriptedProvider:
    """Answers from the data it was shown, like a model reading the prompt."""

    model_name = "offline-budget-v1"

    def __init__(self, respond):
        self.respond = respond
        self.calls = 0
        self.user_prompt = None

    def generate_json(self, *, system_prompt, user_prompt):
        self.calls += 1
        self.user_prompt = user_prompt
        return json.dumps(self.respond(shown_data(user_prompt)), ensure_ascii=False)


def first_trend_id(shown):
    return next(c["evidence_ids"][0] for c in shown["trend_candidates"] if c.get("evidence_ids"))


class MeasurementTests(unittest.TestCase):
    def test_encoding_matches_the_serializer_including_field_bounds(self):
        nested = "leaf"
        for _ in range(10):
            nested = {"child": nested}
        values = [
            {"a": 1, "b": [True, None, 1.5], "c": '따옴표"와\n줄바꿈'},
            {"long": "가" * 2_500},
            {"items": list(range(150))},
            {f"k{i}": i for i in range(120)},
            {"x" * 250: "long key"},
            nested,
            {"tuple": (1, 2), "decimal": Decimal("1.5")},
            sample_data(),
        ]
        for value in values:
            with self.subTest(value=str(value)[:40]):
                self.assertEqual(pb.encode_prompt_data(value), serialize_untrusted_prompt_data(value))

    def test_measured_length_decides_the_collapse_exactly_at_the_cap(self):
        chunks = ["a" * 1_000] * 23
        missing = PROMPT_DATA_MAX_CHARS - pb.prompt_data_chars({"x": [*chunks, ""]})
        self.assertTrue(0 < missing < 2_000)
        at_cap = {"x": [*chunks, "a" * missing]}
        over_cap = {"x": [*chunks, "a" * (missing + 1)]}
        self.assertEqual(pb.prompt_data_chars(at_cap), PROMPT_DATA_MAX_CHARS)
        self.assertEqual(serialize_untrusted_prompt_data(at_cap), pb.encode_prompt_data(at_cap))
        self.assertEqual(pb.prompt_data_chars(over_cap), PROMPT_DATA_MAX_CHARS + 1)
        self.assertIn("data_preview", json.loads(serialize_untrusted_prompt_data(over_cap)))


class LadderStepTests(unittest.TestCase):
    def test_t1_keeps_only_limitation_lines_not_shown_elsewhere(self):
        data = sample_data()
        self.assertEqual(pb.drop_duplicate_limitations(data), 7)
        self.assertEqual(data["limitations"], [
            "Upstream result from stock-agent has status 'partial'.", "X 매핑 문제", "Stock trend mapping: 다른 문제",
        ])
        self.assertEqual(len(data["inventory_limitations"]), 5)

    def test_t2_groups_lines_differing_only_in_reference_tokens_and_digits(self):
        data = sample_data()
        self.assertEqual(pb.group_repeated_limitations(data), 2)
        grouped = f"{CLIP_LINES[0]} ({GROUPED_NOTE.format(count=1)})"
        self.assertEqual(data["inventory_limitations"], [
            "재고·판매가는 가상 데이터(sample)입니다.", grouped,
            "요청 성별(남)에 맞는 고객군(Menswear, Divided)에서 찾았습니다.",
            "요청 성별(여)에 맞는 고객군(Ladieswear, Divided)에서 찾았습니다.",
        ])
        self.assertIn(grouped, data["limitations"])
        self.assertNotIn(CLIP_LINES[1], data["limitations"])

    def test_t3_merges_inventory_entries_that_differ_only_in_evidence_ids(self):
        data = sample_data(products=3, same_style=True)
        self.assertEqual(pb.compact_structure(data), [3])
        (product,) = data["inventory_products"]
        self.assertEqual(product["evidence_ids"],
                         [f"stock-agent:{i}-s0:E-00{k}" for i in range(3) for k in range(1, 7)])
        self.assertEqual(product["attributes"], [{"name": "color", "value": "블랙"}])
        self.assertEqual(data["inventory_common"], {"attribute_origin": "unknown"})
        keys = list(data)
        self.assertEqual(keys.index("inventory_common") + 1, keys.index("inventory_products"))

        different = sample_data(products=2, same_style=True)
        different["inventory_products"][1]["quantity"] = 11
        self.assertEqual(pb.compact_structure(different), [1, 1])

    def test_t3_merge_never_passes_the_serializers_100_item_bound(self):
        data = sample_data(products=20, same_style=True)
        original = copy.deepcopy(data)
        before = [i for p in data["inventory_products"] for i in p["evidence_ids"]]
        linked = pb.compact_structure(data)
        after = [i for p in data["inventory_products"] for i in p["evidence_ids"]]
        self.assertEqual(len(before), 120)
        self.assertEqual(after, before)
        self.assertEqual([len(p["evidence_ids"]) for p in data["inventory_products"]], [96, 24])
        self.assertEqual(linked, [16, 4])
        # Every ID is still shown after the serializer's bounds, as before the merge.
        self.assertEqual(collect_ids(json.loads(pb.encode_prompt_data(data))), collect_ids(original))

    def test_t3_hoists_common_inventory_scalars_and_keeps_evidenced_null_attributes(self):
        data = sample_data(products=3)
        data["inventory_products"][0]["attributes"][1]["evidence_ids"] = ["stock-agent:fit-evidence"]
        pb.compact_structure(data)
        self.assertEqual(data["inventory_common"], {
            "category": "드레스", "season": "2026FW", "quantity": 10, "unit": "pieces",
            "inventory_definition": "virtual_stock_v1", "as_of": "2020-09-22", "attribute_origin": "unknown",
        })
        self.assertEqual(set(data["inventory_products"][1]), {"style_id", "evidence_ids", "attributes"})
        self.assertIn({"name": "fit", "value": None, "origin": "unknown", "evidence_ids": ["stock-agent:fit-evidence"]},
                      data["inventory_products"][0]["attributes"])

    def test_t3_compacts_trends_and_hoists_only_the_qualification(self):
        data = sample_data(trends=3)
        for candidate in data["trend_candidates"]:
            candidate["season"] = "2026FW"
        data["trend_candidates"][2]["attributes"].append(
            {"name": "fit", "value": "slim", "origin": "evidence_observation", "evidence_ids": []})
        pb.compact_structure(data)
        self.assertEqual(data["trend_common"], {"qualification": "trend_analysis_result",
                                                "attribute_origin": "evidence_observation"})
        first = data["trend_candidates"][0]
        self.assertEqual(set(first), {"name", "season", "description", "evidence_ids", "description_evidence_ids",
                                      "attributes"})
        self.assertEqual(first["attributes"], [{"name": "color", "value": "그레이", "evidence_ids": ["trend:0:3:abcdef12"]}])
        self.assertIn({"name": "fit", "value": "slim", "origin": "evidence_observation", "evidence_ids": []},
                      data["trend_candidates"][2]["attributes"])
        keys = list(data)
        self.assertEqual(keys.index("trend_common") + 1, keys.index("trend_candidates"))

    def test_t4_aliases_ids_in_first_appearance_order_and_round_trips(self):
        data = sample_data()
        data["trend_limitations"].append("trend:0:0:abcdef12 in text")
        before = collect_ids(data)
        aliases = pb.alias_evidence_ids(data)
        self.assertEqual(aliases["E1"], "trend:0:0:abcdef12")
        self.assertEqual(aliases["E4"], "trend:0:3:abcdef12")
        self.assertEqual(data["trend_candidates"][0]["evidence_ids"], ["E1", "E2", "E3", "E4"])
        self.assertEqual(data["trend_candidates"][0]["description_evidence_ids"], ["E1"])
        self.assertEqual({aliases[a] for a in collect_ids(data)}, before)
        self.assertEqual(len(set(aliases.values())), len(aliases))
        self.assertIn("trend:0:0:abcdef12 in text", data["trend_limitations"])
        output = {"risks": [{"value": "E1 근거", "kind": "hypothesis",
                             "evidence_ids": ["E1", "E9999", "trend:0:0:abcdef12"]}]}
        resolved = pb.resolve_output_aliases(output, aliases)
        self.assertEqual(resolved["risks"][0]["evidence_ids"], ["trend:0:0:abcdef12", "E9999", "trend:0:0:abcdef12"])
        self.assertEqual(resolved["risks"][0]["value"], "E1 근거")

    def test_t4_prefix_avoids_real_ids_that_look_like_aliases(self):
        data = sample_data()
        data["trend_candidates"][0]["evidence_ids"].append("E3")
        aliases = pb.alias_evidence_ids(data)
        self.assertTrue(all(alias.startswith("EV") and alias[2:].isdigit() for alias in aliases))
        self.assertEqual(aliases["EV5"], "E3")
        data = sample_data()
        data["trend_candidates"][0]["evidence_ids"] += ["E3", "EV2"]
        self.assertTrue(all(alias.startswith("EVV") for alias in pb.alias_evidence_ids(data)))

    def test_t4_prefix_avoids_alias_shaped_tokens_in_free_text(self):
        # restore_model_text rewrites alias tokens anywhere in the model text, so a token the data already
        # holds in free text (a user query, a trend description) must not become an alias either.
        data = sample_data()
        data["trend_candidates"][1]["description"] = "E2 라인 확장, 볼륨 소매"
        aliases = pb.alias_evidence_ids(data)
        self.assertTrue(all(alias.startswith("EV") and alias[2:].isdigit() for alias in aliases))
        self.assertEqual(data["trend_candidates"][1]["description"], "E2 라인 확장, 볼륨 소매")
        restored = pb.restore_model_text({"concept": {"value": "E2 라인 확장을 EV1 근거로 제안"}}, aliases)
        self.assertEqual(restored["concept"]["value"], "E2 라인 확장을 " + aliases["EV1"] + " 근거로 제안")

    def test_t5_drops_least_linked_products_later_first_and_stops_when_it_fits(self):
        data = sample_data(products=6)
        trimmed = pb.trim_to_budget(data, lambda d: len(d["inventory_products"]) <= 4, linked=[2, 1, 1, 3, 1, 2])
        self.assertEqual([p["style_id"] for p in data["inventory_products"]], ["0000", "0001", "0003", "0005"])
        self.assertEqual(trimmed, {"inventory": 2, "descriptions": 0, "trends": 0, "limitation_lines": 0})

    def test_t5_cuts_longest_descriptions_after_inventory_floor(self):
        data = sample_data(trends=3, products=5)
        for candidate, length in zip(data["trend_candidates"], (300, 500, 200)):
            candidate["description"] = "가" * length

        def fits(d):
            return len(d["inventory_products"]) <= 3 and sum(len(c["description"]) for c in d["trend_candidates"]) <= 900

        trimmed = pb.trim_to_budget(data, fits)
        self.assertEqual([p["style_id"] for p in data["inventory_products"]], ["0000", "0001", "0002"])
        self.assertEqual([len(c["description"]) for c in data["trend_candidates"]], [300, 161, 200])
        self.assertTrue(data["trend_candidates"][1]["description"].endswith("…"))
        self.assertEqual(trimmed, {"inventory": 2, "descriptions": 1, "trends": 0, "limitation_lines": 0})

    def test_t5_drops_lowest_priority_trends_later_first(self):
        data = sample_data(trends=5, products=0, description="짧은 설명")
        shapes = [("27SS", 1, 4), (None, 2, 1), (None, 0, 4), (None, 0, 4), ("27SS", 0, 1)]
        for candidate, (season, attributes, ids) in zip(data["trend_candidates"], shapes):
            candidate["season"] = season
            candidate["attributes"] = candidate["attributes"] * attributes
            candidate["evidence_ids"] = candidate["evidence_ids"][:ids]
        trimmed = pb.trim_to_budget(data, lambda d: len(d["trend_candidates"]) <= 3, request_season="27SS")
        self.assertEqual([c["name"] for c in data["trend_candidates"]], ["트렌드0", "트렌드1", "트렌드4"])
        self.assertEqual(trimmed["trends"], 2)

    def test_t5_last_resort_keeps_one_trend_and_first_limitation_lines(self):
        data = sample_data(trends=4, products=4)
        pb.compact_structure(data)
        trimmed = pb.trim_to_budget(data, lambda d: False, request_season="2026FW")
        self.assertEqual(data["inventory_products"], [])
        self.assertNotIn("inventory_common", data)
        self.assertEqual([c["name"] for c in data["trend_candidates"]], ["트렌드0"])
        for key in ("limitations", "inventory_limitations", "trend_limitations"):
            self.assertLessEqual(len(data[key]), 1)
        self.assertEqual(trimmed, {"inventory": 4, "descriptions": 0, "trends": 3, "limitation_lines": 13})


class ReducePromptDataTests(unittest.TestCase):
    def test_data_under_the_budget_is_left_alone(self):
        data = sample_data()
        original = copy.deepcopy(data)
        reduction = pb.reduce_prompt_data(data)
        self.assertEqual(reduction.steps, ())
        self.assertEqual(reduction.data, original)
        self.assertEqual(reduction.chars_before, reduction.chars_after)
        self.assertEqual(data, original)

    def test_ladder_stops_at_the_first_step_that_fits(self):
        data = sample_data()
        after_t1 = copy.deepcopy(data)
        pb.drop_duplicate_limitations(after_t1)
        reduction = pb.reduce_prompt_data(data, max_chars=pb.prompt_data_chars(after_t1))
        self.assertEqual(reduction.steps, ("T1",))
        self.assertEqual(reduction.data, after_t1)
        self.assertTrue(reduction.fits)

    def test_without_t5_allowed_ids_equal_the_uncapped_set(self):
        data = sample_data(trends=30, products=30, same_style=True)
        through_t3 = copy.deepcopy(data)
        for step in (pb.drop_duplicate_limitations, pb.group_repeated_limitations, pb.compact_structure):
            step(through_t3)
        through_t4 = copy.deepcopy(through_t3)
        pb.alias_evidence_ids(through_t4)
        budget = pb.prompt_data_chars(through_t4)
        self.assertGreater(pb.prompt_data_chars(through_t3), budget)
        reduction = pb.reduce_prompt_data(data, max_chars=budget)
        self.assertEqual(reduction.steps, ("T1", "T2", "T3", "T4"))
        shown = collect_ids(json.loads(serialize_untrusted_prompt_data(reduction.data)))
        self.assertEqual({reduction.alias_to_real[i] for i in shown}, collect_ids(data))

    def test_t5_keeps_the_allowed_ids_inside_the_input(self):
        data = sample_data(trends=30, products=30, description="긴 설명 " * 120)
        reduction = pb.reduce_prompt_data(data, max_chars=6_000, request_season="2026FW")
        self.assertEqual(reduction.steps[-1], "T5")
        self.assertTrue(reduction.fits)
        shown = collect_ids(json.loads(pb.encode_prompt_data(reduction.data)))
        self.assertTrue(shown and {reduction.alias_to_real[i] for i in shown} <= collect_ids(data))
        self.assertIsNotNone(reduction.trimmed_limitation())

    def test_unreducible_data_is_reported_instead_of_collapsed(self):
        data = sample_data()
        data["request"]["constraints"] = ["가" * 2_000] * 100
        reduction = pb.reduce_prompt_data(data)
        self.assertFalse(reduction.fits)
        self.assertEqual(reduction.steps, pb.LADDER)
        self.assertGreater(reduction.chars_after, PROMPT_DATA_MAX_CHARS)


class ModelTextTests(unittest.TestCase):
    def test_aliases_in_free_text_become_real_ids_and_grouping_notes_are_stripped(self):
        aliases = {"E1": "trend:1:0:a1", "E12": "trend:12:0:a1"}
        note = f"CLIP 줄 ({GROUPED_NOTE.format(count=9)})"
        output = {
            "request_id": "E1", "opportunity": {"value": "E1의 관찰과 [E12], E123 그리고 AE1", "kind": "E1",
                                                "evidence_ids": ["E1"]},
            "limitations": ["초안", note, f"첫 줄\n{note}", GROUPED_NOTE.format(count=3)],
            "questions_for_validation": ["E12 확인", "줄바꿈\r\n유지"],
        }
        restored = pb.restore_model_text(output, aliases)
        self.assertEqual(restored["opportunity"]["value"], "trend:1:0:a1의 관찰과 [trend:12:0:a1], E123 그리고 AE1")
        self.assertEqual(restored["opportunity"]["kind"], "E1")
        self.assertEqual(restored["opportunity"]["evidence_ids"], ["E1"])
        self.assertEqual(restored["request_id"], "E1")
        # The note goes; the real upstream line it was appended to stays; a note-only item is removed.
        self.assertEqual(restored["limitations"], ["초안", "CLIP 줄", "첫 줄\nCLIP 줄"])
        self.assertEqual(restored["questions_for_validation"], ["trend:12:0:a1 확인", "줄바꿈\r\n유지"])

    def test_a_grouped_line_copied_into_a_single_value_keeps_its_text(self):
        # Dropping the whole line here would leave the claim empty (EMPTY_CLAIM_VALUE) and discard the LLM result.
        grouped = f"{CLIP_LINES[0]} ({GROUPED_NOTE.format(count=89)})"
        restored = pb.restore_model_text({"risks": [{"value": grouped, "kind": "hypothesis", "evidence_ids": []}]}, {})
        self.assertEqual(restored["risks"][0]["value"], CLIP_LINES[0])


class GeneratorBudgetTests(unittest.TestCase):
    # Only the primary trend reaches the LLM data (domain/trend_basis.py), so these fixtures exceed the budget with
    # inventory products, limitation lines and request constraints instead of many trend candidates.
    def legacy_prompt(self, context):
        """build_planning_prompt as of d05e74e: serialize, collect IDs, render."""
        serialized = serialize_untrusted_prompt_data(prompt_data_of(context))
        user_prompt = render_prompt("text_planning", "user", {"UNTRUSTED_PLANNING_INPUT_JSON": serialized})
        return user_prompt, frozenset(collect_ids(json.loads(serialized)))

    def generate(self, context, respond):
        provider = ScriptedProvider(respond)
        generator = tcg.PromptedConceptGenerator(provider=provider, enabled=True)
        draft, issues = generator.generate(context)
        return provider, generator, draft, issues

    def test_under_the_budget_prompt_ids_and_metadata_are_unchanged(self):
        for context in (make_context(), make_context(trends=5, description="가" * 2_500)):
            with self.subTest(trends=len(context.trends.candidates)):
                prompt = tcg.build_planning_prompt(context)
                self.assertEqual((prompt.user_prompt, prompt.allowed_evidence_ids), self.legacy_prompt(context))
                self.assertIsNone(prompt.reduction)
                self.assertFalse(prompt.over_budget)
                provider, generator, draft, issues = self.generate(
                    context, lambda shown: answer(context, [first_trend_id(shown)]))
                self.assertEqual(generator.generation_metadata["status"], "generated")
                self.assertEqual(list(generator.generation_metadata), [
                    "engine", "status", "prompt_version", "model", "error_code", "llm_empty_fields",
                ])
        disabled = tcg.PromptedConceptGenerator(enabled=False)
        disabled.generate(make_context())
        self.assertNotIn("prompt_reduction", disabled.generation_metadata)

    def test_over_the_budget_data_is_reduced_instead_of_collapsed(self):
        context = make_context(trends=14, description="가" * 300, products=3, inventory_lines=CLIP_LINES)
        data = prompt_data_of(context)
        self.assertGreater(pb.prompt_data_chars(data), PROMPT_DATA_MAX_CHARS)
        self.assertIn("data_preview", json.loads(serialize_untrusted_prompt_data(data)))
        prompt = tcg.build_planning_prompt(context)
        sent = prompt.user_prompt.split(MARKER, 1)[1]
        self.assertNotIn("data_preview", json.loads(sent))
        self.assertLessEqual(len(sent), PROMPT_DATA_MAX_CHARS)
        self.assertEqual(prompt.allowed_evidence_ids, frozenset(collect_ids(json.loads(pb.encode_prompt_data(data)))))
        self.assertEqual(prompt.version, tcg.PROMPT_VERSION)

        provider, generator, draft, issues = self.generate(
            context, lambda shown: answer(context, [first_trend_id(shown)]))
        metadata = generator.generation_metadata
        self.assertEqual((metadata["status"], metadata["error_code"], provider.calls), ("generated", None, 1))
        self.assertEqual(metadata["prompt_version"], tcg.PROMPT_VERSION)
        self.assertEqual(metadata["prompt_reduction"], {
            "version": "p06-prompt-budget/1", "cap": PROMPT_DATA_MAX_CHARS,
            "chars_before": pb.prompt_data_chars(data), "chars_after": len(sent), "steps": ["T1"],
            "aliased": False, "allowed_evidence_ids": len(prompt.allowed_evidence_ids),
            "trimmed": {"inventory": 0, "descriptions": 0, "trends": 0},
        })
        # T1 only shortens the prompt copy: the Draft keeps every context limitation.
        self.assertEqual(draft.limitations[:len(context.limitations)], context.limitations)
        self.assertEqual(issues, ())

    def test_grouping_notes_reach_the_model_but_never_the_draft(self):
        context = make_context(trends=25, description="가" * 300, products=30, inventory_lines=CLIP_LINES)
        grouped = f"{CLIP_LINES[0]} ({GROUPED_NOTE.format(count=89)})"

        def respond(shown):
            self.assertIn(grouped, shown["inventory_limitations"])
            return answer(context, [first_trend_id(shown)], limitations=("초안", grouped), questions=(grouped, "톤 확인"))

        provider, generator, draft, issues = self.generate(context, respond)
        self.assertEqual(generator.generation_metadata["prompt_reduction"]["steps"], ["T1", "T2"])
        self.assertEqual(generator.generation_metadata["status"], "generated")
        self.assertFalse(any("같은 형식의 항목" in line for line in (*draft.limitations, *draft.questions_for_validation)))
        self.assertTrue(set(CLIP_LINES) <= set(draft.limitations))
        self.assertIn("초안", draft.limitations)
        self.assertIn("톤 확인", draft.questions_for_validation)

    def test_aliases_round_trip_through_generation(self):
        context = make_context(trends=40, description="나" * 200, ids_per_trend=8, id_tag="0123456789abcdef01234567",
                               products=100)
        seen = {}

        def respond(shown):
            alias = first_trend_id(shown)
            seen["alias"] = alias
            return answer(context, [alias], opportunity=f"{alias}에서 관찰된 방향")

        provider, generator, draft, issues = self.generate(context, respond)
        metadata = generator.generation_metadata
        self.assertEqual(metadata["status"], "generated")
        self.assertEqual(metadata["prompt_reduction"]["steps"], ["T1", "T2", "T3", "T4"])
        self.assertTrue(metadata["prompt_reduction"]["aliased"])
        self.assertEqual(seen["alias"], "E1")
        real = "trend:0:0:0123456789abcdef01234567"
        self.assertEqual(draft.opportunity.evidence_ids, (real,))
        self.assertEqual(draft.opportunity.value, f"{real}에서 관찰된 방향")
        self.assertEqual(draft.product_profile.color.evidence_ids, (real,))
        self.assertIn(real, draft.evidence_ids)
        self.assertFalse(any(item.startswith("E") and item[1:].isdigit() for item in draft.evidence_ids))

    def test_unknown_alias_is_rejected_by_the_claim_check(self):
        context = make_context(trends=40, description="나" * 200, ids_per_trend=8, id_tag="0123456789abcdef01234567",
                               products=100)
        provider, generator, draft, issues = self.generate(context, lambda shown: answer(context, ["E9999"]))
        self.assertEqual(provider.calls, 1)
        self.assertEqual(generator.generation_metadata["status"], "fallback")
        self.assertEqual(generator.generation_metadata["error_code"], "TEXT_OUTPUT_INVALID")
        self.assertTrue(any(item.code == "TEXT_GENERATION_FALLBACK" for item in issues))
        self.assertNotIn("E9999", str(draft))

        prompt = tcg.build_planning_prompt(context)
        with self.assertRaises(ValueError):
            tcg.parse_concept_output(pb.resolve_output_aliases(answer(context, ["E9999"]), prompt.reduction.alias_to_real),
                                     context, prompt.allowed_evidence_ids)

    def test_t5_trimming_is_named_in_the_draft(self):
        # Request constraints are never reduced: they fill the data so that T5 drops 7 of the 10 products and
        # still has to cut the primary trend's description (2,000 chars) to fit.
        context = make_context(trends=60, description="다" * 2_000, ids_per_trend=4, products=10,
                               constraints=["가" * 2_000] * 10 + ["가" * 1_360])
        provider, generator, draft, issues = self.generate(
            context, lambda shown: answer(context, [first_trend_id(shown)]))
        metadata = generator.generation_metadata
        reduction = metadata["prompt_reduction"]
        self.assertEqual(metadata["status"], "generated")
        self.assertEqual(reduction["steps"], ["T1", "T2", "T3", "T4", "T5"])
        self.assertLessEqual(reduction["chars_after"], PROMPT_DATA_MAX_CHARS)
        self.assertEqual(reduction["trimmed"], {"inventory": 7, "descriptions": 1, "trends": 0})
        self.assertIn("텍스트 LLM 입력이 한도(24,000자)를 넘어 다음 입력은 LLM에 보내지 않았습니다: "
                      "재고 상품 7개, 트렌드 설명 1개의 160자 이후 부분.", draft.limitations)
        self.assertEqual(draft.limitations[:len(context.limitations)], context.limitations)

    def test_input_over_budget_after_reduction_never_reaches_the_provider(self):
        context = make_context(constraints=["가" * 2_000] * 100)
        prompt = tcg.build_planning_prompt(context)
        self.assertTrue(prompt.over_budget)
        self.assertEqual((prompt.user_prompt, prompt.allowed_evidence_ids), ("", frozenset()))
        provider, generator, draft, issues = self.generate(context, lambda shown: self.fail("provider was called"))
        metadata = generator.generation_metadata
        self.assertEqual(provider.calls, 0)
        self.assertEqual((metadata["engine"], metadata["status"], metadata["error_code"]),
                         ("rule_based", "fallback", "TEXT_INPUT_OVER_BUDGET"))
        self.assertGreater(metadata["prompt_reduction"]["chars_after"], PROMPT_DATA_MAX_CHARS)
        self.assertEqual(metadata["prompt_reduction"]["allowed_evidence_ids"], 0)
        self.assertIn(tcg.INPUT_OVER_BUDGET_LIMITATION, draft.limitations)
        self.assertTrue(any(item.code == "TEXT_GENERATION_FALLBACK" for item in issues))


if __name__ == "__main__":
    unittest.main()
