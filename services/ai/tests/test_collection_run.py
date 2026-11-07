import importlib.util
from hashlib import sha256
import json
from pathlib import Path
from uuid import UUID
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from knowflow_ai.budget import BudgetLedger

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("collection_run", ROOT / "evaluation/collector/run.py")
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


@pytest.mark.asyncio
@pytest.mark.parametrize("reach_soft_limit_on_last_question", [False, True])
async def test_public_seed_upload_index_question_capture_and_cleanup_with_fake_http(
        tmp_path, reach_soft_limit_on_last_question):
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
        runtime_rows[key] = {"id": str(UUID(int=len(runtime_rows) + 1)), "request_id": request_id}
        response = {"request_id": request_id, "answer": "Synthetic refusal", "has_answer": False, "sources": []}
        trace = []
        for index, document in enumerate(uploaded):
            text = sources[document["id"]]
            trace.append({"document_id": str(index), "content_version_id": "content-" + str(index),
                          "index_version_id": str(index), "source_id": "src-" + str(index),
                          "locator": {"kind": "text_range", "unit": "unicode_code_point", "start": 0, "end": len(text)},
                          "text_sha256": sha256(text.encode("utf-8")).hexdigest()})
        captures[request_id] = {"request_id": request_id, "response": response, "error_code": None, "trace": trace,
                                "citation": {"decision": "refused", "reason": "empty_evidence",
                                             "repair_gate_reason": "ineligible_reason",
                                             "repair_attempt": 0, "repair_outcome": "not_attempted"}}
        return httpx.Response(200, json=response)
    async def ai_transport(request):
        return httpx.Response(200, json=captures.pop(request.url.path.rsplit("/", 1)[1]))
    async def fetch(sql, params):
        if "index_versions" in sql:
            return {"content_version_id": "content-" + params[0]}
        return runtime_rows[params[0]]
    output = tmp_path / "predictions.json"
    async with httpx.AsyncClient(base_url="http://java.test", transport=httpx.MockTransport(java_transport)) as java:
        async with httpx.AsyncClient(base_url="http://ai.test", transport=httpx.MockTransport(ai_transport)) as ai:
            payload = await run.collect_dataset(
                java=java, ai=ai, dataset=dataset, split="development", output=output,
                run_metadata={"code_sha": "a" * 40, "schema_sha256": "b" * 64,
                              "config_sha256": "c" * 64, "prompt_sha256": "d" * 64, "model": "fake"},
                fetch_row=fetch, ledger=ledger)
    expected = sum(q["split"] == "development" for q in questions)
    assert len(uploaded) == 10
    assert len(payload["predictions"]) == expected
    assert all(len(row["retrieved_evidence"]) == 10 for row in payload["predictions"])
    assert cleanup == ["/api/v1/knowledge-bases/kb"]
    assert json.loads(output.with_suffix(".status.json").read_text())["complete"] is True
    assert run.scorer.evaluate(output, dataset_root=dataset)["sample_count"] == expected
    assert json.loads(output.with_suffix(".status.json").read_text())["complete"] is True
    assert ledger.summary()["reserved_microyuan"] == (8_000_000 if reach_soft_limit_on_last_question else 0)
    diagnostics = json.loads(output.with_suffix(".diagnostics.json").read_text())
    assert diagnostics["dataset_sha256"] == payload["dataset_sha256"]
    assert [entry["question_id"] for entry in diagnostics["diagnostics"]] == [
        row["question_id"] for row in payload["predictions"]]
    assert all(entry["outcome"] == "refused" for entry in diagnostics["diagnostics"])
    assert all(entry["citation"]["reason"] == "empty_evidence"
               for entry in diagnostics["diagnostics"])
    assert all(entry["citation"]["repair_gate_reason"] == "ineligible_reason"
               for entry in diagnostics["diagnostics"])
    sidecar = json.loads(output.with_suffix(".public-sources.json").read_text())
    assert sidecar["sidecar_version"] == 1
    assert sidecar["split"] == "development"
    assert sidecar["dataset_sha256"] == payload["dataset_sha256"]
    assert [entry["question_id"] for entry in sidecar["questions"]] == [
        row["question_id"] for row in payload["predictions"]]
    assert all(entry["sources"] == [] for entry in sidecar["questions"])


