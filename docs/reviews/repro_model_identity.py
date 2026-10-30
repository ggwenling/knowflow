"""Offline reproduction for Q-003-01; never calls a model provider.

Run: python docs/reviews/repro_model_identity.py --repo /path/to/reviewed/tree
The output shows whether mismatched provider model IDs are accepted as success.
"""

import argparse
import importlib.util
import io
import json
from pathlib import Path
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    args = parser.parse_args()
    path = args.repo / "evaluation/smoke/model_smoke.py"
    spec = importlib.util.spec_from_file_location("reviewed_model_smoke", path)
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)
    env = {
        "KNOWFLOW_MODEL_BASE_URL": "https://provider.invalid/v1",
        "KNOWFLOW_EMBEDDING_MODEL": "selected-embedding",
        "KNOWFLOW_LLM_MODEL": "selected-chat",
        "KNOWFLOW_EMBEDDING_DIMENSIONS": "2",
        "OPENAI_API_KEY": "synthetic-test-credential",
    }
    for embedding_id, chat_id in (
        ("different-embedding", "selected-chat"),
        ("selected-embedding", "different-chat"),
        ("different-embedding", "different-chat"),
    ):
        embedding = {
            "model": embedding_id,
            "data": [{"index": i, "embedding": [1, 2]} for i in range(2)],
        }
        chat = {
            "model": chat_id,
            "choices": [{"message": {"content": "限制是 8 MiB。"}, "finish_reason": "stop"}],
        }
        responses = [io.BytesIO(json.dumps(item).encode()) for item in (embedding, chat)]
        with patch.object(smoke.request.OpenerDirector, "open", side_effect=responses):
            report, code = smoke.run(env, 1)
        print(json.dumps({
            "embedding_response_model": embedding_id,
            "chat_response_model": chat_id,
            "status": report["status"],
            "exit_code": code,
            "embedding_model_matches": report["checks"]["embedding"].get("provider_model_matches_request"),
            "chat_model_matches": report["checks"].get("chat", {}).get("provider_model_matches_request"),
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
