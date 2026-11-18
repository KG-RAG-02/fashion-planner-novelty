"""HTTP 관문: 인증, 미디어 타입, 본문 크기, JSON 오류는 기획 작업을 시작하기 전에 응답한다."""
import io
import json
import os
import tempfile
import unittest
from email.message import Message
from types import SimpleNamespace
from unittest.mock import patch

from fashion_planner_novelty.server.app import MAX_RUN_BODY_BYTES, NoveltyRequestHandler

RUNS_PATH = "/v1/agents/novelty/runs"
TOKEN = "gate-test-token"


class _UnreadBody(io.BytesIO):
    """핸들러가 읽으면 테스트를 실패시키는 요청 본문."""

    def read(self, *args, **kwargs):
        raise AssertionError("헤더만으로 거절해야 할 요청의 본문을 읽었다")


def call(*, body=b"{}", content_type="application/json", content_length=None, token=TOKEN, mode="private",
         rfile=None):
    handler = object.__new__(NoveltyRequestHandler)
    handler.path = RUNS_PATH
    handler.headers = Message()
    handler.headers["Content-Type"] = content_type
    handler.headers["Content-Length"] = str(len(body) if content_length is None else content_length)
    if token is not None:
        handler.headers["Authorization"] = f"Bearer {token}"
    handler.rfile = rfile if rfile is not None else io.BytesIO(body)
    handler.wfile = SimpleNamespace(body=b"", status=None)
    handler.wfile.write = lambda data: setattr(handler.wfile, "body", handler.wfile.body + data)
    handler.client_address = ("127.0.0.1", 1234)
    handler.send_response = lambda status: setattr(handler.wfile, "status", status)
    handler.send_header = lambda *_: None
    handler.end_headers = lambda: None
    env = {"NOVELTY_HTTP_MODE": mode, "FASHION_PLANNER_SERVICE_TOKEN": TOKEN,
           "NOVELTY_DRAFT_ARTIFACT_DIR": tempfile.mkdtemp(), "NOVELTY_DRAFT_IMAGE_PROVIDER": "",
           "NOVELTY_TEXT_GENERATION_ENABLED": "false"}
    with patch.dict(os.environ, env, clear=False), \
         patch("fashion_planner_novelty.server.app._build_handoff_run",
               side_effect=AssertionError("거절한 요청으로 기획을 시작하면 안 된다")):
        handler.do_POST()
    return handler.wfile.status, json.loads(handler.wfile.body)["error"]["code"]


class HttpGateTests(unittest.TestCase):
    def test_body_over_the_limit_is_rejected_from_the_header_without_reading_it(self):
        status, code = call(content_length=MAX_RUN_BODY_BYTES + 1, rfile=_UnreadBody())
        self.assertEqual((status, code), (413, "PAYLOAD_TOO_LARGE"))

    def test_the_limit_is_one_million_bytes(self):
        self.assertEqual(MAX_RUN_BODY_BYTES, 1_000_000)

    def test_missing_or_wrong_token_is_401_in_private_and_service_modes(self):
        for mode in ("private", "service"):
            for token in (None, "wrong-token"):
                with self.subTest(mode=mode, token=token):
                    self.assertEqual(call(token=token, mode=mode), (401, "UNAUTHORIZED"))

    def test_non_json_media_type_is_415(self):
        self.assertEqual(call(content_type="text/plain"), (415, "UNSUPPORTED_MEDIA_TYPE"))

    def test_malformed_json_is_400(self):
        self.assertEqual(call(body=b"{not json"), (400, "INVALID_JSON"))

    def test_non_numeric_content_length_is_400(self):
        status, code = call(content_length="abc", rfile=_UnreadBody())
        self.assertEqual((status, code), (400, "INVALID_CONTENT_LENGTH"))


if __name__ == "__main__":
    unittest.main()
