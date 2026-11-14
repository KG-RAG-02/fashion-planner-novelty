"""P08 vogue-handoff/0.3 planning draft producer tests."""
import copy
import contextlib
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import os
import tempfile
import threading
import time
import unittest
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from vogue_npp.prototype.server import PrototypeHandler, _build_handoff_run, _image_profile_from_draft
from vogue_npp.workflows.draft_artifacts import DraftArtifactStore, ImageRunAlreadyClaimed, OpenAIDraftImageProvider
from vogue_npp.workflows.image_generation import ImageProviderError, OpenAIImageProvider

FIXTURE = Path(__file__).parent / "fixtures/workflow-inputs/success.json"


def request():
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    value["contract_version"] = "vogue-handoff/0.3"
    value["input"]["planning_request"].update(category="Outerwear", season="spring/summer 2027")
    return value


def invoke(handler_type, path, value, *, env):
    body = json.dumps(value).encode()
    handler = object.__new__(handler_type)
    handler.path = path
    handler.headers = Message()
    handler.headers["Content-Type"] = "application/json"
    handler.headers["Content-Length"] = str(len(body))
    if env.get("VOGUE_HTTP_MODE") in {"private", "service"}:
        handler.headers["Authorization"] = f"Bearer {env['VOGUE_AGENT_SERVICE_BEARER_TOKEN']}"
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

        def capture_image(image_request):
            prompts.append(image_request.prompt)
            return SimpleNamespace(image_bytes=f"mock-image-{len(prompts)}".encode())

        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "VOGUE_DRAFT_ARTIFACT_DIR": directory, "VOGUE_DRAFT_IMAGE_PROVIDER": "openai",
        }), patch("vogue_npp.prototype.server.load_settings",
                  return_value=SimpleNamespace(image_generation_api_key="test-key")), \
             patch.object(OpenAIImageProvider, "generate", side_effect=capture_image):
            response = _build_handoff_run(value)

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
            "VOGUE_DRAFT_ARTIFACT_DIR": directory, "VOGUE_DRAFT_IMAGE_PROVIDER": "openai",
        }), patch("vogue_npp.prototype.server.load_settings",
                  return_value=SimpleNamespace(image_generation_api_key="test-key")), \
             patch.object(OpenAIDraftImageProvider, "generate", return_value=b"mock-image"):
            response = _build_handoff_run(value)

        self.assertEqual(response["status"], "partial")
        codes = {issue["code"] for issue in response["result"]["validation_issues"]}
        self.assertIn("UPSTREAM_DATA_MISSING", codes)

    def test_safe_logs_correlate_cache_and_http_serialization_timings(self):
        value = request()
        logs = io.StringIO()
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "VOGUE_DRAFT_ARTIFACT_DIR": directory, "VOGUE_DRAFT_IMAGE_PROVIDER": "",
        }), contextlib.redirect_stderr(logs):
            status, response = invoke(PrototypeHandler, "/v1/agents/new-product-agent/runs", value, env={})
        events = [json.loads(line) for line in logs.getvalue().splitlines()]
        completion = next(event for event in events if event["event"] == "p06_draft_completed")
        http = next(event for event in events if event["event"] == "p06_http_response_serialized")
        self.assertEqual(status, 200)
        self.assertEqual(completion["request_id"], value["request_id"])
        self.assertIn("response_cache_persistence", completion["timings_ms"])
        self.assertIn("total_processing_including_cache", completion["timings_ms"])
        self.assertEqual(http["request_id"], value["request_id"])
        self.assertEqual(http["http_status"], 200)
        self.assertIsInstance(http["http_response_serialization_ms"], int)
        self.assertNotIn("mock-key", logs.getvalue())

    def test_p08_native_response_envelope_and_required_result_fields(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "VOGUE_DRAFT_ARTIFACT_DIR": directory, "VOGUE_DRAFT_IMAGE_PROVIDER": "",
        }):
            response = _build_handoff_run(request())
        self.assertEqual(set(response), {"contract_version", "request_id", "producer", "status", "result"})
        self.assertEqual(response["contract_version"], "vogue-handoff/0.3")
        self.assertEqual(response["producer"], {"agent_id": "new-product-agent", "schema_version": "1.0"})
        result = response["result"]
        self.assertEqual(result["schema_version"], "1.0")
        self.assertEqual(result["request_id"], response["request_id"])
        self.assertEqual(result["status"], response["status"])
        self.assertEqual(result["input_evidence"]["trend_result"]["source_schema_version"], "1.1")
        self.assertEqual(result["input_evidence"]["trend_result"]["payload"]["schema_version"], "1.1")
        self.assertEqual(result["compatibility"]["input_schemas"]["trend_result"]["internal_schema_version"], "1.0")
        self.assertIn("product_profile", result["draft"])
        self.assertEqual(result["draft"]["product_profile"]["category"]["value"], "Outerwear")
        self.assertEqual(result["draft"]["category"], result["draft"]["product_profile"]["category"]["value"])
        self.assertEqual(set(result["draft"]["visuals"]), {"product", "outfit"})
        self.assertIsNone(result["planning_board"])

    def test_real_provider_creates_request_owned_product_and_outfit_artifacts(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "VOGUE_DRAFT_ARTIFACT_DIR": directory, "VOGUE_DRAFT_IMAGE_PROVIDER": "openai",
        }), patch("vogue_npp.prototype.server.load_settings", return_value=SimpleNamespace(image_generation_api_key="test-key")), \
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
            visuals = result["draft"]["visuals"]
            self.assertEqual(visuals["product"]["product_specification_sha256"],
                             visuals["outfit"]["product_specification_sha256"])
            self.assertEqual(result["generation_metadata"]["image_call_policy"], "two concurrent calls; no automatic retry")

    def test_product_and_outfit_calls_run_concurrently_and_share_one_specification(self):
        state = {"active": 0, "maximum": 0, "prompts": []}
        lock = threading.Lock()
        both_started = threading.Event()

        def mock_generate(image_request):
            with lock:
                state["active"] += 1
                state["maximum"] = max(state["maximum"], state["active"])
                state["prompts"].append(image_request.prompt)
                if state["active"] == 2:
                    both_started.set()
            if not both_started.wait(1):
                raise AssertionError("both image requests should overlap")
            time.sleep(0.02)
            with lock:
                state["active"] -= 1
            return SimpleNamespace(image_bytes=b"mock-image")

        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "VOGUE_DRAFT_ARTIFACT_DIR": directory, "VOGUE_DRAFT_IMAGE_PROVIDER": "openai",
        }), patch("vogue_npp.prototype.server.load_settings", return_value=SimpleNamespace(image_generation_api_key="test-key")), \
             patch.object(OpenAIImageProvider, "generate", side_effect=mock_generate):
            response = _build_handoff_run(request())
        self.assertEqual(state["maximum"], 2)
        specification = json.dumps({"category": "Outerwear", "season": "spring/summer 2027"},
                                   sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        self.assertEqual(len(state["prompts"]), 2)
        self.assertTrue(all(specification in prompt for prompt in state["prompts"]))
        self.assertEqual(response["result"]["draft"]["visuals"]["product"]["product_specification_sha256"],
                         response["result"]["draft"]["visuals"]["outfit"]["product_specification_sha256"])
        self.assertGreaterEqual(response["result"]["generation_metadata"]["timings_ms"]["image_generation_wall"], 0)

    def test_partial_status_identifies_image_error_without_exposing_exception_text(self):
        def fail_product(kind, profile, request_id):
            if kind == "product":
                raise ImageProviderError("IMAGE_API_HTTP_429")
            return b"mock-outfit"

        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "VOGUE_DRAFT_ARTIFACT_DIR": directory, "VOGUE_DRAFT_IMAGE_PROVIDER": "openai",
        }), patch("vogue_npp.prototype.server.load_settings", return_value=SimpleNamespace(image_generation_api_key="test-key")), \
             patch.object(OpenAIDraftImageProvider, "generate", side_effect=fail_product) as generate:
            response = _build_handoff_run(request())
            replay = _build_handoff_run(request())
        self.assertEqual(response, replay)
        self.assertEqual(response["status"], "partial")
        self.assertEqual(response["result"]["draft"]["visuals"]["product"]["error_code"], "IMAGE_API_HTTP_429")
        self.assertTrue(any(item["code"] == "IMAGE_API_HTTP_429" for item in response["result"]["validation_issues"]))
        self.assertEqual(generate.call_count, 2)
        self.assertNotIn("authorization", json.dumps(response).lower())

    def test_uncertain_prior_image_run_is_not_repeated(self):
        value = request()
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "VOGUE_DRAFT_ARTIFACT_DIR": directory, "VOGUE_DRAFT_IMAGE_PROVIDER": "openai",
        }), patch("vogue_npp.prototype.server.load_settings", return_value=SimpleNamespace(image_generation_api_key="test-key")), \
             patch.object(OpenAIDraftImageProvider, "generate") as generate:
            store = DraftArtifactStore(directory)
            store.claim_image_run(value["request_id"], __import__("vogue_npp.prototype.server", fromlist=["_canonical_sha"])._canonical_sha(value))
            with self.assertRaises(ImageRunAlreadyClaimed):
                _build_handoff_run(value)
        self.assertFalse(generate.called)

    def test_unresolved_category_does_not_trigger_paid_image_generation(self):
        value = request()
        value["input"]["planning_request"].pop("category")
        value["input"]["planning_request"].pop("season")
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "VOGUE_DRAFT_ARTIFACT_DIR": directory, "VOGUE_DRAFT_IMAGE_PROVIDER": "openai",
        }), patch("vogue_npp.prototype.server.load_settings", return_value=SimpleNamespace(image_generation_api_key="test-key")), \
             patch.object(OpenAIDraftImageProvider, "generate") as generate:
            response = _build_handoff_run(value)
        self.assertFalse(generate.called)
        self.assertTrue(all(item["status"] == "skipped" and item["provider_calls"] == 0
                            for item in response["result"]["draft"]["visuals"].values()))

    def test_non_openai_image_provider_is_reported_as_unsupported(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "VOGUE_DRAFT_ARTIFACT_DIR": directory, "VOGUE_DRAFT_IMAGE_PROVIDER": "fixture",
        }), patch.object(OpenAIDraftImageProvider, "generate") as generate:
            response = _build_handoff_run(request())
        self.assertFalse(generate.called)
        self.assertTrue(all(item["status"] == "failed" and item["error_code"] == "IMAGE_PROVIDER_UNSUPPORTED"
                            for item in response["result"]["draft"]["visuals"].values()))

    def test_http_runs_route_and_retired_drafts_route(self):
        value = request()
        with tempfile.TemporaryDirectory() as directory:
            env = {"VOGUE_HTTP_MODE": "private", "VOGUE_AGENT_SERVICE_BEARER_TOKEN": "local-test",
                   "VOGUE_DRAFT_ARTIFACT_DIR": directory, "VOGUE_DRAFT_IMAGE_PROVIDER": ""}
            status, response = invoke(PrototypeHandler, "/v1/agents/new-product-agent/runs", value, env=env)
            self.assertEqual(status, 200)
            self.assertEqual(response["request_id"], value["request_id"])
            status, response = invoke(PrototypeHandler, "/v1/agents/new-product-agent/drafts", value, env=env)
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
        bad["contract_version"] = "vogue-workflow/0.1"
        with self.assertRaises(ValueError):
            _build_handoff_run(bad)

    def test_replay_is_stable_and_prevents_reusing_request_id_with_new_payload(self):
        value = request()
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "VOGUE_DRAFT_ARTIFACT_DIR": directory, "VOGUE_DRAFT_IMAGE_PROVIDER": "",
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
            "VOGUE_DRAFT_ARTIFACT_DIR": directory, "VOGUE_DRAFT_IMAGE_PROVIDER": "",
        }):
            first_status, _ = invoke(
                PrototypeHandler, "/v1/agents/new-product-agent/runs", value,
                env={"VOGUE_HTTP_MODE": "local"},
            )
            second_status, error = invoke(
                PrototypeHandler, "/v1/agents/new-product-agent/runs", changed,
                env={"VOGUE_HTTP_MODE": "local"},
            )
        self.assertEqual(first_status, 200)
        self.assertEqual(second_status, 409)
        self.assertEqual(error["error"]["code"], "REQUEST_ID_REUSED")

    def test_concurrent_identical_no_image_requests_converge_on_saved_response(self):
        value = request()
        import vogue_npp.prototype.server as server_module
        original = server_module._analyze_planning_inputs
        both_started = threading.Barrier(2)

        def synchronized_analysis(*args, **kwargs):
            both_started.wait(timeout=2)
            return original(*args, **kwargs)

        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "VOGUE_DRAFT_ARTIFACT_DIR": directory, "VOGUE_DRAFT_IMAGE_PROVIDER": "",
        }), patch.object(server_module, "_analyze_planning_inputs", side_effect=synchronized_analysis):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(_build_handoff_run, (value, copy.deepcopy(value))))
        self.assertEqual(results[0], results[1])


if __name__ == "__main__":
    unittest.main()