@pytest.mark.asyncio
async def test_cleanup_failure_does_not_mask_the_collection_error(tmp_path):
    dataset = ROOT / "evaluation/data/seed-v1"
    ledger = BudgetLedger(tmp_path / "budget.sqlite3")
    output = tmp_path / "predictions.json"
    cleanup = []

    async def java_transport(request):
        if request.method == "DELETE":
            cleanup.append(request.url.path)
            return httpx.Response(500)
        if request.url.path == "/api/v1/knowledge-bases":
            return httpx.Response(201, json={"id": "kb"})
        if request.url.path.endswith("/documents"):
            return httpx.Response(500)
        raise AssertionError("unexpected " + request.url.path)

    async def unused_ai(*_args, **_kwargs):
        raise AssertionError("ai must not run when upload fails")

    async def unused_fetch(*_args, **_kwargs):
        raise AssertionError("fetch_row must not run when upload fails")

    async with httpx.AsyncClient(base_url="http://java.test", transport=httpx.MockTransport(java_transport)) as java:
        with pytest.raises(ValueError, match="EVALUATION_UPLOAD_FAILED"):
            await run.collect_dataset(
                java=java, ai=object(), dataset=dataset, split="development", output=output,
                run_metadata={"code_sha": "a" * 40, "schema_sha256": "b" * 64,
                              "config_sha256": "c" * 64, "prompt_sha256": "d" * 64, "model": "fake"},
                fetch_row=unused_fetch, ledger=ledger)

    assert cleanup == ["/api/v1/knowledge-bases/kb"]
    status = json.loads(output.with_suffix(".status.json").read_text())
    assert status["complete"] is False
    assert status["failures"] == [{"code": "EVALUATION_CLEANUP_FAILED"}]


@pytest.mark.asyncio
async def test_error_rows_are_recorded_as_failures_and_mark_collection_incomplete(tmp_path):
    dataset = ROOT / "evaluation/data/seed-v1"
    manifest, questions, _documents, sources, _digest = run.scorer._load_dataset(dataset)
    uploaded, captures, runtime_rows = [], {}, {}
    cleanup = []
    ledger = BudgetLedger(tmp_path / "budget.sqlite3")

    async def java_transport(request):
        path = request.url.path
        if request.method == "DELETE":
            cleanup.append(path)
            return httpx.Response(204)
        if path == "/api/v1/knowledge-bases":
            return httpx.Response(201, json={"id": "kb"})
        if path.endswith("/documents"):
            index = len(uploaded)
            uploaded.append(manifest["documents"][index])
            return httpx.Response(202, json={"document_id": str(index), "task_id": str(index)})
        if path.startswith("/api/v1/tasks/"):
            return httpx.Response(200, json={"status": "SUCCEEDED"})
        if path.startswith("/api/v1/documents/"):
            index = int(path.rsplit("/", 1)[1])
            return httpx.Response(200, json={"status": "READY", "source_sha256": uploaded[index]["sha256"],
                                           "active_index_version_id": str(index)})
        assert path.endswith("/questions")
        key = request.headers["Idempotency-Key"]
        request_id = "req-" + str(len(runtime_rows))
        runtime_rows[key] = {"id": str(UUID(int=len(runtime_rows) + 1)), "request_id": request_id,
                             "failure_code": "AI_PROCESSING_FAILED"}
        trace = []
        for index, document in enumerate(uploaded):
            text = sources[document["id"]]
            trace.append({"document_id": str(index), "content_version_id": "content-" + str(index),
                          "index_version_id": str(index), "source_id": "src-" + str(index),
                          "locator": {"kind": "text_range", "unit": "unicode_code_point",
                                      "start": 0, "end": len(text)},
                          "text_sha256": sha256(text.encode("utf-8")).hexdigest()})
        captures[request_id] = {"request_id": request_id, "response": None,
                                "error_code": "AI_PROCESSING_FAILED", "trace": trace, "citation": None}
        return httpx.Response(500, json={"code": "AI_PROCESSING_FAILED"})

    async def ai_transport(request):
        return httpx.Response(200, json=captures.pop(request.url.path.rsplit("/", 1)[1]))

    async def fetch(sql, params):
        if "index_versions" in sql:
            return {"content_version_id": "content-" + params[0]}
        return runtime_rows[params[0]]

    output = tmp_path / "predictions.json"
    async with httpx.AsyncClient(base_url="http://java.test", transport=httpx.MockTransport(java_transport)) as java:
        async with httpx.AsyncClient(base_url="http://ai.test", transport=httpx.MockTransport(ai_transport)) as ai:
            with pytest.raises(ValueError, match="COLLECTION_INCOMPLETE"):
                await run.collect_dataset(
                    java=java, ai=ai, dataset=dataset, split="development", output=output,
                    run_metadata={"code_sha": "a" * 40, "schema_sha256": "b" * 64,
                                  "config_sha256": "c" * 64, "prompt_sha256": "d" * 64, "model": "fake"},
                    fetch_row=fetch, ledger=ledger)

    expected = sum(question["split"] == "development" for question in questions)
    status = json.loads(output.with_suffix(".status.json").read_text())
    assert status["complete"] is False
    assert len(status["failures"]) == expected
    assert {failure["error_code"] for failure in status["failures"]} == {"AI_PROCESSING_FAILED"}
    assert all(failure["question_id"] for failure in status["failures"])
    assert cleanup == ["/api/v1/knowledge-bases/kb"]


