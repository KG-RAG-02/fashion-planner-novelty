import io
import json
import os
from pathlib import Path
import unittest
from email.message import Message
from unittest.mock import patch

from vogue_npp.prototype.server import PrototypeHandler, _build_handoff_result, _request_sales_market_review


FIXTURE_PATH = Path(__file__).parent / "fixtures/http-handoff-v0.3/success.json"


def fixture(trend_status=None):
    value = json.loads(FIXTURE_PATH.read_text())
    if trend_status is not None:
        value["input"]["trend_result"]["status"] = trend_status
    return value


class FakeConnection:
    def settimeout(self, value):
        self.timeout = value


class FakeWriter:
    def __init__(self):
        self.body = b""
        self.status = None

    def write(self, value):
        self.body += value


class HandoffHTTPTests(unittest.TestCase):
    def invoke(self, value=None, *, raw=None, content_type="application/json", path="/v1/agents/new-product-agent/runs",
               mode="local", token="synthetic-agent-token", content_length=None):
        handler = object.__new__(PrototypeHandler)
        handler.path = path
        body = raw if raw is not None else json.dumps(value).encode()
        handler.headers = Message()
        handler.headers["Content-Type"] = content_type
        handler.headers["Content-Length"] = str(len(body) if content_length is None else content_length)
        if token is not None:
            handler.headers["Authorization"] = f"Bearer {token}"
        handler.rfile = io.BytesIO(body)
        handler.wfile = FakeWriter()
        handler.connection = FakeConnection()
        handler.client_address = ("127.0.0.1", 4567)
        handler.send_response = lambda status: setattr(handler.wfile, "status", status)
        handler.send_header = lambda *_: None
        handler.end_headers = lambda: None
        env = {
            "VOGUE_HTTP_MODE": mode,
            "VOGUE_AGENT_SERVICE_BEARER_TOKEN": "synthetic-agent-token",
        }
        with patch.dict(os.environ, env):
            handler.do_POST()
        return handler.wfile.status, json.loads(handler.wfile.body)

    def test_valid_trend_11_normalizes_without_relabeling_source(self):
        value = fixture()
        result = _build_handoff_result(value["request_id"], value["input"])
        self.assertEqual(result["compatibility"]["adapter_version"], "project06-input-normalizer/1.3")
        self.assertEqual(result["compatibility"]["input_schemas"]["trend_result"]["source_schema_version"], "1.1")
        self.assertEqual(result["compatibility"]["input_schemas"]["trend_result"]["internal_schema_version"], "1.0")
        self.assertEqual(result["input_evidence"]["trend_result"]["payload"]["schema_version"], "1.1")

    def test_domain_statuses_return_http_200_and_match_result_status(self):
        for status in ("ok", "partial", "no_results", "error"):
            with self.subTest(status=status):
                value = fixture(trend_status=status)
                code, response = self.invoke(value)
                self.assertEqual(code, 200)
                self.assertEqual(response["contract_version"], "vogue-handoff/0.3")
                self.assertEqual(response["producer"], {"agent_id": "new-product-agent", "schema_version": "1.0"})
                self.assertEqual(response["status"], response["result"]["status"])
                self.assertEqual(response["request_id"], value["request_id"])

    def test_bad_json_media_type_request_id_and_schema_statuses(self):
        code, body = self.invoke(raw=b"{")
        self.assertEqual((code, body["error"]["code"]), (400, "INVALID_JSON"))
        code, body = self.invoke(fixture(), content_type="text/plain")
        self.assertEqual((code, body["error"]["code"]), (415, "UNSUPPORTED_MEDIA_TYPE"))
        value = fixture()
        value["input"]["trend_result"]["request_id"] = "other-id"
        code, body = self.invoke(value)
        self.assertEqual((code, body["error"]["code"]), (422, "REQUEST_ID_MISMATCH"))
        value = fixture()
        value["input"]["trend_result"]["schema_version"] = "1.0"
        code, body = self.invoke(value)
        self.assertEqual((code, body["error"]["code"]), (422, "UNSUPPORTED_PRODUCER_SCHEMA"))
        code, body = self.invoke(raw=b"{}", content_length=1_000_001)
        self.assertEqual((code, body["error"]["code"]), (413, "PAYLOAD_TOO_LARGE"))

    def test_sales_market_is_not_an_input_and_legacy_draft_needs_only_planning_sources(self):
        value = fixture()
        value["input"]["sales_market_result"] = {"unexpected": "ignored input is rejected"}
        code, response = self.invoke(value)
        self.assertEqual((code, response["error"]["code"]), (422, "INVALID_INPUT"))

        draft_payload = {"request_id": value["request_id"], **value["input"]}
        code, response = self.invoke(draft_payload, path="/api/planning-draft")
        self.assertEqual(code, 200)
        self.assertNotIn("sales_market_result", response["input_evidence"])

    def test_service_mode_requires_bearer_token(self):
        code, body = self.invoke(fixture(), mode="service", token=None)
        self.assertEqual((code, body["error"]["code"]), (401, "UNAUTHORIZED"))
        code, response = self.invoke(fixture(), mode="service", token="synthetic-agent-token")
        self.assertEqual(code, 200)
        self.assertEqual(response["producer"]["agent_id"], "new-product-agent")

    def test_local_handoff_requires_matching_shared_bearer_token(self):
        for token in (None, "wrong-token"):
            with self.subTest(token="missing" if token is None else "wrong"):
                code, body = self.invoke(fixture(), mode="local", token=token)
                self.assertEqual((code, body["error"]["code"]), (401, "UNAUTHORIZED"))

    def test_unknown_route_is_404(self):
        code, body = self.invoke({}, path="/v1/agents/other/runs")
        self.assertEqual(code, 404)
        self.assertEqual(body["error"], "Not found")

    def test_sales_market_review_proxy_forwards_versioned_draft_and_returns_opaque_response(self):
        response_body = {
            "contract_version": "vogue-sales-market-review/0.1-proposal",
            "request_id": "review-1",
            "producer": {"agent_id": "sales-market-agent", "schema_version": "sales-market-review/0.1-internal"},
            "status": "no_results",
            "result": {"schema_version": "sales-market-review/0.1-internal", "request_id": "review-1",
                       "producer_id": "sales-market-agent", "status": "no_results"},
        }
        request = {
            "contract_version": "vogue-sales-market-review/0.1-proposal",
            "request_id": "review-1",
            "input": {"request_id": "review-1", "planning_draft": {
                "schema_version": "1.0", "request_id": "review-1",
                "draft": {"category": "원피스", "season": "2027SS",
                          "attributes": [{"name": "material", "value": "cotton"}]},
            }},
        }

        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def read(self, _limit): return json.dumps(response_body).encode()

        with patch.dict(os.environ, {"VOGUE_SALES_MARKET_AGENT_URL": "http://127.0.0.1:8766"}), \
             patch("vogue_npp.prototype.server.urllib.request.urlopen", return_value=FakeResponse()) as open_request:
            result = _request_sales_market_review(request)
        self.assertEqual(result, response_body)
        sent = json.loads(open_request.call_args.args[0].data)
        self.assertEqual(sent["contract_version"], request["contract_version"])
        self.assertEqual(sent["request_id"], request["request_id"])
        self.assertEqual(sent["input"]["planning_draft"]["draft_id"], "review-1")
        self.assertEqual(sent["input"]["planning_draft"]["product"], {
            "category": "원피스", "season": "2027SS", "material": "cotton",
        })

    def test_sales_market_review_route_requires_auth_and_returns_review_envelope(self):
        request = {
            "contract_version": "vogue-sales-market-review/0.1-proposal",
            "request_id": "review-1",
            "input": {"request_id": "review-1", "planning_draft": {
                "schema_version": "1.0", "draft_id": "draft-1", "product": {"category": "원피스"},
            }},
        }
        forwarded = {"contract_version": request["contract_version"], "request_id": "review-1",
                     "producer": {"agent_id": "sales-market-agent", "schema_version": "sales-market-review/0.1-internal"},
                     "status": "no_results", "result": {"schema_version": "sales-market-review/0.1-internal",
                     "request_id": "review-1", "producer_id": "sales-market-agent", "status": "no_results"}}
        path = "/v1/agents/new-product-agent/sales-market-reviews"
        code, body = self.invoke(request, path=path, token=None)
        self.assertEqual((code, body["error"]["code"]), (401, "UNAUTHORIZED"))
        with patch("vogue_npp.prototype.server._request_sales_market_review", return_value=forwarded):
            code, body = self.invoke(request, path=path)
        self.assertEqual(code, 200)
        self.assertEqual(body, forwarded)


if __name__ == "__main__":
    unittest.main()
