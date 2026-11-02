import importlib.util
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from threading import Barrier

import pytest


ROOT = Path(__file__).resolve().parents[3]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "evaluation" / "collector" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


budget = load("budget")
mapping = load("mapping")
capture = load("capture")
NOW = datetime(2026, 11, 2, tzinfo=timezone.utc)
QUOTE = {"provider": "synthetic", "model": "model-a", "input_cny_per_million": "1",
         "output_cny_per_million": "2", "source_url": "https://example.test/prices",
         "verified_by": "test", "verified_at": "2026-11-01T00:00:00Z",
         "valid_until": "2026-11-03T00:00:00Z"}


def reserve(ledger, request_id, *, tokens=1_000_000, quote=None, model="model-a"):
    return ledger.reserve(request_id, provider="synthetic", model=model, input_tokens_upper=tokens,
                          output_tokens_upper=0, quote=quote if quote is not None else QUOTE, now=NOW)


def test_budget_is_durable_and_duplicate_retries_cannot_reuse_reservation(tmp_path):
    path = tmp_path / "budget.sqlite3"
    result = reserve(budget.BudgetLedger(path), "request-1", tokens=9_000_000)
    assert result["remaining_microyuan"] == 1_000_000
    reopened = budget.BudgetLedger(path)
    with pytest.raises(ValueError, match="DUPLICATE_REQUEST_ID"):
        reserve(reopened, "request-1", tokens=1)
    with pytest.raises(ValueError, match="BUDGET_EXCEEDED"):
        reserve(reopened, "retry-2", tokens=1_000_001)
    assert reserve(reopened, "retry-3")["remaining_microyuan"] == 0
    with pytest.raises(ValueError, match="BUDGET_LIMIT_MISMATCH"):
        budget.BudgetLedger(path, limit_microyuan=9_000_000)
    # Windows refuses removal while SQLite connections remain open.
    path.unlink()


def test_budget_reservations_are_serialized_across_independent_connections(tmp_path):
    path = tmp_path / "budget.sqlite3"
    budget.BudgetLedger(path)
    barrier = Barrier(3)

    def run(index):
        ledger = budget.BudgetLedger(path)
        barrier.wait()
        try:
            reserve(ledger, f"attempt-{index}", tokens=4_000_000)
            return "reserved"
        except ValueError as exc:
            return str(exc)

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(run, range(3)))
    assert sorted(results) == ["BUDGET_EXCEEDED", "reserved", "reserved"]


def test_budget_rejects_unknown_expired_or_wrong_model_prices(tmp_path):
    ledger = budget.BudgetLedger(tmp_path / "budget.sqlite3")
    with pytest.raises(ValueError, match="UNVERIFIED_PRICE"):
        reserve(ledger, "unverified", quote={**QUOTE, "verified_by": ""})
    with pytest.raises(ValueError, match="PRICE_EXPIRED_OR_UNVERIFIED"):
        reserve(ledger, "expired", quote={**QUOTE, "valid_until": "2026-11-01T01:00:00Z"})
    with pytest.raises(ValueError, match="PRICE_MODEL_MISMATCH"):
        reserve(ledger, "wrong-model", model="another")
    with pytest.raises(ValueError, match="UNVERIFIED_PRICE"):
        reserve(ledger, "invalid-price", quote={**QUOTE, "input_cny_per_million": "NaN"})
    assert reserve(ledger, "ok", tokens=1)["reserved_microyuan"] == 1


def test_budget_rounds_up_and_reserves_output_upper_bound(tmp_path):
    ledger = budget.BudgetLedger(tmp_path / "budget.sqlite3")
    result = ledger.reserve("mixed", provider="synthetic", model="model-a", input_tokens_upper=3,
                            output_tokens_upper=2, quote={**QUOTE, "input_cny_per_million": "0.1",
                                                         "output_cny_per_million": "0.2"}, now=NOW)
    assert result["reserved_microyuan"] == 1
    precise = ledger.reserve("precise", provider="synthetic", model="model-a", input_tokens_upper=10,
                             output_tokens_upper=0, quote={**QUOTE, "input_cny_per_million": "0.10000000000000000000000000001"}, now=NOW)
    assert precise["reserved_microyuan"] == 2


def test_public_id_matches_java_name_uuid():
    assert mapping.public_source_id("550e8400-e29b-41d4-a716-446655440000", "src-1") == "8e12941d-7836-3c6d-87d0-65e9e8b5267b"


@pytest.mark.asyncio
async def test_capture_runs_one_top10_retrieval_and_preserves_generation_top5():
    from knowflow_ai.answering import AnswerService

    rows = [{"document_id": "d", "content_version_id": "c", "index_version_id": "i",
             "source_id": f"src-{i}", "text_content": "private text", "text_sha256": "a" * 64,
             "locator": {"kind": "text_range", "unit": "unicode_code_point", "start": i, "end": i + 1}}
            for i in range(10)]
    scope = {"indexes": [{"document_id": "d", "content_version_id": "c", "index_version_id": "i"}]}

    class Retriever:
        def __init__(self): self.calls = []
        async def retrieve(self, question, scope, request_id, *, deadline, top_k):
            self.calls.append((request_id, top_k))
            return rows

    class Contract:
        def validate(self, *_args): pass

    class Llm:
        async def generate(self, question, evidence, *, request_id):
            assert evidence == rows[:5]
            return {"answer": "insufficient", "has_answer": False, "source_ids": []}
        async def aclose(self): pass

    store = capture.CaptureStore()
    retriever = Retriever()
    service = AnswerService("unused", Contract(), retriever=capture.CapturingRetriever(retriever, store),
                            llm_factory=Llm)
    result = await service.answer({"question": "test", "scope": scope, "request_id": "r1"})
    assert result["has_answer"] is False
    assert retriever.calls == [("r1", 10)]
    trace = await store.take("r1")
    assert [row["source_id"] for row in trace] == [f"src-{i}" for i in range(10)]
    assert all("text_content" not in row for row in trace)
    with pytest.raises(ValueError, match="TRACE_NOT_AVAILABLE"):
        await store.take("r1")


