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
        self.assertEqual(config["embedding"]["key"], "another-secret")
        self.assertEqual(config["llm"]["key"], "another-secret")

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
        endpoint = config["embedding"]
        for status, expected in ((401, "AUTH_REJECTED"), (403, "AUTH_REJECTED"),
                                 (429, "RATE_LIMITED"), (500, "HTTP_FAILURE")):
            with self.subTest(status=status):
                failure = error.HTTPError(endpoint["base_url"], status, endpoint["key"], {}, io.BytesIO(endpoint["key"].encode()))
                with patch.object(smoke.request.OpenerDirector, "open", side_effect=failure):
                    report, code = smoke.run(self.env, 1)
                serialized = json.dumps(report)
                self.assertNotIn(endpoint["key"], serialized)
                self.assertNotIn(endpoint["base_url"], serialized)
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

    def test_split_providers_use_separate_urls_and_credentials(self):
        env = {**self.env,
               "KNOWFLOW_EMBEDDING_BASE_URL": "https://embedding.example.invalid/v1/",
               "KNOWFLOW_EMBEDDING_KEY_ENV": "EMBEDDING_API_KEY",
               "EMBEDDING_API_KEY": "embedding-only-secret",
               "KNOWFLOW_LLM_BASE_URL": "https://chat.example.invalid/",
               "KNOWFLOW_LLM_KEY_ENV": "CHAT_API_KEY",
               "CHAT_API_KEY": "chat-only-secret",
               "KNOWFLOW_LLM_THINKING": "disabled"}
        embedding = {"data": [{"index": i, "embedding": [1, 2]} for i in range(2)]}
        chat = {"choices": [{"message": {"content": "限制是 8 MiB。"}, "finish_reason": "stop"}]}
        responses = [io.BytesIO(json.dumps(value).encode()) for value in (embedding, chat)]
        with patch.object(smoke.request.OpenerDirector, "open", side_effect=responses) as opened:
            report, code = smoke.run(env, 1)
        self.assertEqual(code, 0)
        first, second = [call.args[0] for call in opened.call_args_list]
        self.assertEqual(first.full_url, "https://embedding.example.invalid/v1/embeddings")
        self.assertEqual(first.get_header("Authorization"), "Bearer embedding-only-secret")
        self.assertEqual(second.full_url, "https://chat.example.invalid/chat/completions")
        self.assertEqual(second.get_header("Authorization"), "Bearer chat-only-secret")
        self.assertNotIn("embedding-only-secret", second.data.decode())
        self.assertEqual(json.loads(second.data)["thinking"], {"type": "disabled"})
        self.assertNotIn("thinking", json.loads(first.data))
        self.assertNotIn("secret", json.dumps(report))

    def test_split_endpoint_never_inherits_shared_key_without_selector(self):
        env = {**self.env, "KNOWFLOW_LLM_BASE_URL": "https://other.example.invalid"}
        with patch.object(smoke.request, "build_opener") as build:
            report, code = smoke.run(env, 1)
        build.assert_not_called()
        self.assertEqual(code, 2)
        self.assertIn("KNOWFLOW_LLM_KEY_ENV", report["missing_configuration"])

    def test_missing_split_secret_never_falls_back_to_shared_key(self):
        env = {**self.env, "KNOWFLOW_LLM_KEY_ENV": "MISSING_CHAT_KEY"}
        with patch.object(smoke.request, "build_opener") as build:
            report, code = smoke.run(env, 1)
        build.assert_not_called()
        self.assertEqual(code, 2)
        self.assertIn("MISSING_CHAT_KEY", report["missing_configuration"])

    def test_reranker_is_rejected_before_any_call(self):
        for model in ("BAAI/bge-reranker-v2-m3", "Pro/BAAI/bge-reranker-v2-m3"):
            with self.subTest(model=model), patch.object(smoke.request, "build_opener") as build:
                report, code = smoke.run({**self.env, "KNOWFLOW_EMBEDDING_MODEL": model}, 1)
                build.assert_not_called()
                self.assertEqual((report["error"], code), ("RERANKER_IS_NOT_EMBEDDING", 1))
                self.assertFalse(report["network_attempted"])

    def test_invalid_thinking_mode_is_rejected(self):
        with patch.object(smoke.request, "build_opener") as build:
            report, code = smoke.run({**self.env, "KNOWFLOW_LLM_THINKING": "arbitrary"}, 1)
        build.assert_not_called()
        self.assertEqual((report["error"], code), ("INVALID_THINKING_MODE", 1))


if __name__ == "__main__":
    unittest.main()
