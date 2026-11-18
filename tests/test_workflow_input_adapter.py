import copy
import json
import unittest
from pathlib import Path

from fashion_planner_novelty.adapters.draft_inputs import WorkflowInputError, normalize_workflow_inputs


FIXTURE = Path(__file__).parent / "fixtures/workflow-inputs/success.json"


class WorkflowInputRegistryTests(unittest.TestCase):
    def setUp(self):
        self.envelope = json.loads(FIXTURE.read_text())

    def test_inputs_keep_source_payloads_and_record_provenance(self):
        original = copy.deepcopy(self.envelope["input"])
        adapted = normalize_workflow_inputs(self.envelope["request_id"], self.envelope["input"])
        self.assertEqual(self.envelope["input"], original)
        self.assertEqual(adapted.source_inputs["trend_result"]["schema_version"], "1.0.0")
        self.assertEqual(adapted.normalized_inputs["trend_result"]["schema_version"], "1.0.0")
        trace = adapted.provenance["input_schemas"]["trend_result"]
        self.assertEqual(trace["source_schema_version"], "1.0.0")
        self.assertEqual(trace["normalized_schema_version"], "1.0.0")
        self.assertFalse(trace["transformed"])
        self.assertEqual(trace["adapter_version"], "novelty-input-normalizer")
        self.assertEqual(len(trace["source_payload_sha256"]), 64)

    def test_unsupported_version_and_unrecognized_input_field_are_explicit_errors(self):
        bad = copy.deepcopy(self.envelope["input"])
        bad["trend_result"]["schema_version"] = "1.2"
        with self.assertRaises(WorkflowInputError) as caught:
            normalize_workflow_inputs(self.envelope["request_id"], bad)
        self.assertEqual(caught.exception.code, "UNSUPPORTED_PRODUCER_SCHEMA")

        bad = {**self.envelope["input"], "mystery_payload": {}}
        with self.assertRaises(WorkflowInputError) as caught:
            normalize_workflow_inputs(self.envelope["request_id"], bad)
        self.assertEqual(caught.exception.code, "INVALID_INPUT")

    def test_rejects_undeclared_business_inputs(self):
        inputs = copy.deepcopy(self.envelope["input"])
        inputs["sales_market_result"] = {"request_id": self.envelope["request_id"]}
        with self.assertRaises(WorkflowInputError) as caught:
            normalize_workflow_inputs(self.envelope["request_id"], inputs)
        self.assertEqual(caught.exception.code, "INVALID_INPUT")


if __name__ == "__main__":
    unittest.main()
