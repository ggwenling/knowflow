"""Offline client regression only. Passing these tests is not live model evidence."""

import io
import json
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib import error

sys.path.insert(0, str(Path(__file__).resolve().parent))
import model_smoke as smoke


class SmokeTests(unittest.TestCase):
    def setUp(self):
        self.env = {
            "KNOWFLOW_MODEL_BASE_URL": "https://example.invalid/v1",
            "KNOWFLOW_EMBEDDING_MODEL": "example-embedding-v1",
            "KNOWFLOW_LLM_MODEL": "example-chat-v1",
            "KNOWFLOW_EMBEDDING_DIMENSIONS": "2",
            "OPENAI_API_KEY": "secret-must-never-appear",
        }

    def test_no_configuration_never_opens_network(self):
        with patch.object(smoke.request, "build_opener") as build:
            report, code = smoke.run({}, 1)
        build.assert_not_called()
        self.assertEqual((report["status"], code), ("WAITING_INPUT", 2))
        self.assertFalse(report["network_attempted"])

    def test_rejects_unsafe_base_urls_before_network(self):
        for url in ("http://example.invalid/v1", "https://user:pass@example.invalid/v1",
                    "https://example.invalid/v1?key=secret", "https://example.invalid/v1#secret",
                    "https://example.invalid:bad/v1"):
            with self.subTest(url=url), patch.object(smoke.request, "build_opener") as build:
                report, code = smoke.run({**self.env, "KNOWFLOW_MODEL_BASE_URL": url}, 1)
                self.assertEqual(code, 1)
                self.assertEqual(report["status"], "FAILED")
                build.assert_not_called()

    def test_key_environment_selector(self):
        env = {**self.env, "KNOWFLOW_MODEL_KEY_ENV": "PROVIDER_API_KEY", "PROVIDER_API_KEY": "another-secret"}
        config, missing = smoke.read_config(env)
        self.assertFalse(missing)
        self.assertEqual(config["key"], "another-secret")

    def test_dimension_and_numeric_integrity(self):
        for vector, dimension in (([1], 2), ([0, 0], 2), ([math.nan, 1], 2),
                                  ([True, 1], 2), ([math.inf, 1], 2)):
            with self.subTest(vector=vector), self.assertRaises(smoke.SmokeFailure):
                smoke.validate_embeddings({"data": [{"index": 0, "embedding": vector}]}, 1, dimension)
        with self.assertRaises(smoke.SmokeFailure):
            smoke.validate_embeddings({"data": [{"index": 0, "embedding": [1, 2]}] * 2}, 2, 2)

    def test_incomplete_or_unsupported_answer_is_rejected(self):
        fixture = json.loads(smoke.FIXTURE.read_text())
        for answer, finish in (("", "stop"), ("限制是 16 MiB。", "stop"),
                               ("The limit is 8 MiB.", "stop"), ("限制是 8 MiB。", "length")):
            with self.subTest(answer=answer), self.assertRaises(smoke.SmokeFailure):
                smoke.validate_answer({"choices": [{"message": {"content": answer}, "finish_reason": finish}]}, fixture)

    def test_http_failures_do_not_echo_secrets_or_response_bodies(self):
        config, _ = smoke.read_config(self.env)
        for status, expected in ((401, "AUTH_REJECTED"), (403, "AUTH_REJECTED"),
                                 (429, "RATE_LIMITED"), (500, "HTTP_FAILURE")):
            with self.subTest(status=status):
                failure = error.HTTPError(config["base_url"], status, config["key"], {}, io.BytesIO(config["key"].encode()))
                with patch.object(smoke.request.OpenerDirector, "open", side_effect=failure):
                    report, code = smoke.run(self.env, 1)
                serialized = json.dumps(report)
                self.assertNotIn(config["key"], serialized)
                self.assertNotIn(config["base_url"], serialized)
                self.assertEqual(report["checks"]["embedding"]["error"], expected)
                self.assertEqual(code, 1)
                self.assertNotIn("chat", report["checks"])

    def test_timeout_is_reported_without_second_call(self):
        with patch.object(smoke.request.OpenerDirector, "open", side_effect=TimeoutError("secret")) as opened:
            report, code = smoke.run(self.env, 1)
        self.assertEqual(opened.call_count, 1)
        self.assertEqual(code, 1)
        self.assertEqual(report["checks"]["embedding"]["error"], "TIMEOUT")
        self.assertNotIn("secret", json.dumps(report))

    def test_redirect_is_rejected(self):
        with self.assertRaisesRegex(smoke.SmokeFailure, "REDIRECT_REJECTED"):
            smoke.NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.invalid")

    def test_invalid_and_oversized_payloads_are_bounded(self):
        for raw, expected in ((b"not json", "INVALID_JSON_RESPONSE"),
                              (b"[]", "INVALID_RESPONSE_SHAPE"),
                              (b"x" * (smoke.MAX_RESPONSE_BYTES + 1), "RESPONSE_TOO_LARGE")):
            with self.subTest(expected=expected):
                with patch.object(smoke.request.OpenerDirector, "open", return_value=io.BytesIO(raw)):
                    report, code = smoke.run(self.env, 1)
                self.assertEqual((report["error"], code), (expected, 1))

    def test_success_path_redacts_provider_text_and_vectors(self):
        embedding = {"data": [{"index": 0, "embedding": [0.5, 0.7]},
                               {"index": 1, "embedding": [0.1, 0.3]}],
                     "usage": {"total_tokens": 20, "private": "secret"}}
        chat = {"choices": [{"message": {"content": "限制是 8 MiB。"}, "finish_reason": "stop"}]}
        responses = [io.BytesIO(json.dumps(value).encode()) for value in (embedding, chat)]
        with patch.object(smoke.request.OpenerDirector, "open", side_effect=responses) as opened:
            report, code = smoke.run(self.env, 1)
        self.assertEqual((report["status"], code), ("LIVE_SMOKE_PASSED", 0))
        self.assertEqual(opened.call_count, 2)
        serialized = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("限制是 8 MiB。", serialized)
        self.assertNotIn("secret", serialized)
        self.assertNotIn("[0.5, 0.7]", serialized)
        self.assertIsNone(report["cost"]["amount"])


if __name__ == "__main__":
    unittest.main()
