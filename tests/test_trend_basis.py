"""One primary trend per Draft (VOGUE decision 2026-11-17): selection rule, rule/LLM paths, record, images.

Offline only: fake providers, no network.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
import urllib.error
from dataclasses import asdict
from unittest.mock import patch

from vogue_npp.domain.analysis import analyze_opportunities
from vogue_npp.domain.concept import base_product_profile, validate_concept_draft
from vogue_npp.domain.context import (
    AgentResult,
    AttributeSignal,
    InventoryProductResult,
    PlanningInputs,
    PlanningRequest,
    TrendCandidate,
    TrendResult,
    build_planning_context,
)
from vogue_npp.domain.generator import RuleBasedConceptGenerator
from vogue_npp.domain.prompt_registry import PROMPT_ROOT
from vogue_npp.domain.trend_basis import (
    DESIGN_ATTRIBUTE_NAMES,
    TREND_SELECTION_RULE,
    build_trend_basis,
    select_primary_trend,
)
from vogue_npp.prototype.server import _build_handoff_run, _image_profile_from_draft
from vogue_npp.workflows import image_generation
from vogue_npp.workflows.planning_draft import _analyze_planning_inputs
from vogue_npp.workflows.text_concept_generation import (
    PLANNING_SYSTEM_PROMPT,
    PROMPT_VERSION,
    PromptedConceptGenerator,
    build_planning_prompt,
)

RID = "trend-basis-1"
SCHEMA = "1.0"
MARKER = "UNTRUSTED_PLANNING_INPUT_JSON:\n"


def signal(name, value, *ids):
    return AttributeSignal(name, value, "evidence_observation" if ids else "unknown", tuple(ids))


def trend(name, *attributes, ids=(), description_ids=(), description=None, style=None, season="2027SS",
          category="드레스"):
    return TrendCandidate(
        name=name, qualification="trend_analysis_result", season=season, category=category,
        attributes=tuple(attributes), evidence_ids=tuple(ids), description=description,
        description_evidence_ids=tuple(description_ids), source_style_id=style,
    )


def context_of(*candidates, trend_status="ok", request_status="ok"):
    # The trend envelope lists every ID it carries, as the P06 input normalizer does.
    all_ids = tuple(dict.fromkeys(
        evidence_id for candidate in candidates for evidence_id in (
            *candidate.evidence_ids, *candidate.description_evidence_ids,
            *(eid for item in candidate.attributes for eid in item.evidence_ids),
        )
    ))
    request = PlanningRequest(
        AgentResult("user-request", RID, SCHEMA, request_status), original_query="2027SS 여성 드레스 기획",
        season="2027SS", category="드레스", field_origins={"season": "user", "category": "user"},
    )
    trend_result = TrendResult(AgentResult("trend-analysis-agent", RID, SCHEMA, trend_status, evidence_ids=all_ids),
                               candidates=tuple(candidates))
    inventory = InventoryProductResult(AgentResult("stock-agent", RID, SCHEMA, "no_results"))
    return build_planning_context(PlanningInputs(request, trend_result, inventory))


def ids_of(candidate):
    return {*candidate.evidence_ids, *candidate.description_evidence_ids,
            *(eid for item in candidate.attributes for eid in item.evidence_ids)}


def cited_ids(draft):
    """Every Evidence ID the Draft's claims, attributes, findings and record cite.

    The top-level ``evidence_ids`` is the input Evidence registry (context.evidence_ids), not a citation.
    """
    into = set()

    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "evidence_ids" and isinstance(child, (list, tuple)):
                    into.update(child)
                else:
                    walk(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                walk(child)

    walk({key: value for key, value in asdict(draft).items() if key != "evidence_ids"})
    return into


# The live 2027SS dress run (req-synthetic) in miniature: the rule must pick 시럽코어 (two colours,
# most evidence), and 폴카 도트's pattern must not reach the plan.
POLKA = trend("폴카 도트 패턴", signal("pattern", "도트", "dot:1"), ids=("dot:0", "dot:1"),
              description="도트 원피스", description_ids=("dot:0",), style="990102-s0")
COLOUR = trend("컬러 트렌드", signal("color", "옐로우", "col:1"), ids=("col:0", "col:1"), style="990103-s0")
SYRUP = trend("시럽코어", signal("color", "옐로우", "syr:1"), signal("color", "스카이블루", "syr:2"),
              signal("mood", "달콤함", "syr:3"), ids=("syr:0", "syr:1", "syr:2"),
              description="파스텔 시럽 컬러", description_ids=("syr:4",), style="990104-s0")
PURPLE = trend("보라색", signal("color", "퍼플", "pur:1"), signal("color", "퍼플", "pur:2"),
               ids=("pur:1", "pur:2"), style="990106-s0")
WINTER = trend("겨울 니트", signal("material", "울", "win:1"), signal("pattern", "케이블", "win:1"),
               signal("fit", "오버", "win:1"), ids=("win:0", "win:1"), season="2026FW", style="900000-s0")
DRESS_TRENDS = (POLKA, COLOUR, SYRUP, PURPLE, WINTER)


def valid_output(context, cite):
    """A strict, valid model answer that cites `cite`."""
    base = base_product_profile(context)

    def claim(value, kind, ids=()):
        return {"value": value, "kind": kind, "evidence_ids": list(ids)}

    def same(item):
        return {"value": item.value, "kind": item.kind, "evidence_ids": list(item.evidence_ids)}

    return {
        "request_id": context.request_id,
        "opportunity": claim("기준 트렌드 관찰을 바탕으로 검토할 방향", "hypothesis", cite),
        "target_customer": claim(None, "unknown"),
        "product_definition": claim("파스텔 드레스 콘셉트 제안", "proposal"),
        "product_profile": {
            "category": same(base.category), "season": same(base.season), "gender": claim("unknown", "proposal"),
            "product_type": claim("lightweight jacket", "proposal"), "material": claim("cotton blend", "proposal"),
            "silhouette": claim("A라인", "proposal"), "color": claim("옐로우", "evidence_observation", cite),
            "details": [],
        },
        "attributes": [{"name": "color", "value": "옐로우", "kind": "evidence_observation", "evidence_ids": list(cite)}],
        "relation_to_own_products": [],
        "differentiation": [],
        "risks": [],
        "questions_for_validation": ["톤 범위를 확인해 주세요."],
        "limitations": [],
    }


class FakeProvider:
    model_name = "offline-trend-basis-v1"

    def __init__(self, respond=None, error=None):
        self.respond = respond
        self.error = error
        self.calls = 0
        self.user_prompt = None

    def generate_json(self, *, system_prompt, user_prompt):
        self.calls += 1
        self.user_prompt = user_prompt
        if self.error:
            raise RuntimeError(self.error)
        return self.respond


class SelectionRuleTests(unittest.TestCase):
    def test_most_design_attributes_wins_over_more_evidence(self):
        many_ids = trend("A", signal("color", "블랙", "a:1"), ids=("a:0", "a:1", "a:2", "a:3", "a:4"))
        two_attrs = trend("B", signal("color", "화이트", "b:1"), signal("fit", "슬림", "b:1"), ids=("b:0",))
        self.assertIs(select_primary_trend(context_of(many_ids, two_attrs)), two_attrs)

    def test_evidence_ids_break_a_design_attribute_tie(self):
        fewer = trend("A", signal("color", "블랙", "a:1"), ids=("a:0", "a:1"))
        # The extra ID is only a description ID: candidate, description and attribute IDs all count.
        more = trend("B", signal("color", "화이트", "b:1"), ids=("b:0", "b:1"), description="설명",
                     description_ids=("b:2",))
        self.assertIs(select_primary_trend(context_of(fewer, more)), more)
        self.assertIs(select_primary_trend(context_of(more, fewer)), more)

    def test_a_full_tie_goes_to_the_earliest_input(self):
        first = trend("A", signal("color", "블랙", "a:1"), ids=("a:0", "a:1"))
        second = trend("B", signal("color", "화이트", "b:1"), ids=("b:0", "b:1"))
        self.assertIs(select_primary_trend(context_of(first, second)), first)
        self.assertIs(select_primary_trend(context_of(second, first)), second)

    def test_only_evidence_linked_design_attributes_count(self):
        # mood is not a design attribute; an attribute without evidence or without a value does not count.
        uncounted = trend("A", signal("mood", "차분함", "a:1"), signal("color", "블랙"), signal("pattern", None, "a:2"),
                          ids=("a:0", "a:1", "a:2", "a:3"))
        korean = trend("B", signal("패턴", "체크", "b:1"), ids=("b:0",))
        plural = trend("C", signal("details", "프릴", "c:1"), ids=("c:0",))
        self.assertIs(select_primary_trend(context_of(uncounted, korean)), korean)
        self.assertIs(select_primary_trend(context_of(uncounted, plural)), plural)

    def test_mismatched_unnamed_and_unevidenced_candidates_are_never_selected(self):
        mismatched = trend("M", *(signal("color", f"c{i}", f"m:{i}") for i in range(5)), ids=("m:0",), season="2026FW")
        unnamed = trend("  ", *(signal("color", f"u{i}", f"u:{i}") for i in range(5)), ids=("u:0",))
        unevidenced = trend("N", *(signal("color", f"n{i}", f"n:{i}") for i in range(5)))
        plain = trend("P", signal("color", "블랙", "p:1"), ids=("p:0",))
        context = context_of(mismatched, unnamed, unevidenced, plain)
        self.assertIs(select_primary_trend(context), plain)
        self.assertEqual(build_trend_basis(context).candidates_considered, 1)

    def test_no_usable_trend_gives_none(self):
        mismatched = trend("M", signal("color", "블랙", "m:1"), ids=("m:0",), category="재킷")
        usable = trend("P", signal("color", "블랙", "p:1"), ids=("p:0",))
        for context in (context_of(), context_of(mismatched), context_of(usable, trend_status="error"),
                        context_of(usable, trend_status="no_results"), context_of(usable, request_status="error")):
            with self.subTest(statuses=dict(context.input_statuses), candidates=len(context.trends.candidates)):
                self.assertIsNone(select_primary_trend(context))
                self.assertIsNone(build_trend_basis(context))

    def test_record_traces_the_rule(self):
        context = context_of(*DRESS_TRENDS)
        self.assertEqual(asdict(build_trend_basis(context)), {
            "source_style_id": "990104-s0",
            "name": "시럽코어",
            "selection_rule": "most_evidence_linked_design_attributes/1",
            "evidence_ids": ("syr:0", "syr:1", "syr:2", "syr:4", "syr:3"),
            "design_attributes": (
                {"name": "color", "value": "옐로우", "evidence_ids": ("syr:1",)},
                {"name": "color", "value": "스카이블루", "evidence_ids": ("syr:2",)},
            ),
            "candidates_considered": 4,
        })
        self.assertEqual(TREND_SELECTION_RULE, "most_evidence_linked_design_attributes/1")

    def test_selection_and_image_prompt_share_one_design_name_set(self):
        self.assertIs(image_generation._DESIGN_ATTRIBUTE_NAMES, DESIGN_ATTRIBUTE_NAMES)
        for name in ("color", "colour", "pattern", "print", "detail", "details", "material", "fabric", "fit",
                     "silhouette", "length", "texture", "decoration", "색상", "패턴", "디테일", "소재", "핏", "실루엣"):
            self.assertIn(name, DESIGN_ATTRIBUTE_NAMES)


class RuleDraftTests(unittest.TestCase):
    def test_rule_draft_is_planned_around_the_primary_trend_only(self):
        context = context_of(*DRESS_TRENDS)
        draft, issues = RuleBasedConceptGenerator().generate(context)
        serialized = json.dumps(asdict(draft), ensure_ascii=False)
        self.assertEqual(issues, ())
        self.assertIn("시럽코어", draft.product_definition.value)
        self.assertIn("color=옐로우, color=스카이블루", draft.product_definition.value)
        self.assertIn("파스텔 시럽 컬러", draft.product_definition.value)
        self.assertIn("'시럽코어'", draft.opportunity.value)
        # The other usable trends are not mixed in anywhere in the Draft.
        for other in ("폴카 도트 패턴", "컬러 트렌드", "보라색", "도트", "퍼플"):
            self.assertNotIn(other, serialized)
        # A mismatched candidate is only named in the existing exclusion note.
        self.assertNotIn("겨울 니트", draft.product_definition.value + draft.opportunity.value)
        self.assertTrue(any("겨울 니트" in question and "요청 조건과 달라" in question
                            for question in draft.questions_for_validation))
        trend_ids = set().union(*(ids_of(candidate) for candidate in DRESS_TRENDS))
        self.assertEqual(cited_ids(draft) & trend_ids, ids_of(SYRUP))
        self.assertEqual(set(draft.product_definition.evidence_ids), ids_of(SYRUP))
        self.assertEqual({finding.trend_name for finding in draft.opportunity_findings}, {"시럽코어"})
        self.assertEqual(draft.trend_basis, build_trend_basis(context))

    def test_profile_attributes_are_a_subset_of_the_primary_trends(self):
        cowboy = trend("카우보이 스타일", signal("detail", "프린지", "cow:1"), signal("color", "브라운", "cow:2"),
                       signal("material", "스웨이드", "cow:3"), ids=("cow:0",), category="재킷", style="990101-s0")
        toothpaste = trend("치약 드레싱", signal("color", "민트", "tp:1"), signal("pattern", "스트라이프", "tp:2"),
                           ids=("tp:0", "tp:3", "tp:4", "tp:5"), category="재킷", style="tp-s0")
        candidates = (toothpaste, cowboy)
        context = build_planning_context(PlanningInputs(
            PlanningRequest(AgentResult("user-request", RID, SCHEMA, "ok"), season="2027SS", category="재킷",
                            field_origins={"season": "user", "category": "user"}),
            TrendResult(AgentResult("trend-analysis-agent", RID, SCHEMA, "ok",
                                    evidence_ids=tuple(sorted(set().union(*map(ids_of, candidates))))),
                        candidates=candidates),
            InventoryProductResult(AgentResult("stock-agent", RID, SCHEMA, "no_results")),
        ))
        draft, issues = RuleBasedConceptGenerator().generate(context)
        self.assertEqual(issues, ())
        primary_pairs = {(item.name, item.value) for item in cowboy.attributes}
        profile = draft.product_profile
        self.assertLessEqual({(item.name, item.value) for item in profile.details}, primary_pairs)
        self.assertEqual((profile.color.value, profile.material.value), ("브라운", "스웨이드"))
        self.assertLessEqual({(item.name, item.value) for item in draft.attributes}, primary_pairs)
        # The images follow the profile: only the primary trend's attributes reach the image specification.
        self.assertEqual(_image_profile_from_draft(asdict(draft)), {
            "category": "재킷", "season": "2027SS", "color": "브라운", "material": "스웨이드", "details": ["프린지"],
            # 빈 필드는 정해진 검토 제안값을 받고, 다른 트렌드의 값은 받지 않는다.
            "product_type": "가벼운 아우터", "gender": "unknown", "silhouette": "레귤러 핏",
        })

    def test_without_a_primary_trend_the_analysis_keeps_every_eligible_trend(self):
        context = context_of(*DRESS_TRENDS)
        names = {finding.trend_name for finding in analyze_opportunities(context).findings}
        self.assertEqual(names, {"폴카 도트 패턴", "컬러 트렌드", "시럽코어", "보라색"})
        primary_only = analyze_opportunities(context, primary_trend=select_primary_trend(context))
        self.assertEqual({finding.trend_name for finding in primary_only.findings}, {"시럽코어"})

    def test_no_usable_trend_leaves_trend_basis_null(self):
        context = context_of(WINTER)
        draft, _ = RuleBasedConceptGenerator().generate(context)
        self.assertIsNone(draft.trend_basis)
        self.assertNotIn("겨울 니트", draft.opportunity.value + draft.product_definition.value)
        self.assertEqual(draft.product_profile.details, ())


def colour_of(draft):
    claim = draft.product_profile.color
    return claim.value, claim.kind, claim.evidence_ids


class FirstEvidenceColourTests(unittest.TestCase):
    """VOGUE decision 2026-11-17: a primary trend with 2+ colours passes its first evidence colour."""

    def test_rule_profile_and_image_take_the_first_evidence_colour(self):
        draft, issues = RuleBasedConceptGenerator().generate(context_of(*DRESS_TRENDS))
        self.assertEqual(issues, ())
        self.assertEqual(colour_of(draft), ("옐로우", "evidence_observation", ("syr:1",)))
        self.assertEqual(_image_profile_from_draft(asdict(draft))["color"], "옐로우")

    def test_a_colour_without_evidence_is_passed_over(self):
        two_tone = trend("투톤", signal("color", "화이트"), signal("color", "블랙", "tt:1"),
                         signal("detail", "포켓", "tt:2"), ids=("tt:0",), style="tt-s0")
        draft, _ = RuleBasedConceptGenerator().generate(context_of(two_tone))
        self.assertEqual(colour_of(draft), ("블랙", "evidence_observation", ("tt:1",)))

    def test_material_and_silhouette_keep_the_one_value_rule(self):
        mixed = trend("믹스 소재", signal("color", "네이비", "mx:1"), signal("color", "아이보리", "mx:2"),
                      signal("material", "린넨", "mx:3"), signal("material", "코튼", "mx:4"),
                      ids=("mx:0",), style="mx-s0")
        profile = RuleBasedConceptGenerator().generate(context_of(mixed))[0].product_profile
        self.assertEqual(profile.color.value, "네이비")
        # 근거 소재가 둘이면 어느 쪽도 올리지 않는다. 빈 필드는 대신 표시된 검토 제안값을 받는다.
        self.assertNotIn(profile.material.value, {"린넨", "코튼"})
        self.assertEqual((profile.material.kind, profile.material.evidence_ids), ("proposal", ()))
        self.assertEqual((profile.silhouette.kind, profile.silhouette.evidence_ids), ("proposal", ()))

    def test_a_requested_colour_is_kept(self):
        context = build_planning_context(PlanningInputs(
            PlanningRequest(AgentResult("user-request", RID, SCHEMA, "ok"), original_query="블랙 드레스 기획",
                            season="2027SS", category="드레스", field_origins={"season": "user", "category": "user"},
                            requested_attributes=(AttributeSignal("color", "블랙", "user_requested", ()),)),
            TrendResult(AgentResult("trend-analysis-agent", RID, SCHEMA, "ok",
                                    evidence_ids=tuple(sorted(ids_of(SYRUP)))), candidates=(SYRUP,)),
            InventoryProductResult(AgentResult("stock-agent", RID, SCHEMA, "no_results")),
        ))
        draft, _ = RuleBasedConceptGenerator().generate(context)
        self.assertEqual(draft.product_profile.color.value, "블랙")
        self.assertEqual(draft.product_profile.color.kind, "user_requested")

    def test_the_model_path_applies_the_same_colour_rule(self):
        context = context_of(*DRESS_TRENDS)
        output = valid_output(context, ["syr:2"])
        sky = {"value": "스카이블루", "kind": "evidence_observation", "evidence_ids": ["syr:2"]}
        output["product_profile"]["color"] = sky
        output["attributes"] = [{"name": "color", **sky}]
        generator = PromptedConceptGenerator(provider=FakeProvider(output), enabled=True)
        draft, _ = generator.generate(context)
        self.assertEqual(generator.generation_metadata["status"], "generated")
        self.assertEqual(colour_of(draft), ("옐로우", "evidence_observation", ("syr:1",)))
        # The Draft stays consistent: the profile colour is one of its colour attributes.
        self.assertIn(("color", "옐로우"), {(item.name, item.value) for item in draft.attributes})
        self.assertEqual(validate_concept_draft(context, draft), ())
        self.assertEqual(_image_profile_from_draft(asdict(draft))["color"], "옐로우")

    def test_the_model_colour_stays_for_a_single_colour_trend(self):
        context = context_of(COLOUR)
        output = valid_output(context, ["col:1"])
        cream = {"value": "크림", "kind": "proposal", "evidence_ids": []}
        output["product_profile"]["color"] = cream
        output["attributes"] = [{"name": "color", **cream}]
        generator = PromptedConceptGenerator(provider=FakeProvider(output), enabled=True)
        draft, _ = generator.generate(context)
        self.assertEqual(generator.generation_metadata["status"], "generated")
        self.assertEqual(colour_of(draft), ("크림", "proposal", ()))


class TextPathTests(unittest.TestCase):
    def test_prompt_data_holds_only_the_primary_trend(self):
        context = context_of(*DRESS_TRENDS)
        prompt = build_planning_prompt(context)
        data = json.loads(prompt.user_prompt.split(MARKER, 1)[1])
        self.assertEqual(data["primary_trend"], {"name": "시럽코어", "selection_rule": TREND_SELECTION_RULE})
        self.assertEqual([item["name"] for item in data["trend_candidates"]], ["시럽코어"])
        self.assertLessEqual(ids_of(SYRUP), prompt.allowed_evidence_ids)
        for other in (POLKA, COLOUR, PURPLE, WINTER):
            self.assertFalse(ids_of(other) & prompt.allowed_evidence_ids)
            self.assertNotIn(other.name, prompt.user_prompt)

    def test_prompt_without_a_usable_trend_sends_no_trend(self):
        data = json.loads(build_planning_prompt(context_of(WINTER)).user_prompt.split(MARKER, 1)[1])
        self.assertIsNone(data["primary_trend"])
        self.assertEqual(data["trend_candidates"], [])

    def test_prompt_v8_tells_the_model_to_plan_around_the_primary_trend(self):
        manifest = json.loads((PROMPT_ROOT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["text_planning"]["version"], "v8")
        self.assertEqual(PROMPT_VERSION, "new-product-planner-v8-llm-required-profile")
        self.assertIn("기준 트렌드를 중심으로 기획하고, 다른 트렌드를 새로 들여오거나 섞지 않는다", PLANNING_SYSTEM_PROMPT)
        self.assertIn("`primary_trend`", PLANNING_SYSTEM_PROMPT)

    def test_trend_basis_is_the_rule_record_on_generated_and_fallback_drafts(self):
        context = context_of(*DRESS_TRENDS)
        expected = build_trend_basis(context)
        cases = {
            "generated": PromptedConceptGenerator(provider=FakeProvider(valid_output(context, ["syr:1"])), enabled=True),
            "fallback": PromptedConceptGenerator(provider=FakeProvider(error="provider down"), enabled=True),
            "disabled": PromptedConceptGenerator(enabled=False),
            "unavailable": PromptedConceptGenerator(enabled=True),
        }
        for status, generator in cases.items():
            with self.subTest(status=status):
                draft, _ = generator.generate(context)
                self.assertEqual(generator.generation_metadata["status"], status)
                self.assertEqual(draft.trend_basis, expected)

    def test_the_model_cannot_choose_the_trend(self):
        context = context_of(*DRESS_TRENDS)
        output = valid_output(context, ["syr:1"])
        output["trend_basis"] = {"name": "폴카 도트 패턴"}
        generator = PromptedConceptGenerator(provider=FakeProvider(output), enabled=True)
        draft, _ = generator.generate(context)
        self.assertEqual(generator.generation_metadata["status"], "fallback")
        self.assertEqual(draft.trend_basis.name, "시럽코어")

    def test_generated_and_fallback_drafts_have_null_trend_basis_without_a_usable_trend(self):
        context = context_of(WINTER)
        output = valid_output(context, [])
        output["opportunity"] = {"value": "요청 범위 검토", "kind": "hypothesis", "evidence_ids": []}
        output["product_profile"]["color"] = {"value": None, "kind": "unknown", "evidence_ids": []}
        output["attributes"] = []
        for generator in (PromptedConceptGenerator(provider=FakeProvider(output), enabled=True),
                          PromptedConceptGenerator(provider=FakeProvider(error="down"), enabled=True)):
            draft, _ = generator.generate(context)
            self.assertIn(generator.generation_metadata["status"], {"generated", "fallback"})
            self.assertIsNone(draft.trend_basis)


def trend_payload(request_id):
    """trend_result in the P08 `trends` shape (style + items)."""
    return {
        "schema_version": "1.0", "request_id": request_id, "status": "ok",
        "trends": [
            {"style": {"id": "990102-s0", "name": "폴카 도트 패턴", "seasons": ["2027SS"], "focus_evidence_ids": ["dot:0"]},
             "items": [{"id": "990102-s0-i0", "patterns": ["도트"], "evidence_ids": ["dot:1"]}]},
            {"style": {"id": "990104-s0", "name": "시럽코어", "seasons": ["2027SS"], "focus_evidence_ids": ["syr:0"],
                       "description": [{"text": "파스텔 시럽 컬러", "evidence_ids": ["syr:4"]}]},
             "items": [{"id": "990104-s0-i0", "colors": ["옐로우"], "evidence_ids": ["syr:1"]},
                       {"id": "990104-s0-i2", "colors": ["스카이블루"], "evidence_ids": ["syr:2"]}]},
        ],
    }


class SerializationTests(unittest.TestCase):
    def payload(self, trends=True):
        rid = "trend-basis-wire-1"
        return {
            "planning_request": {"schema_version": "1.0", "request_id": rid, "query": "2027SS 여성 드레스",
                                 "context": {"category": "드레스", "season": "2027SS"}},
            "trend_result": trend_payload(rid) if trends else {"schema_version": "1.0", "request_id": rid,
                                                              "status": "ok", "trends": []},
            "inventory_product_result": {"schema_version": "1.0", "request_id": rid, "agent_id": "stock-agent",
                                         "status": "ok", "products": []},
        }

    def test_trend_basis_is_serialized_in_the_draft(self):
        response = _analyze_planning_inputs(self.payload())
        wire = json.loads(json.dumps(response, ensure_ascii=False))["draft"]["trend_basis"]
        self.assertEqual(list(wire), ["source_style_id", "name", "selection_rule", "evidence_ids",
                                      "design_attributes", "candidates_considered"])
        self.assertEqual(wire, {
            "source_style_id": "990104-s0", "name": "시럽코어",
            "selection_rule": "most_evidence_linked_design_attributes/1",
            "evidence_ids": ["syr:0", "syr:4", "syr:1", "syr:2"],
            "design_attributes": [{"name": "color", "value": "옐로우", "evidence_ids": ["syr:1"]},
                                  {"name": "color", "value": "스카이블루", "evidence_ids": ["syr:2"]}],
            "candidates_considered": 2,
        })
        self.assertNotIn("도트", json.dumps(response["draft"], ensure_ascii=False))

    def test_trend_basis_is_null_without_a_usable_trend(self):
        response = _analyze_planning_inputs(self.payload(trends=False))
        self.assertIn('"trend_basis": null', json.dumps(response["draft"], ensure_ascii=False))

    def test_handoff_response_carries_the_trend_basis(self):
        payload = self.payload()
        rid = payload["planning_request"]["request_id"]
        payload["trend_result"]["schema_version"] = "1.1"
        guard = patch("urllib.request.urlopen", side_effect=urllib.error.URLError(OSError("network disabled")))
        with tempfile.TemporaryDirectory() as directory, guard, patch.dict(os.environ, {
            "VOGUE_DRAFT_ARTIFACT_DIR": directory, "VOGUE_DRAFT_IMAGE_PROVIDER": "",
            "VOGUE_TEXT_GENERATION_ENABLED": "false",
        }), contextlib.redirect_stderr(io.StringIO()):
            response = _build_handoff_run({"contract_version": "vogue-handoff/0.3", "request_id": rid,
                                           "input": payload})
        basis = response["result"]["draft"]["trend_basis"]
        self.assertEqual((basis["source_style_id"], basis["name"]), ("990104-s0", "시럽코어"))
        self.assertEqual(response["result"]["generation_metadata"]["status"], "disabled")


if __name__ == "__main__":
    unittest.main()
