"""research로 넘어가는 프로필 값은 research 계약의 길이 상한(120자)을 지킨다.

넘는 값은 규칙 기반 Draft의 값으로, 그것도 길면 카테고리별 검토 제안값으로 바꾸고, 바꾼 필드를
generation_metadata.length_limited_fields에 남긴다. category·season은 요청 식별자라 길면 거절한다.
"""
import copy
import unittest

from fashion_planner_novelty.domain.generator import RESEARCH_FIELD_MAX_CHARS
from fashion_planner_novelty.server.app import _analyze_planning_inputs
from fashion_planner_novelty.workflows.text_concept_generation import PromptedConceptGenerator
from test_text_concept_generation import FakeStructuredProvider, valid_output

RID = "text-plan-1"


def claim(value):
    """asdict 결과(tuple)와 JSON 결과(list)를 같은 모양으로 비교한다."""
    return value["value"], value["kind"], list(value["evidence_ids"])


def llm_payload(category="outerwear", season="27SS"):
    return {
        "planning_request": {"request_id": RID, "schema_version": "1.0", "query": "27SS 아우터 기획",
                             "season": season, "category": category},
        "trend_result": {"request_id": RID, "schema_version": "1.0", "status": "partial",
                         "evidence_ids": ["trend:E-1"],
                         "trends": [{"style": {"name": "urban utility", "seasons": ["27SS"],
                                               "category_major": "outerwear", "focus_evidence_ids": ["trend:E-1"]},
                                     "items": []}]},
        "inventory_product_result": {"request_id": RID, "schema_version": "1.0", "status": "no_results",
                                     "products": []},
    }


def run_with_model_profile(**profile_values):
    output = valid_output()
    for name, value in profile_values.items():
        output["product_profile"][name] = {"value": value, "kind": "proposal", "evidence_ids": []}
    generator = PromptedConceptGenerator(provider=FakeStructuredProvider(output), enabled=True)
    return _analyze_planning_inputs(copy.deepcopy(llm_payload()), concept_generator=generator)


def rule_payload(material):
    rid = "length-limit-rule-1"
    return {
        "request_id": rid,
        "planning_request": {"schema_version": "1.0", "request_id": rid, "status": "ok",
                             "context": {"category": "아우터", "season": "2027SS"}},
        "trend_result": {
            "schema_version": "1.0", "request_id": rid, "status": "ok",
            "candidates": [{
                "name": "utility", "qualification": "candidate", "season": "2027SS", "category": "아우터",
                "evidence_ids": ["trend-1"],
                "attributes": [{"name": "material", "value": material, "origin": "evidence_observation",
                                "evidence_ids": ["trend-1"]}],
            }],
        },
        "inventory_product_result": {"schema_version": "1.0", "request_id": rid, "agent_id": "inventory",
                                     "status": "no_results"},
    }


class ResearchFieldLimitTests(unittest.TestCase):
    def test_the_limit_matches_the_research_contract(self):
        self.assertEqual(RESEARCH_FIELD_MAX_CHARS, 120)

    def test_a_long_model_value_is_replaced_by_the_rule_value(self):
        response = run_with_model_profile(product_type="가" * 121)
        profile = response["draft"]["product_profile"]
        self.assertEqual(claim(profile["product_type"]), ("가벼운 아우터", "proposal", []))
        self.assertEqual(response["generation_metadata"]["status"], "generated")
        self.assertEqual(response["generation_metadata"]["length_limited_fields"], ["product_profile.product_type"])

    def test_a_value_of_exactly_the_limit_is_kept(self):
        response = run_with_model_profile(material="나" * 120)
        self.assertEqual(response["draft"]["product_profile"]["material"]["value"], "나" * 120)
        self.assertEqual(response["generation_metadata"]["length_limited_fields"], [])

    def test_every_research_field_fits_after_the_guard(self):
        response = run_with_model_profile(product_type="가" * 300, material="나" * 2_000)
        profile = response["draft"]["product_profile"]
        for name in ("category", "product_type", "gender", "season", "material"):
            with self.subTest(field=name):
                self.assertLessEqual(len(profile[name]["value"]), RESEARCH_FIELD_MAX_CHARS)
        self.assertEqual(response["generation_metadata"]["length_limited_fields"],
                         ["product_profile.product_type", "product_profile.material"])

    def test_a_long_rule_value_falls_back_to_the_category_proposal(self):
        long_material = "재생 나일론과 " * 20
        self.assertGreater(len(long_material), RESEARCH_FIELD_MAX_CHARS)
        response = _analyze_planning_inputs(rule_payload(long_material))
        self.assertEqual(claim(response["draft"]["product_profile"]["material"]), ("나일론 혼방", "proposal", []))
        self.assertEqual(response["generation_metadata"]["length_limited_fields"], ["product_profile.material"])

    def test_a_short_rule_value_is_untouched(self):
        response = _analyze_planning_inputs(rule_payload("재생 나일론"))
        material = response["draft"]["product_profile"]["material"]
        self.assertEqual((material["value"], material["kind"]), ("재생 나일론", "evidence_observation"))
        self.assertEqual(response["generation_metadata"]["length_limited_fields"], [])

    def test_a_long_request_category_or_season_is_rejected(self):
        for field_name in ("category", "season"):
            with self.subTest(field=field_name):
                payload = llm_payload(**{field_name: "x" * (RESEARCH_FIELD_MAX_CHARS + 1)})
                with self.assertRaises(ValueError) as raised:
                    _analyze_planning_inputs(payload)
                self.assertIn(field_name, str(raised.exception))


if __name__ == "__main__":
    unittest.main()
