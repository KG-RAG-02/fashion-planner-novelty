"""Tests for the planning-draft handoff the orchestrator calls."""
import base64
import copy
import contextlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
import hashlib
import io
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fashion_planner_novelty.domain.concept import ProductProfile, ProposedAttribute, SourcedClaim
from fashion_planner_novelty.domain.generator import RuleBasedConceptGenerator
from fashion_planner_novelty.server.app import NoveltyRequestHandler, _build_handoff_run, _image_profile_from_draft
from fashion_planner_novelty.workflows.draft_artifacts import DraftArtifactStore, ImageRunAlreadyClaimed, OpenAIDraftImageProvider
from fashion_planner_novelty.workflows.image_generation import ImageProviderError, OpenAIImageEditProvider, OpenAIImageProvider

SEQUENTIAL_IMAGE_POLICY = "sequential: product generation, then outfit edit of the product image; no automatic retry"

FIXTURE = Path(__file__).parent / "fixtures/workflow-inputs/success.json"
# 규칙 기반 Draft는 픽스처의 빈 디자인 필드를 표시된 검토 제안값으로 채운다
# (generator._complete_product_profile_with_proposals). 이 값도 이미지 사양에 들어간다.
FIXTURE_PROPOSALS = {"color": "뉴트럴 톤", "gender": "unknown", "material": "나일론 혼방",
                     "product_type": "가벼운 아우터", "silhouette": "레귤러 핏"}


def request():
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    value["contract_version"] = "novelty-handoff"
    value["input"]["planning_request"].update(category="Outerwear", season="spring/summer 2027")
    return value


def invoke(handler_type, path, value, *, env):
    body = json.dumps(value).encode()
    handler = object.__new__(handler_type)
    handler.path = path
    handler.headers = Message()
    handler.headers["Content-Type"] = "application/json"
    handler.headers["Content-Length"] = str(len(body))
    if env.get("NOVELTY_HTTP_MODE") in {"private", "service"}:
        handler.headers["Authorization"] = f"Bearer {env['FASHION_PLANNER_SERVICE_TOKEN']}"
    handler.rfile = __import__("io").BytesIO(body)
    handler.wfile = SimpleNamespace(body=b"", status=None)
    handler.wfile.write = lambda data: setattr(handler.wfile, "body", handler.wfile.body + data)
    handler.client_address = ("127.0.0.1", 1234)
    handler.send_response = lambda status: setattr(handler.wfile, "status", status)
    handler.send_header = lambda *_: None
    handler.end_headers = lambda: None
    with patch.dict(os.environ, env, clear=False):
        handler.do_POST()
    return handler.wfile.status, json.loads(handler.wfile.body)