@pytest.mark.asyncio
async def test_capture_isolates_requests_rejects_reuse_and_out_of_scope():
    entered = asyncio.Event()
    release = asyncio.Event()
    scope = {"indexes": [{"document_id": "d", "content_version_id": "c", "index_version_id": "i"}]}
    def row(source_id, document_id="d"):
        return {"document_id": document_id, "content_version_id": "c", "index_version_id": "i",
                "source_id": source_id, "locator": {"start": 0}, "text_sha256": "a" * 64}
    class Retriever:
        async def retrieve(self, question, scope, request_id, *, deadline, top_k):
            if request_id == "first":
                entered.set()
                await release.wait()
            return [row(request_id, "other" if request_id == "bad" else "d")]
    store = capture.CaptureStore()
    retriever = capture.CapturingRetriever(Retriever(), store)
    first = asyncio.create_task(retriever.retrieve("q", scope, "first"))
    await entered.wait()
    with pytest.raises(ValueError, match="DUPLICATE_REQUEST_ID"):
        await retriever.retrieve("q", scope, "first")
    assert (await retriever.retrieve("q", scope, "second"))[0]["source_id"] == "second"
    release.set()
    await first
    assert (await store.take("first"))[0]["source_id"] == "first"
    assert (await store.take("second"))[0]["source_id"] == "second"
    with pytest.raises(ValueError, match="INVALID_RETRIEVAL_TRACE"):
        await retriever.retrieve("q", scope, "bad")
    with pytest.raises(ValueError, match="TRACE_NOT_AVAILABLE"):
        await store.take("bad")


@pytest.mark.asyncio
async def test_capture_uses_real_retriever_once_with_top10(monkeypatch):
    from knowflow_ai.answering import ReadOnlyRetriever
    from knowflow_ai.embedding import EmbeddingSettings
    calls = {"embedding": 0, "sql": 0}
    class Embedding:
        async def embed(self, texts, *, request_id):
            calls["embedding"] += 1
            return {"data": [{"embedding": [1.0] * 1024} for _ in texts]}
        async def aclose(self): pass
    def fetch(_url, _query, params, _deadline=None, _cancellation=None):
        calls["sql"] += 1
        assert params[-1] == 10
        return [{"document_id": "d", "content_version_id": "c", "index_version_id": "i",
                 "text_content": "a", "text_sha256": sha256(b"a").hexdigest(),
                 "locator_kind": "text_range", "source_start": 0, "source_end": 1,
                 "source_page": None, "chunk_id": str(i)} for i in range(10)]
    monkeypatch.setattr(ReadOnlyRetriever, "_fetch_rows", staticmethod(fetch))
    real = ReadOnlyRetriever("postgresql://readonly.invalid/db", embedding_factory=Embedding,
                             embedding_settings=EmbeddingSettings(api_key="test-key" * 8))
    scope = {"owner_id": "u", "knowledge_base_id": "kb", "indexes": [
        {"document_id": "d", "content_version_id": "c", "index_version_id": "i"}]}
    store = capture.CaptureStore()
    visible = await capture.CapturingRetriever(real, store).retrieve("q", scope, "request")
    trace = await store.take("request")
    assert calls == {"embedding": 1, "sql": 1}
    assert len(visible) == 5 and len(trace) == 10
    assert [row["source_id"] for row in visible] == [row["source_id"] for row in trace[:5]]


def test_trace_maps_unicode_range_and_rejects_wrong_bytes_and_versions():
    source = "甲证据乙".encode("utf-8")
    key = ("runtime-doc", "runtime-content", "runtime-index")
    entry = {"dataset_document_id": "doc", "dataset_content_version_id": "version",
             "source_bytes": source, "source_sha256": sha256(source).hexdigest()}
    row = {"document_id": key[0], "content_version_id": key[1], "index_version_id": key[2],
           "source_id": "src-1", "locator": {"kind": "text_range", "unit": "unicode_code_point", "start": 1, "end": 3},
           "text_sha256": sha256("证据".encode("utf-8")).hexdigest()}
    question = "550e8400-e29b-41d4-a716-446655440000"
    result = mapping.map_retrieval(question, [row], {key: entry})
    assert result == [{"document_id": "doc", "content_version_id": "version", "start": 1, "end": 3,
                       "text_sha256": row["text_sha256"], "source_id": "8e12941d-7836-3c6d-87d0-65e9e8b5267b"}]
    with pytest.raises(ValueError, match="SOURCE_HASH_MISMATCH"):
        mapping.map_retrieval(question, [row], {key: {**entry, "source_bytes": b"tampered"}})
    with pytest.raises(ValueError, match="INVALID_TRACE_MAPPING"):
        mapping.map_retrieval(question, [{**row, "index_version_id": "old-index"}], {key: entry})
    with pytest.raises(ValueError, match="DUPLICATE_SOURCE_ID"):
        mapping.map_retrieval(question, [row, row], {key: entry})
