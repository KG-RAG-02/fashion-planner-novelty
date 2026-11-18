import io
import json
import unittest
from unittest.mock import patch

from fashion_planner_novelty.sources.openai_text_provider import (
    OpenAIResponsesTextProvider,
    OpenAITextProviderError,
)


class _Response:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size=-1):
        return json.dumps(self.value).encode()


class OpenAITextProviderTests(unittest.TestCase):
    def test_posts_strict_schema_without_tools_or_response_storage(self):
        captured = {}
        result_json = '{"request_id":"safe-1"}'

        def open_request(request, timeout):
            captured["url"] = request.full_url
            captured["headers"] = dict(request.header_items())
            captured["body"] = json.loads(request.data)
            captured["timeout"] = timeout
            return _Response({
                "status": "completed",
                "output": [{"type": "message", "content": [{"type": "output_text", "text": result_json}]}],
            })

        provider = OpenAIResponsesTextProvider("test-key", model="gpt-6-astra", timeout_seconds=17)
        with patch("urllib.request.urlopen", side_effect=open_request):
            output = provider.generate_json(system_prompt="trusted system", user_prompt="bounded input")

        self.assertEqual(output, result_json)
        self.assertEqual(captured["url"], "https://api.openai.com/v1/responses")
        self.assertEqual(captured["timeout"], 17)
        self.assertEqual(captured["body"]["instructions"], "trusted system")
        self.assertEqual(captured["body"]["input"], "bounded input")
        self.assertFalse(captured["body"]["store"])
        self.assertEqual(captured["body"]["tools"], [])
        self.assertFalse(captured["body"]["parallel_tool_calls"])
        output_format = captured["body"]["text"]["format"]
        self.assertEqual(output_format["type"], "json_schema")
        self.assertTrue(output_format["strict"])
        self.assertFalse(output_format["schema"]["additionalProperties"])

    def test_rejects_incomplete_and_refusal_responses(self):
        provider = OpenAIResponsesTextProvider("test-key")
        for response in (
            {"status": "incomplete", "output": []},
            {"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "private"}]}]},
        ):
            with self.subTest(response=response), patch("urllib.request.urlopen", return_value=_Response(response)):
                with self.assertRaises(OpenAITextProviderError):
                    provider.generate_json(system_prompt="system", user_prompt="input")

    def test_provider_http_error_is_redacted(self):
        provider = OpenAIResponsesTextProvider("test-key")
        error = __import__("urllib.error", fromlist=["HTTPError"]).HTTPError(
            "https://api.openai.com/v1/responses", 401, "secret response body", {}, io.BytesIO(b"secret"),
        )
        with patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(OpenAITextProviderError) as caught:
                provider.generate_json(system_prompt="system", user_prompt="input")
        self.assertEqual(str(caught.exception), "TEXT_API_HTTP_401")
        self.assertNotIn("secret", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