class HandoffRunTests(unittest.TestCase):
    def setUp(self):
        # These tests patch load_settings with a fake key, which also enables the text LLM path. Block every real
        # outbound HTTP call so no test depends on, or reaches, a provider; a test that inspects HTTP patches again.
        guard = patch("urllib.request.urlopen",
                      side_effect=urllib.error.URLError(OSError("network is disabled in tests")))
        guard.start()
        self.addCleanup(guard.stop)

    def test_image_profile_keeps_details_of_an_asdict_draft(self):
        # The live Draft comes from dataclasses.asdict, so ProductProfile.details arrives as a tuple, not a list.
        profile = ProductProfile(
            category=SourcedClaim("재킷", "user_requested"), product_type=SourcedClaim(None, "unknown"),
            gender=SourcedClaim("men", "user_requested"), season=SourcedClaim("2026FW", "user_requested"),
            material=SourcedClaim(None, "unknown"),
            silhouette=SourcedClaim("페플럼", "evidence_observation", ("trend:1:0:aaaaaaaa",)),
            color=SourcedClaim(None, "unknown"),
            details=(
                ProposedAttribute("detail", "프린지", "evidence_observation", ("trend:1:1:bbbbbbbb",)),
                ProposedAttribute("pattern", "체크", "proposal"),
                ProposedAttribute("detail", "미확인 장식", "to_validate"),
            ),
        )
        draft = {"product_profile": asdict(profile)}
        self.assertIsInstance(draft["product_profile"]["details"], tuple)
        self.assertEqual(_image_profile_from_draft(draft), {
            "category": "재킷", "gender": "men", "season": "2026FW", "silhouette": "페플럼",
            "details": ["프린지", "체크"],
        })
        no_details = {"product_profile": asdict(replace(profile, details=()))}
        self.assertNotIn("details", _image_profile_from_draft(no_details))

    def test_image_profile_excludes_unverified_and_unknown_detail_claims(self):
        result = _image_profile_from_draft({"product_profile": {
            "category": {"value": "knitwear", "kind": "user_requested"},
            "material": {"value": "silk", "kind": "to_validate"},
            "details": [
                {"value": "lace trim", "kind": "proposal"},
                {"value": "unverified blend", "kind": "to_validate"},
                {"value": "", "kind": "user_requested"},
                {"value": "unknown trim", "kind": "unknown"},
            ],
        }})
        self.assertEqual(result, {"category": "knitwear", "details": ["lace trim"]})

    def test_live_reproduction_preserves_user_values_and_does_not_promote_unverified_material(self):
        value = request()
        value["request_id"] = "synthetic-live-run"
        for source in value["input"].values():
            source["request_id"] = value["request_id"]
        planning = value["input"]["planning_request"]
        planning["query"] = "27년도 봄 여성 니트 제안해줘"
        planning["context"] = {"category": "니트웨어", "season": "2027SS"}
        trend = value["input"]["trend_result"]
        trend["status"] = "ok"
        warning = "find_categories rule_violation on first attempt; valid re-selection completed"
        trend["limitations"] = [warning]
        trend["evidence"] = [{"evidence_id": "trend-color-e1"}]
        trend["trend_candidates"] = [{
            "name": "봄 니트 방향", "qualification": "candidate", "category": "니트웨어",
            "season": "2027SS", "evidence_ids": ["trend-color-e1"],
            "attributes": [
                {"name": "color", "value": "navy", "evidence_ids": ["trend-color-e1"]},
                {"name": "material", "value": "silk"},
            ],
        }]
        value["input"]["inventory_product_result"]["status"] = "ok"
        value["input"]["inventory_product_result"]["products"] = []
        prompts = []
        references = []

        def capture_image(image_request):
            prompts.append(image_request.prompt)
            return SimpleNamespace(image_bytes=f"mock-image-{len(prompts)}".encode())

        def capture_edit(image_request, reference_image, **_kwargs):
            references.append(reference_image)
            return capture_image(image_request)

        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "NOVELTY_DRAFT_ARTIFACT_DIR": directory, "NOVELTY_DRAFT_IMAGE_PROVIDER": "openai",
        }), patch("fashion_planner_novelty.server.app.load_settings",
                  return_value=SimpleNamespace(image_generation_api_key="test-key")), \
             patch.object(OpenAIImageProvider, "generate", side_effect=capture_image), \
             patch.object(OpenAIImageEditProvider, "edit", side_effect=capture_edit):
            response = _build_handoff_run(value)
        self.assertEqual(references, [b"mock-image-1"])  # the outfit edits the stored product image

        draft = response["result"]["draft"]
        profile = draft["product_profile"]
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["result"]["input_statuses"], {
            "planning_request": "ok", "trend_result": "ok", "inventory_product_result": "ok",
        })
        self.assertEqual(draft["category"], "니트웨어")
        self.assertEqual(draft["season"], "2027SS")
        self.assertEqual(draft["field_origins"]["category"], "user")
        self.assertEqual(draft["field_origins"]["season"], "user")
        self.assertEqual(profile["category"]["kind"], "user_requested")
        self.assertEqual(profile["season"]["kind"], "user_requested")
        self.assertEqual(profile["material"]["value"], "silk")
        self.assertEqual(profile["material"]["kind"], "to_validate")
        self.assertEqual(profile["color"]["kind"], "evidence_observation")
        self.assertIn(warning, response["result"]["limitations"])
        self.assertEqual(response["result"]["validation_issues"], [])
        self.assertEqual(len(prompts), 2)
        self.assertTrue(all("navy" in prompt for prompt in prompts))
        self.assertTrue(all("silk" not in prompt for prompt in prompts))
        self.assertTrue(all(visual["status"] == "generated" for visual in draft["visuals"].values()))

    def test_explicit_upstream_missing_data_keeps_partial_with_a_specific_issue(self):
        value = request()
        trend = value["input"]["trend_result"]
        trend["status"] = "ok"
        trend["missing_data"] = ["trend evidence coverage incomplete"]

        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "NOVELTY_DRAFT_ARTIFACT_DIR": directory, "NOVELTY_DRAFT_IMAGE_PROVIDER": "openai",
        }), patch("fashion_planner_novelty.server.app.load_settings",
                  return_value=SimpleNamespace(image_generation_api_key="test-key")), \
             patch.object(OpenAIDraftImageProvider, "generate", return_value=b"mock-image"):
            response = _build_handoff_run(value)

        self.assertEqual(response["status"], "partial")
        codes = {issue["code"] for issue in response["result"]["validation_issues"]}
        self.assertIn("UPSTREAM_DATA_MISSING", codes)

    def test_complete_deliverables_with_informational_limitations_are_ok(self):
        value = request()
        value["input"]["trend_result"].update(status="ok", limitations=["재고·판매가는 가상 데이터(sample)입니다."])
        value["input"]["inventory_product_result"]["status"] = "ok"

        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "NOVELTY_DRAFT_ARTIFACT_DIR": directory, "NOVELTY_DRAFT_IMAGE_PROVIDER": "openai",
        }), patch("fashion_planner_novelty.server.app.load_settings",
                  return_value=SimpleNamespace(image_generation_api_key="test-key")), \
             patch.object(OpenAIDraftImageProvider, "generate", return_value=b"mock-image"):
            response = _build_handoff_run(value)

        # Deliverable-based status: the Draft and both visuals exist and every input is ok.
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["result"]["status"], "ok")
        codes = {issue["code"] for issue in response["result"]["validation_issues"]}
        self.assertIn("INPUT_LIMITATION_PRESENT", codes)  # the limitation stays visible for review
        self.assertIn("재고·판매가는 가상 데이터(sample)입니다.", response["result"]["limitations"])

    def test_safe_logs_correlate_cache_and_http_serialization_timings(self):
        value = request()
        logs = io.StringIO()
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "NOVELTY_DRAFT_ARTIFACT_DIR": directory, "NOVELTY_DRAFT_IMAGE_PROVIDER": "",
        }), contextlib.redirect_stderr(logs):
            status, response = invoke(NoveltyRequestHandler, "/v1/agents/novelty/runs", value, env={})
        events = [json.loads(line) for line in logs.getvalue().splitlines()]
        completion = next(event for event in events if event["event"] == "novelty_draft_completed")
        http = next(event for event in events if event["event"] == "novelty_http_response_serialized")
        self.assertEqual(status, 200)
        self.assertEqual(completion["request_id"], value["request_id"])
        self.assertIn("response_cache_persistence", completion["timings_ms"])
        self.assertIn("total_processing_including_cache", completion["timings_ms"])
        self.assertEqual(http["request_id"], value["request_id"])
        self.assertEqual(http["http_status"], 200)
        self.assertIsInstance(http["http_response_serialization_ms"], int)
        self.assertNotIn("mock-key", logs.getvalue())

    def test_native_response_envelope_and_required_result_fields(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "NOVELTY_DRAFT_ARTIFACT_DIR": directory, "NOVELTY_DRAFT_IMAGE_PROVIDER": "",
        }):
            response = _build_handoff_run(request())
        self.assertEqual(set(response), {"contract_version", "request_id", "producer", "status", "result"})
        self.assertEqual(response["contract_version"], "novelty-handoff")
        self.assertEqual(response["producer"], {"agent_id": "novelty", "schema_version": "1.0.0"})
        result = response["result"]
        self.assertEqual(result["schema_version"], "1.0.0")
        self.assertEqual(result["request_id"], response["request_id"])
        self.assertEqual(result["status"], response["status"])
        self.assertEqual(result["input_evidence"]["trend_result"]["source_schema_version"], "1.0.0")
        self.assertEqual(result["input_evidence"]["trend_result"]["payload"]["schema_version"], "1.0.0")
        self.assertEqual(result["compatibility"]["input_schemas"]["trend_result"]["internal_schema_version"], "1.0.0")
        self.assertIn("product_profile", result["draft"])
        self.assertEqual(result["draft"]["product_profile"]["category"]["value"], "Outerwear")
        self.assertEqual(result["draft"]["category"], result["draft"]["product_profile"]["category"]["value"])
        self.assertEqual(set(result["draft"]["visuals"]), {"product", "outfit"})
        self.assertIsNone(result["planning_board"])

    def test_real_provider_creates_request_owned_product_and_outfit_artifacts(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "NOVELTY_DRAFT_ARTIFACT_DIR": directory, "NOVELTY_DRAFT_IMAGE_PROVIDER": "openai",
        }), patch("fashion_planner_novelty.server.app.load_settings", return_value=SimpleNamespace(image_generation_api_key="test-key")), \
             patch.object(OpenAIDraftImageProvider, "generate", return_value=b"synthetic-test-image") as generate:
            response = _build_handoff_run(request())
            result = response["result"]
            self.assertEqual(generate.call_count, 2)
            self.assertEqual(set(result["draft"]["visuals"]), {"product", "outfit"})
            store = DraftArtifactStore(directory)
            for kind, visual in result["draft"]["visuals"].items():
                artifact = visual["artifact"]
                self.assertTrue(store.owns(response["request_id"], kind, artifact))
                data = store.resolve(response["request_id"], kind, artifact).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), artifact["sha256"])
                self.assertEqual(len(data), artifact["size_bytes"])
            with self.assertRaises(PermissionError):
                store.resolve("another-request", "product", result["draft"]["visuals"]["product"]["artifact"])
            self.assertEqual(_build_handoff_run(request()), response)
            self.assertEqual(generate.call_count, 2)
            self.assertEqual([call.args[0] for call in generate.call_args_list], ["product", "outfit"])
            self.assertNotIn("reference_image", generate.call_args_list[0].kwargs)
            self.assertEqual(generate.call_args_list[1].kwargs["reference_image"], b"synthetic-test-image")
            visuals = result["draft"]["visuals"]
            self.assertEqual(visuals["product"]["product_specification_sha256"],
                             visuals["outfit"]["product_specification_sha256"])
            self.assertEqual(visuals["outfit"]["reference_image_sha256"], visuals["product"]["artifact"]["sha256"])
            self.assertEqual(result["generation_metadata"]["image_call_policy"], SEQUENTIAL_IMAGE_POLICY)

    def test_outfit_is_an_edit_of_the_stored_product_image_and_never_overlaps_it(self):
        product_png, outfit_png = b"product-image-bytes", b"outfit-image-bytes"
        state = {"active": 0, "maximum": 0, "calls": []}

        class FakeResponse:
            def __init__(self, image):
                self.image = image

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                state["active"] -= 1
                return False

            def read(self):
                return json.dumps({"data": [{"b64_json": base64.b64encode(self.image).decode("ascii")}]}).encode()

        def open_request(http_request, timeout):
            state["active"] += 1
            state["maximum"] = max(state["maximum"], state["active"])
            state["calls"].append((http_request.full_url, json.loads(http_request.data), timeout))
            return FakeResponse(product_png if http_request.full_url.endswith("/generations") else outfit_png)

        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "NOVELTY_DRAFT_ARTIFACT_DIR": directory, "NOVELTY_DRAFT_IMAGE_PROVIDER": "openai",
            "NOVELTY_TEXT_GENERATION_ENABLED": "false",
        }), patch("fashion_planner_novelty.server.app.load_settings", return_value=SimpleNamespace(image_generation_api_key="test-key")), \
             patch("urllib.request.urlopen", side_effect=open_request):
            response = _build_handoff_run(request())

        self.assertEqual([url for url, _body, _timeout in state["calls"]], [
            "https://api.openai.com/v1/images/generations", "https://api.openai.com/v1/images/edits",
        ])
        self.assertEqual(state["maximum"], 1)  # the edit starts only after the product call has returned
        generation, edit = state["calls"][0][1], state["calls"][1][1]
        self.assertEqual(edit["images"], [{"image_url": "data:image/png;base64," + base64.b64encode(product_png).decode("ascii")}])
        self.assertEqual((edit["model"], edit["n"]), (generation["model"], 1))
        self.assertNotIn("input_fidelity", edit)
        specification = json.dumps({"category": "Outerwear", "season": "spring/summer 2027", **FIXTURE_PROPOSALS},
                                   sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        self.assertIn(specification, generation["prompt"])
        self.assertIn(specification, edit["prompt"])
        self.assertIn("Input image 1", edit["prompt"])
        visuals = response["result"]["draft"]["visuals"]
        self.assertEqual(visuals["product"]["artifact"]["sha256"], hashlib.sha256(product_png).hexdigest())
        self.assertEqual(visuals["outfit"]["artifact"]["sha256"], hashlib.sha256(outfit_png).hexdigest())
        self.assertEqual(visuals["outfit"]["reference_image_sha256"], visuals["product"]["artifact"]["sha256"])
        self.assertIsNone(visuals["outfit"]["companion"])  # the fixture has no stock slot for its trend
        self.assertEqual({visual["prompt_version"] for visual in visuals.values()}, {"novelty-draft-visuals"})
        self.assertEqual(visuals["product"]["product_specification_sha256"], visuals["outfit"]["product_specification_sha256"])
        metadata = response["result"]["generation_metadata"]
        self.assertEqual(metadata["image_call_policy"], SEQUENTIAL_IMAGE_POLICY)
        timings = metadata["timings_ms"]
        self.assertGreaterEqual(timings["image_generation_wall"] + 2,
                                timings["product_image_generation"] + timings["outfit_image_generation"])

    def test_live_draft_details_reach_both_image_prompts(self):
        class DetailedDraftGenerator:
            generation_metadata = {"engine": "rule_based", "status": "generated", "prompt_version": None, "model": None}

            def generate(self, context):
                draft, issues = RuleBasedConceptGenerator().generate(context)
                details = (ProposedAttribute("detail", "프린지", "evidence_observation"),
                           ProposedAttribute("pattern", "체크", "proposal"),
                           ProposedAttribute("detail", "미확인 장식", "to_validate"))
                return replace(draft, product_profile=replace(draft.product_profile, details=details)), issues

        prompts, references = [], []

        def capture_generation(image_request):
            prompts.append(image_request.prompt)
            return SimpleNamespace(image_bytes=b"product-image")

        def capture_edit(image_request, reference_image, **_kwargs):
            prompts.append(image_request.prompt)
            references.append(reference_image)
            return SimpleNamespace(image_bytes=b"outfit-image")

        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "NOVELTY_DRAFT_ARTIFACT_DIR": directory, "NOVELTY_DRAFT_IMAGE_PROVIDER": "openai",
        }), patch("fashion_planner_novelty.server.app.load_settings", return_value=SimpleNamespace(image_generation_api_key="test-key")), \
             patch("fashion_planner_novelty.server.app._build_concept_generator", return_value=DetailedDraftGenerator()), \
             patch.object(OpenAIImageProvider, "generate", side_effect=capture_generation), \
             patch.object(OpenAIImageEditProvider, "edit", side_effect=capture_edit):
            response = _build_handoff_run(request())

        expected = {"category": "Outerwear", "details": ["프린지", "체크"], "season": "spring/summer 2027", **FIXTURE_PROPOSALS}
        specification = json.dumps(expected, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        self.assertEqual(len(prompts), 2)
        self.assertTrue(all(specification in prompt for prompt in prompts))
        self.assertTrue(all("미확인 장식" not in prompt for prompt in prompts))
        self.assertEqual(references, [b"product-image"])
        self.assertEqual(response["result"]["generation_metadata"]["image_specification_sha256"],
                         hashlib.sha256(json.dumps(expected, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                                                   allow_nan=False).encode("utf-8")).hexdigest())

    def test_partial_status_identifies_image_error_without_exposing_exception_text(self):
        def fail_product(kind, profile, request_id, reference_image=None):
            if kind == "product":
                raise ImageProviderError("IMAGE_API_HTTP_429")
            return b"mock-outfit"

        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "NOVELTY_DRAFT_ARTIFACT_DIR": directory, "NOVELTY_DRAFT_IMAGE_PROVIDER": "openai",
        }), patch("fashion_planner_novelty.server.app.load_settings", return_value=SimpleNamespace(image_generation_api_key="test-key")), \
             patch.object(OpenAIDraftImageProvider, "generate", side_effect=fail_product) as generate:
            response = _build_handoff_run(request())
            replay = _build_handoff_run(request())
        self.assertEqual(response, replay)
        self.assertEqual(response["status"], "partial")
        visuals = response["result"]["draft"]["visuals"]
        self.assertEqual(visuals["product"]["error_code"], "IMAGE_API_HTTP_429")
        # Without the product image the outfit is not generated from text alone: no call, no mismatched garment.
        self.assertEqual((visuals["outfit"]["status"], visuals["outfit"]["provider_calls"], visuals["outfit"]["error_code"]),
                         ("skipped", 0, "OUTFIT_REFERENCE_UNAVAILABLE"))
        codes = {item["code"] for item in response["result"]["validation_issues"]}
        self.assertTrue({"IMAGE_API_HTTP_429", "OUTFIT_REFERENCE_UNAVAILABLE"} <= codes)
        self.assertEqual(generate.call_count, 1)
        self.assertNotIn("authorization", json.dumps(response).lower())

    def test_uncertain_prior_image_run_is_not_repeated(self):
        value = request()
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "NOVELTY_DRAFT_ARTIFACT_DIR": directory, "NOVELTY_DRAFT_IMAGE_PROVIDER": "openai",
        }), patch("fashion_planner_novelty.server.app.load_settings", return_value=SimpleNamespace(image_generation_api_key="test-key")), \
             patch.object(OpenAIDraftImageProvider, "generate") as generate:
            store = DraftArtifactStore(directory)
            store.claim_image_run(value["request_id"], __import__("fashion_planner_novelty.server.app", fromlist=["_canonical_sha"])._canonical_sha(value))
            with self.assertRaises(ImageRunAlreadyClaimed):
                _build_handoff_run(value)
        self.assertFalse(generate.called)

    def test_unresolved_category_does_not_trigger_paid_image_generation(self):
        value = request()
        value["input"]["planning_request"].pop("category")
        value["input"]["planning_request"].pop("season")
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "NOVELTY_DRAFT_ARTIFACT_DIR": directory, "NOVELTY_DRAFT_IMAGE_PROVIDER": "openai",
        }), patch("fashion_planner_novelty.server.app.load_settings", return_value=SimpleNamespace(image_generation_api_key="test-key")), \
             patch.object(OpenAIDraftImageProvider, "generate") as generate:
            response = _build_handoff_run(value)
        self.assertFalse(generate.called)
        self.assertTrue(all(item["status"] == "skipped" and item["provider_calls"] == 0
                            for item in response["result"]["draft"]["visuals"].values()))

    def test_non_openai_image_provider_is_reported_as_unsupported(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "NOVELTY_DRAFT_ARTIFACT_DIR": directory, "NOVELTY_DRAFT_IMAGE_PROVIDER": "fixture",
        }), patch.object(OpenAIDraftImageProvider, "generate") as generate:
            response = _build_handoff_run(request())
        self.assertFalse(generate.called)
        self.assertTrue(all(item["status"] == "failed" and item["error_code"] == "IMAGE_PROVIDER_UNSUPPORTED"
                            for item in response["result"]["draft"]["visuals"].values()))

    def test_http_runs_route_and_retired_drafts_route(self):
        value = request()
        with tempfile.TemporaryDirectory() as directory:
            env = {"NOVELTY_HTTP_MODE": "private", "FASHION_PLANNER_SERVICE_TOKEN": "local-test",
                   "NOVELTY_DRAFT_ARTIFACT_DIR": directory, "NOVELTY_DRAFT_IMAGE_PROVIDER": ""}
            status, response = invoke(NoveltyRequestHandler, "/v1/agents/novelty/runs", value, env=env)
            self.assertEqual(status, 200)
            self.assertEqual(response["request_id"], value["request_id"])
            status, response = invoke(NoveltyRequestHandler, "/v1/agents/novelty/drafts", value, env=env)
        self.assertEqual(status, 404)
        self.assertEqual(response["error"]["code"], "NOT_FOUND")

    def test_request_id_contract_and_input_validation(self):
        bad = request()
        bad["input"]["planning_request"]["request_id"] = "different"
        with self.assertRaises(ValueError):
            _build_handoff_run(bad)
        bad = request()
        bad["input"]["extra"] = {}
        with self.assertRaises(ValueError):
            _build_handoff_run(bad)
        bad = request()
        bad["contract_version"] = "trend-handoff"
        with self.assertRaises(ValueError):
            _build_handoff_run(bad)

    def test_replay_is_stable_and_prevents_reusing_request_id_with_new_payload(self):
        value = request()
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "NOVELTY_DRAFT_ARTIFACT_DIR": directory, "NOVELTY_DRAFT_IMAGE_PROVIDER": "",
        }):
            first = _build_handoff_run(value)
            self.assertEqual(first, _build_handoff_run(copy.deepcopy(value)))
            changed = copy.deepcopy(value)
            changed["input"]["planning_request"]["query"] += " changed"
            with self.assertRaises(ValueError):
                _build_handoff_run(changed)

    def test_http_returns_conflict_for_reused_request_id_with_changed_payload(self):
        value = request()
        changed = copy.deepcopy(value)
        changed["input"]["planning_request"]["query"] += " changed"
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "NOVELTY_DRAFT_ARTIFACT_DIR": directory, "NOVELTY_DRAFT_IMAGE_PROVIDER": "",
        }):
            first_status, _ = invoke(
                NoveltyRequestHandler, "/v1/agents/novelty/runs", value,
                env={"NOVELTY_HTTP_MODE": "local"},
            )
            second_status, error = invoke(
                NoveltyRequestHandler, "/v1/agents/novelty/runs", changed,
                env={"NOVELTY_HTTP_MODE": "local"},
            )
        self.assertEqual(first_status, 200)
        self.assertEqual(second_status, 409)
        self.assertEqual(error["error"]["code"], "REQUEST_ID_REUSED")

    def test_concurrent_identical_no_image_requests_converge_on_saved_response(self):
        value = request()
        import fashion_planner_novelty.server.app as server_module
        original = server_module._analyze_planning_inputs
        both_started = threading.Barrier(2)

        def synchronized_analysis(*args, **kwargs):
            both_started.wait(timeout=2)
            return original(*args, **kwargs)

        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "NOVELTY_DRAFT_ARTIFACT_DIR": directory, "NOVELTY_DRAFT_IMAGE_PROVIDER": "",
        }), patch.object(server_module, "_analyze_planning_inputs", side_effect=synchronized_analysis):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(_build_handoff_run, (value, copy.deepcopy(value))))
        self.assertEqual(results[0], results[1])


if __name__ == "__main__":
    unittest.main()
