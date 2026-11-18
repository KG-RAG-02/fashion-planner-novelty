"""Regression checks for retired HTTP paths and the active P08 workflow route."""
import io
import json
import os
import unittest
from email.message import Message
from types import SimpleNamespace
from unittest.mock import patch

from fashion_planner_novelty.prototype.server import PrototypeHandler


class LegacyRouteRemovalTests(unittest.TestCase):
    def invoke_post(self, path, payload=None):
        body = json.dumps(payload or {}).encode()
        handler = object.__new__(PrototypeHandler)
        handler.path = path
        handler.headers = Message()
        handler.headers["Content-Type"] = "application/json"
        handler.headers["Content-Length"] = str(len(body))
        handler.rfile = io.BytesIO(body)
        handler.wfile = SimpleNamespace(body=b"", status=None)
        handler.wfile.write = lambda content: setattr(handler.wfile, "body", handler.wfile.body + content)
        handler.client_address = ("127.0.0.1", 1234)
        handler.send_response = lambda status: setattr(handler.wfile, "status", status)
        handler.send_header = lambda *_: None
        handler.end_headers = lambda: None
        with patch.dict(os.environ, {"VOGUE_HTTP_MODE": "local"}):
            handler.do_POST()
        return handler.wfile.status, json.loads(handler.wfile.body)

    def test_drafts_and_removed_routes_are_not_registered(self):
        for path in (
            "/api/planning-draft",
            "/v1/agents/new-product-agent/sales-market-reviews",
        ):
            with self.subTest(path=path):
                status, response = self.invoke_post(path)
                self.assertEqual(status, 404)
                self.assertEqual(response["error"]["code"], "NOT_FOUND")
