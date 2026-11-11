import copy
import json
import unittest
from pathlib import Path

from vogue_npp.adapters.handoff import AdapterCompatibilityError, normalize_handoff_inputs


FIXTURE = Path(__file__).parent / "fixtures/http-handoff-v0.2/success.json"


class HandoffAdapterRegistryTests(unittest.TestCase):
    def setUp(self):
        self.envelope = json.loads(FIXTURE.read_text())

    def test_trend_version_mapping_preserves_source_and_records_provenance(self):
        original = copy.deepcopy(self.envelope["input"])
        adapted = normalize_handoff_inputs(self.envelope["request_id"], self.envelope["input"])
        self.assertEqual(self.envelope["input"], original)
        self.assertEqual(adapted.source_inputs["trend_result"]["schema_version"], "1.1")
        self.assertEqual(adapted.normalized_inputs["trend_result"]["schema_version"], "1.0")
        trace = adapted.provenance["input_schemas"]["trend_result"]
        self.assertEqual(trace["source_schema_version"], "1.1")
        self.assertEqual(trace["normalized_schema_version"], "1.0")
        self.assertTrue(trace["transformed"])
        self.assertEqual(len(trace["source_payload_sha256"]), 64)

    def test_unsupported_version_and_unrecognized_input_field_are_explicit_errors(self):
        bad = copy.deepcopy(self.envelope["input"])
        bad["trend_result"]["schema_version"] = "1.2"
        with self.assertRaises(AdapterCompatibilityError) as caught:
            normalize_handoff_inputs(self.envelope["request_id"], bad)
        self.assertEqual(caught.exception.code, "UNSUPPORTED_PRODUCER_SCHEMA")

        bad = {**self.envelope["input"], "mystery_payload": {}}
        with self.assertRaises(AdapterCompatibilityError) as caught:
            normalize_handoff_inputs(self.envelope["request_id"], bad)
        self.assertEqual(caught.exception.code, "INVALID_INPUT")

    def test_project07_null_is_rejected_as_missing_required_result(self):
        inputs = copy.deepcopy(self.envelope["input"])
        inputs["sales_market_result"] = None
        with self.assertRaises(AdapterCompatibilityError) as caught:
            normalize_handoff_inputs(self.envelope["request_id"], inputs)
        self.assertEqual(caught.exception.code, "INVALID_PRODUCER_PAYLOAD")


if __name__ == "__main__":
    unittest.main()
