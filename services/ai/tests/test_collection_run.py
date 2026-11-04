import importlib.util
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from uuid import UUID
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from knowflow_ai.budget import BudgetLedger

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("collection_run", ROOT / "evaluation/collector/run.py")
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


def test_private_output_must_share_ignored_pack_root(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
    (repository / ".gitignore").write_text(".blindtest/\n", encoding="utf-8")
    dataset = repository / ".blindtest" / "out" / "runner"
    dataset.mkdir(parents=True)
    output = repository / ".blindtest" / "out" / "predictions.json"

    assert run.private_output_is_ignored(dataset, output)
    assert not run.private_output_is_ignored(dataset, repository / "predictions.json")


@pytest.mark.asyncio
@pytest.mark.parametrize("reach_soft_limit_on_last_question", [False, True])
@pytest.mark.parametrize("return_error_on_first_question", [False, True])
async def test_public_seed_upload_index_question_capture_and_cleanup_with_fake_http(
        tmp_path, reach_soft_limit_on_last_question, return_error_on_first_question):
    dataset = ROOT / "evaluation/data/seed-v1"
    manifest, questions, _documents, sources, _digest = run.scorer._load_dataset(dataset)
    uploaded, captures, runtime_rows, cleanup = [], {}, {}, []
    question_calls = []
    ledger = BudgetLedger(tmp_path / "budget.sqlite3")
    _manifest, selected, *_ = run.scorer._load_dataset(dataset)
    expected_questions = sum(row["split"] == "development" for row in selected)
    async def java_transport(request):
        path = request.url.path
        if request.method == "DELETE":
            cleanup.append(path)
            return httpx.Response(204)
        if path == "/api/v1/knowledge-bases":
            return httpx.Response(201, json={"id": "kb"})
        if path.endswith("/documents"):
            index = len(uploaded)
            document = manifest["documents"][index]
            uploaded.append(document)
            return httpx.Response(202, json={"document_id": str(index), "task_id": str(index)})
        if path.startswith("/api/v1/tasks/"):
            return httpx.Response(200, json={"status": "SUCCEEDED"})
        if path.startswith("/api/v1/documents/"):
            index = int(path.rsplit("/", 1)[1])
            return httpx.Response(200, json={"status": "READY", "source_sha256": uploaded[index]["sha256"],
                                           "active_index_version_id": str(index)})
        assert path.endswith("/questions")
        question_calls.append(path)
        if reach_soft_limit_on_last_question and len(question_calls) == expected_questions:
            now = datetime.now(timezone.utc)
            quote = {"provider": "synthetic", "model": "fake", "input_cny_per_million": "1",
                     "output_cny_per_million": "1", "source_url": "https://example.test/prices",
                     "verified_by": "test", "verified_at": (now - timedelta(hours=1)).isoformat(),
                     "valid_until": (now + timedelta(hours=1)).isoformat()}
            ledger.reserve("last-question", provider="synthetic", model="fake",
                           input_tokens_upper=8_000_000, output_tokens_upper=0, quote=quote)
        key = request.headers["Idempotency-Key"]
        request_id = "req-" + str(len(runtime_rows))
        runtime_rows[key] = {"id": str(UUID(int=len(runtime_rows) + 1)), "request_id": request_id,
                             "failure_code": "AI_PROCESSING_FAILED" if return_error_on_first_question else None}
        response = {"request_id": request_id, "answer": "Synthetic refusal", "has_answer": False, "sources": []}
        trace = []
        for index, document in enumerate(uploaded):
            text = sources[document["id"]]
            trace.append({"document_id": str(index), "content_version_id": "content-" + str(index),
                          "index_version_id": str(index), "source_id": "src-" + str(index),
                          "locator": {"kind": "text_range", "unit": "unicode_code_point", "start": 0, "end": len(text)},
                          "text_sha256": sha256(text.encode("utf-8")).hexdigest()})
        captures[request_id] = {"request_id": request_id, "response": response, "error_code": None, "trace": trace}
        return httpx.Response(503 if return_error_on_first_question else 200, json=response)
    async def ai_transport(request):
        return httpx.Response(200, json=captures.pop(request.url.path.rsplit("/", 1)[1]))
    async def fetch(sql, params):
        if "index_versions" in sql:
            return {"content_version_id": "content-" + params[0]}
        return runtime_rows[params[0]]
    output = tmp_path / "predictions.json"
    async with httpx.AsyncClient(base_url="http://java.test", transport=httpx.MockTransport(java_transport)) as java:
        async with httpx.AsyncClient(base_url="http://ai.test", transport=httpx.MockTransport(ai_transport)) as ai:
            if return_error_on_first_question:
                with pytest.raises(ValueError, match="COLLECTION_INCOMPLETE"):
                    await run.collect_dataset(
                        java=java, ai=ai, dataset=dataset, split="development", output=output,
                        run_metadata={"code_sha": "a" * 40, "schema_sha256": "b" * 64,
                                      "config_sha256": "c" * 64, "prompt_sha256": "d" * 64, "model": "fake"},
                        fetch_row=fetch, ledger=ledger)
                payload = json.loads(output.read_text())
            else:
                payload = await run.collect_dataset(
                    java=java, ai=ai, dataset=dataset, split="development", output=output,
                    run_metadata={"code_sha": "a" * 40, "schema_sha256": "b" * 64,
                                  "config_sha256": "c" * 64, "prompt_sha256": "d" * 64, "model": "fake"},
                    fetch_row=fetch, ledger=ledger)
    expected = sum(q["split"] == "development" for q in questions)
    assert len(uploaded) == 10
    assert len(payload["predictions"]) == (1 if return_error_on_first_question else expected)
    if not return_error_on_first_question:
        assert all(len(row["retrieved_evidence"]) == 10 for row in payload["predictions"])
    assert len(question_calls) == (1 if return_error_on_first_question else expected)
    assert cleanup == ["/api/v1/knowledge-bases/kb"]
    status = json.loads(output.with_suffix(".status.json").read_text())
    assert status["complete"] is not return_error_on_first_question
    assert bool(status["failures"]) is return_error_on_first_question
    if not return_error_on_first_question:
        assert run.scorer.evaluate(output, dataset_root=dataset)["sample_count"] == expected
    assert ledger.summary()["reserved_microyuan"] == (
        8_000_000 if reach_soft_limit_on_last_question and not return_error_on_first_question else 0)