@pytest.mark.asyncio
async def test_collect_dataset_stops_when_shared_ledger_records_a_budget_stop(tmp_path):
    dataset = ROOT / "evaluation/data/seed-v1"
    ledger = BudgetLedger(tmp_path / "budget.sqlite3")
    now = datetime.now(timezone.utc)
    quote = {"provider": "synthetic", "model": "fake", "input_cny_per_million": "1",
             "output_cny_per_million": "1", "source_url": "https://example.test/prices",
             "verified_by": "test", "verified_at": (now - timedelta(hours=1)).isoformat(),
             "valid_until": (now + timedelta(hours=1)).isoformat()}
    ledger.reserve("spent", provider="synthetic", model="fake",
                   input_tokens_upper=7_000_000, output_tokens_upper=0, quote=quote)
    with pytest.raises(ValueError, match="BUDGET_SOFT_STOP"):
        ledger.reserve("crosses-soft-stop", provider="synthetic", model="fake",
                       input_tokens_upper=2_000_000, output_tokens_upper=0, quote=quote)
    assert ledger.summary()["reserved_microyuan"] == 7_000_000
    assert ledger.stop_reason() == "BUDGET_SOFT_STOP"

    async def java_transport(request):
        if request.method == "DELETE":
            return httpx.Response(204)
        if request.url.path == "/api/v1/knowledge-bases":
            return httpx.Response(201, json={"id": "kb"})
        raise AssertionError("upload must not start after a recorded budget stop")

    output = tmp_path / "predictions.json"
    async with httpx.AsyncClient(base_url="http://java.test", transport=httpx.MockTransport(java_transport)) as java:
        with pytest.raises(ValueError, match="BUDGET_SOFT_STOP"):
            await run.collect_dataset(
                java=java, ai=object(), dataset=dataset, split="development", output=output,
                run_metadata={"code_sha": "a" * 40, "schema_sha256": "b" * 64,
                              "config_sha256": "c" * 64, "prompt_sha256": "d" * 64, "model": "fake"},
                fetch_row=lambda *_args, **_kwargs: None, ledger=ledger)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_limit", [0, -1, 1.5, "2", True])
async def test_collect_dataset_rejects_invalid_limit(tmp_path, bad_limit):
    dataset = ROOT / "evaluation/data/seed-v1"
    ledger = BudgetLedger(tmp_path / "budget.sqlite3")
    output = tmp_path / "predictions.json"

    async def unused_fetch(*_args, **_kwargs):
        raise AssertionError("fetch_row must not run for invalid limit")

    with pytest.raises(ValueError, match="INVALID_COLLECTION_LIMIT"):
        await run.collect_dataset(
            java=object(), ai=object(), dataset=dataset, split="development",
            output=output,
            run_metadata={"code_sha": "a" * 40, "schema_sha256": "b" * 64,
                          "config_sha256": "c" * 64, "prompt_sha256": "d" * 64, "model": "fake"},
            fetch_row=unused_fetch, ledger=ledger, limit=bad_limit)


@pytest.mark.asyncio
async def test_collect_dataset_limit_slices_selected_questions(tmp_path):
    dataset = ROOT / "evaluation/data/seed-v1"
    manifest, questions, _documents, sources, _digest = run.scorer._load_dataset(dataset)
    uploaded, captures, runtime_rows, cleanup = [], {}, {}, []
    ledger = BudgetLedger(tmp_path / "budget.sqlite3")

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
        key = request.headers["Idempotency-Key"]
        request_id = "req-" + str(len(runtime_rows))
        runtime_rows[key] = {"id": str(UUID(int=len(runtime_rows) + 1)), "request_id": request_id}
        response = {"request_id": request_id, "answer": "Synthetic refusal", "has_answer": False, "sources": []}
        trace = []
        for index, document in enumerate(uploaded):
            text = sources[document["id"]]
            trace.append({"document_id": str(index), "content_version_id": "content-" + str(index),
                          "index_version_id": str(index), "source_id": "src-" + str(index),
                          "locator": {"kind": "text_range", "unit": "unicode_code_point", "start": 0, "end": len(text)},
                          "text_sha256": sha256(text.encode("utf-8")).hexdigest()})
        captures[request_id] = {"request_id": request_id, "response": response, "error_code": None, "trace": trace}
        return httpx.Response(200, json=response)

    async def ai_transport(request):
        return httpx.Response(200, json=captures.pop(request.url.path.rsplit("/", 1)[1]))

    async def fetch(sql, params):
        if "index_versions" in sql:
            return {"content_version_id": "content-" + params[0]}
        return runtime_rows[params[0]]

    output = tmp_path / "predictions.json"
    async with httpx.AsyncClient(base_url="http://java.test", transport=httpx.MockTransport(java_transport)) as java:
        async with httpx.AsyncClient(base_url="http://ai.test", transport=httpx.MockTransport(ai_transport)) as ai:
            payload = await run.collect_dataset(
                java=java, ai=ai, dataset=dataset, split="development", output=output,
                run_metadata={"code_sha": "a" * 40, "schema_sha256": "b" * 64,
                              "config_sha256": "c" * 64, "prompt_sha256": "d" * 64, "model": "fake"},
                fetch_row=fetch, ledger=ledger, limit=1)
    assert len(payload["predictions"]) == 1
    assert cleanup == ["/api/v1/knowledge-bases/kb"]
    assert json.loads(output.with_suffix(".status.json").read_text())["complete"] is True


