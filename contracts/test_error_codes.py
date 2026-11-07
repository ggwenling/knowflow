"""Contract guard: every public error code emitted by Java or Python is enumerated.

This is the invariant that was missed when KNOWLEDGE_BASE_NOT_READY was returned
by the Java API but absent from the shared schema.
"""

import json
import unittest
from pathlib import Path

from contracts import error_code_inventory as inventory


class ErrorCodeInventoryTest(unittest.TestCase):
    def setUp(self):
        self.schema = json.loads(
            Path(inventory.SCHEMA_PATH).read_text(encoding="utf-8")
        )
        self.error_enum, self.stream_enum = inventory.schema_error_codes(self.schema)

    def test_inventory_parsers_find_codes(self):
        self.assertIn("KNOWLEDGE_BASE_NOT_READY", inventory.java_error_codes())
        self.assertIn("AI_PROCESSING_FAILED", inventory.python_error_codes())

    def test_every_java_code_is_in_both_enums(self):
        java = inventory.java_error_codes()
        self.assertEqual(set(), java - self.error_enum)
        self.assertEqual(set(), java - self.stream_enum)

    def test_every_python_code_is_in_both_enums(self):
        python = inventory.python_error_codes()
        self.assertEqual(set(), python - self.error_enum)
        self.assertEqual(set(), python - self.stream_enum)

    def test_knowledge_base_not_ready_is_frozen(self):
        self.assertIn("KNOWLEDGE_BASE_NOT_READY", self.error_enum)
        self.assertIn("KNOWLEDGE_BASE_NOT_READY", self.stream_enum)

    def test_error_and_stream_enums_do_not_drift(self):
        self.assertEqual(self.error_enum, self.stream_enum)

    def test_check_reports_missing_code(self):
        schema = json.loads(json.dumps(self.schema))
        schema["$defs"]["Error"]["properties"]["code"]["enum"].remove(
            "KNOWLEDGE_BASE_NOT_READY"
        )
        problems = inventory.check(schema)
        self.assertTrue(
            any("KNOWLEDGE_BASE_NOT_READY" in problem for problem in problems),
            problems,
        )


if __name__ == "__main__":
    unittest.main()