@pytest.mark.asyncio
async def test_collect_dataset_records_public_source_locator_in_sidecar(tmp_path):
    dataset = ROOT / "evaluation/data/seed-v1"
    ledger = BudgetLedger(tmp_path / "budget.sqlite3")
    output = tmp_path / "predictions.json"
    runtime_id = str(UUID(int=7))
    request_id = "req-locator"
    source_text = "0123456789"
    trace = [{"document_id": "doc-1", "content_version_id": "cv-1", "index_version_id": "iv-1",
              "source_id": "runtime-src", "locator": {"kind": "text_range", "unit": "unicode_code_point",
                                                     "start": 0, "end": len(source_text)},
              "text_sha256": sha256(source_text.encode("utf-8")).hexdigest()}]
    public_id = run.collector.prediction._mapping.public_source_id(runtime_id, "runtime-src")
    internal = {"request_id": request_id, "answer": "答案句 [runtime-src]。", "has_answer": True,
                "sources": [{"source_id": "runtime-src", "document_id": "doc-1",
                             "content_version_id": "cv-1", "index_version_id": "iv-1",
                             "locator": {"kind": "text_range", "unit": "unicode_code_point",
                                         "start": 0, "end": len(source_text)}, "quote": source_text}]}
    response = {"request_id": request_id, "answer": f"答案句 [{public_id}]。", "has_answer": True,
                "sources": [{"source_id": public_id, "document_id": "doc-1",
                             "content_version_id": "cv-1", "index_version_id": "iv-1",
                             "locator": {"kind": "text_range", "unit": "unicode_code_point",
                                         "start": 2, "end": 5}, "quote": "234"}]}
    capture = {"request_id": request_id, "response": internal, "error_code": None, "trace": trace,
               "citation": {"decision": "supported", "reason": None}}

    async def java_transport(request):
        assert request.url.path.endswith("/questions")
        return httpx.Response(200, json=response)

    async def ai_transport(request):
        assert request.url.path.endswith(request_id)
        return httpx.Response(200, json=capture)

    async def lookup(_key):
        return {"id": runtime_id, "request_id": request_id, "failure_code": None}

    mappings = {("doc-1", "cv-1", "iv-1"): {"source_bytes": source_text.encode("utf-8"),
                                            "source_sha256": sha256(source_text.encode("utf-8")).hexdigest(),
                                            "dataset_document_id": "d1",
                                            "dataset_content_version_id": "c1"}}
    sidecar = []
    async with httpx.AsyncClient(base_url="http://java.test", transport=httpx.MockTransport(java_transport)) as java:
        async with httpx.AsyncClient(base_url="http://ai.test", transport=httpx.MockTransport(ai_transport)) as ai:
            row = await run.collector.collect_question(
                java=java, ai=ai, knowledge_base_id="kb", question="q", question_id="candidate-01",
                mappings=mappings, lookup_question=lookup, public_sources_out=sidecar)
    assert row["outcome"] == "answered"
    assert set(row) == {"question_id", "outcome", "answer", "answer_sha256", "retrieved_evidence",
                        "citations", "latency_ms", "error_code"}
    assert "sources" not in row and "locator" not in row
    assert sidecar == [{"question_id": "candidate-01", "runtime_question_id": runtime_id,
                        "request_id": request_id, "sources": response["sources"]}]
    assert sidecar[0]["sources"][0]["locator"] == {"kind": "text_range", "unit": "unicode_code_point",
                                                  "start": 2, "end": 5}
    assert sidecar[0]["sources"][0]["quote"] == "234"
