import importlib.util
import asyncio
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from threading import Barrier, Event
from types import SimpleNamespace

import pytest
import sqlite3


ROOT = Path(__file__).resolve().parents[3]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "evaluation" / "collector" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


budget = load("budget")
mapping = load("mapping")
capture = load("capture")
guarded = load("guarded_adapters")
NOW = datetime(2026, 11, 2, tzinfo=timezone.utc)
QUOTE = {"provider": "synthetic", "model": "model-a", "input_cny_per_million": "1",
         "output_cny_per_million": "2", "source_url": "https://example.test/prices",
         "verified_by": "test", "verified_at": "2026-11-01T00:00:00Z",
         "valid_until": "2026-11-03T00:00:00Z"}


def reserve(ledger, request_id, *, tokens=1_000_000, quote=None, model="model-a"):
    return ledger.reserve(request_id, provider="synthetic", model=model, input_tokens_upper=tokens,
                          output_tokens_upper=0, quote=quote if quote is not None else QUOTE, now=NOW)


def current_quote():
    now = datetime.now(timezone.utc)
    return {**QUOTE, "verified_at": (now - timedelta(hours=1)).isoformat(),
            "valid_until": (now + timedelta(hours=1)).isoformat()}


def verified_bounds(function):
    function.policy_id = "synthetic-test-policy"
    return function


def current_bound_evidence():
    quote = current_quote()
    return {key: quote[key] for key in ("provider", "model", "source_url", "verified_by", "verified_at", "valid_until")} | {"policy_id": "synthetic-test-policy"}


def test_real_evaluation_app_is_unconditionally_disabled():
    create_evaluation_app = load("wiring").create_evaluation_app
    with pytest.raises(RuntimeError, match="EVALUATION_SERVICE_NOT_READY"):
        create_evaluation_app()
    with pytest.raises(RuntimeError, match="EVALUATION_SERVICE_NOT_READY"):
        create_evaluation_app(object(), ledger=object(), token_bounds=lambda *_: (1, 1024))


@pytest.mark.asyncio
async def test_worker_sync_and_stream_factories_share_ledger_and_capture(monkeypatch, tmp_path):
    wiring = load("wiring")
    EvaluationFactories = wiring.EvaluationFactories
    from knowflow_ai.answering import ReadOnlyRetriever
    from knowflow_ai.embedding import EmbeddingSettings
    ledger_path = tmp_path / "budget.sqlite3"
    ledger = wiring.BudgetLedger(ledger_path)
    calls = []
    class Embedding:
        settings = SimpleNamespace(model="model-a")
        async def embed(self, texts, *, request_id):
            calls.append(("embed", request_id))
            return {"data": [{"embedding": [1.0] * 1024} for _ in texts]}
        async def aclose(self): pass
    class Llm:
        settings = SimpleNamespace(model="model-a")
        async def generate(self, question, evidence, *, request_id):
            calls.append(("generate", request_id))
            assert len(evidence) == 5
            return {"answer": "insufficient", "has_answer": False, "source_ids": []}
        async def stream_content(self, question, evidence, *, request_id):
            calls.append(("stream", request_id))
            assert len(evidence) == 5
            yield '{"answer":"insufficient","has_answer":false,"source_ids":[]}'
        async def aclose(self): pass
    class Contract:
        def validate(self, *_args): pass
    def fetch(_url, _query, params, _deadline=None, _cancellation=None):
        assert params[-1] == 10
        return [{"document_id": "d", "content_version_id": "c", "index_version_id": "i",
                 "text_content": "a", "text_sha256": sha256(b"a").hexdigest(),
                 "locator_kind": "text_range", "source_start": 0, "source_end": 1,
                 "source_page": None, "chunk_id": str(i)} for i in range(10)]
    monkeypatch.setattr(ReadOnlyRetriever, "_fetch_rows", staticmethod(fetch))
    common = {"provider": "synthetic", "model": "model-a", "quote": current_quote(),
              "bound_evidence": current_bound_evidence()}
    factories = EvaluationFactories(ledger=ledger,
        embedding={**common, "adapter_factory": Embedding, "token_bounds": verified_bounds(lambda *_: (100, 0))},
        llm={**common, "adapter_factory": Llm, "token_bounds": verified_bounds(lambda *_: (100, 1024))})
    factories.preflight()
    assert calls == []
    worker = factories.index_worker(object())
    worker_adapter = worker._embedding_factory()
    await worker_adapter.embed(["index"], request_id="index")
    await worker_adapter.aclose()
    settings = EmbeddingSettings(api_key="test-key" * 8)
    service = factories.answer_service("postgresql://readonly.invalid/db", Contract(), embedding_settings=settings)
    scope = {"owner_id": "u", "knowledge_base_id": "kb", "indexes": [
        {"document_id": "d", "content_version_id": "c", "index_version_id": "i"}]}
    result = await service.answer({"question": "q", "scope": scope, "request_id": "sync"})
    assert result["has_answer"] is False
    events = [event async for event in service.stream({"question": "q", "scope": scope, "request_id": "stream"})]
    assert events[-1]["event"] == "completed"
    assert len(await factories.traces.take("sync")) == 10
    assert len(await factories.traces.take("stream")) == 10
    assert calls == [("embed", "index"), ("embed", "sync"), ("generate", "sync"),
                     ("embed", "stream"), ("stream", "stream")]
    with closing(sqlite3.connect(ledger_path)) as db:
        assert db.execute("SELECT count(*) FROM reservations").fetchone()[0] == 5


def test_wiring_preflight_checks_both_prices_and_bounds_without_constructing_provider(tmp_path):
    wiring = load("wiring")
    calls = []
    common = {"provider": "synthetic", "model": "model-a", "quote": current_quote(),
              "bound_evidence": current_bound_evidence(), "adapter_factory": lambda: calls.append("provider")}
    embedding = {**common, "token_bounds": verified_bounds(lambda *_: (100, 0))}
    llm = {**common, "token_bounds": verified_bounds(lambda *_: (100, 1024))}
    ledger = wiring.BudgetLedger(tmp_path / "budget.sqlite3")
    wiring.EvaluationFactories(ledger=ledger, embedding=embedding, llm=llm).preflight()
    for bad_embedding, bad_llm in (({**embedding, "quote": None}, llm),
                                   (embedding, {**llm, "quote": None}),
                                   ({**embedding, "bound_evidence": None}, llm),
                                   (embedding, {**llm, "bound_evidence": None})):
        with pytest.raises(ValueError):
            wiring.EvaluationFactories(ledger=ledger, embedding=bad_embedding, llm=bad_llm).preflight()
    assert calls == []


@pytest.mark.asyncio
async def test_guard_reserves_every_embedding_and_llm_attempt_before_adapter_use(tmp_path):
    path = tmp_path / "budget.sqlite3"
    ledger = budget.BudgetLedger(path)
    calls = []
    def reserved_count():
        with closing(sqlite3.connect(path)) as db:
            return db.execute("SELECT count(*) FROM reservations").fetchone()[0]
    class Adapter:
        settings = SimpleNamespace(model="model-a")
        def __init__(self):
            assert reserved_count() > 0
        async def embed(self, texts, *, request_id):
            calls.append(("embed", reserved_count()))
            return {"data": []}
        async def generate(self, question, evidence, *, request_id):
            calls.append(("generate", reserved_count()))
            raise TimeoutError("synthetic")
        async def stream_content(self, question, evidence, *, request_id):
            calls.append(("stream", reserved_count()))
            yield "first"
            yield "second"
        async def aclose(self): pass
    @verified_bounds
    def bounds(operation, *_args):
        return (100, 0 if operation == "embed" else 1024)
    config = {"adapter_factory": Adapter, "ledger": ledger, "provider": "synthetic",
              "model": "model-a", "quote": current_quote(), "token_bounds": bounds,
              "bound_evidence": current_bound_evidence()}
    embedding = guarded.GuardedEmbedding(**config)
    llm = guarded.GuardedLlm(**config)
    await embedding.embed(["a"], request_id="same-request")
    await embedding.embed(["b"], request_id="same-request")
    with pytest.raises(TimeoutError):
        await llm.generate("q", [], request_id="same-request")
    stream = llm.stream_content("q", [], request_id="same-request")
    assert reserved_count() == 3  # Merely creating an async generator does not invoke it.
    assert await anext(stream) == "first"
    await stream.aclose()
    assert calls == [("embed", 1), ("embed", 2), ("generate", 3), ("stream", 4)]
    assert reserved_count() == 4  # Timeout and stream cancellation never refund.
    await embedding.aclose()
    await llm.aclose()


@pytest.mark.asyncio
async def test_guard_rejects_factory_using_a_different_model_before_call(tmp_path):
    path = tmp_path / "budget.sqlite3"
    calls = []
    class WrongModel:
        settings = SimpleNamespace(model="different-model")
        async def embed(self, texts, *, request_id): calls.append("network")
        async def aclose(self): calls.append("closed")
    adapter = guarded.GuardedEmbedding(
        adapter_factory=WrongModel, ledger=budget.BudgetLedger(path), provider="synthetic", model="model-a",
        quote=current_quote(), token_bounds=verified_bounds(lambda *_: (100, 0)),
        bound_evidence=current_bound_evidence())
    with pytest.raises(ValueError, match="ADAPTER_MODEL_MISMATCH"):
        await adapter.embed(["a"], request_id="request")
    assert calls == ["closed"]
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT count(*) FROM reservations").fetchone()[0] == 1


@pytest.mark.asyncio
async def test_guard_fails_closed_before_factory_for_unknown_price_or_bound(tmp_path):
    ledger = budget.BudgetLedger(tmp_path / "budget.sqlite3")
    calls = []
    def factory():
        calls.append("factory")
        raise AssertionError("must not construct adapter")
    common = {"adapter_factory": factory, "ledger": ledger, "provider": "synthetic", "model": "model-a"}
    no_price = guarded.GuardedEmbedding(**common, quote=None, token_bounds=verified_bounds(lambda *_: (100, 0)), bound_evidence=current_bound_evidence())
    with pytest.raises(ValueError, match="UNVERIFIED_PRICE"):
        await no_price.embed(["a"], request_id="r")
    no_bound = guarded.GuardedLlm(**common, quote=current_quote(), token_bounds=verified_bounds(lambda *_: None), bound_evidence=current_bound_evidence())
    with pytest.raises(ValueError, match="TOKEN_BOUNDS_UNAVAILABLE"):
        await no_bound.generate("q", [], request_id="r")
    short_output = guarded.GuardedLlm(**common, quote=current_quote(), token_bounds=verified_bounds(lambda *_: (100, 1023)), bound_evidence=current_bound_evidence())
    with pytest.raises(ValueError, match="TOKEN_BOUNDS_UNAVAILABLE"):
        await anext(short_output.stream_content("q", [], request_id="r"))
    unverified = guarded.GuardedEmbedding(**common, quote=current_quote(), token_bounds=verified_bounds(lambda *_: (100, 0)), bound_evidence=None)
    with pytest.raises(ValueError, match="TOKEN_BOUND_EVIDENCE_REQUIRED"):
        await unverified.embed(["a"], request_id="r")
    assert calls == []


@pytest.mark.asyncio
async def test_guard_cancelled_during_reservation_never_calls_provider_or_refunds(tmp_path):
    path = tmp_path / "budget.sqlite3"
    real_ledger = budget.BudgetLedger(path)
    entered, release, finished = Event(), Event(), Event()
    class BlockingLedger:
        def reserve(self, *args, **kwargs):
            entered.set()
            if not release.wait(3): raise RuntimeError("test timeout")
            try: return real_ledger.reserve(*args, **kwargs)
            finally: finished.set()
    called = []
    adapter = guarded.GuardedEmbedding(adapter_factory=lambda: called.append(True), ledger=BlockingLedger(),
        provider="synthetic", model="model-a", quote=current_quote(),
        token_bounds=verified_bounds(lambda *_: (100, 0)), bound_evidence=current_bound_evidence())
    task = asyncio.create_task(adapter.embed(["a"], request_id="request"))
    assert await asyncio.to_thread(entered.wait, 3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    release.set()
    assert await asyncio.to_thread(finished.wait, 3)
    assert called == []
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT count(*) FROM reservations").fetchone()[0] == 1


@pytest.mark.asyncio
async def test_guard_freezes_evidence_before_estimation_and_reservation(tmp_path):
    entered, release = Event(), Event()
    real_ledger = budget.BudgetLedger(tmp_path / "budget.sqlite3")
    class BlockingLedger:
        def reserve(self, *args, **kwargs):
            entered.set()
            if not release.wait(3): raise RuntimeError("test timeout")
            return real_ledger.reserve(*args, **kwargs)
    captured = []
    class Adapter:
        settings = SimpleNamespace(model="model-a")
        async def generate(self, question, evidence, *, request_id):
            captured.append(evidence)
            return {}
        async def aclose(self): pass
    def estimate(operation, question, evidence):
        assert evidence == [{"text_content": "original"}]
        return (100, 1024)
    adapter = guarded.GuardedLlm(adapter_factory=Adapter, ledger=BlockingLedger(),
        provider="synthetic", model="model-a", quote=current_quote(),
        token_bounds=verified_bounds(estimate), bound_evidence=current_bound_evidence())
    evidence = [{"text_content": "original"}]
    task = asyncio.create_task(adapter.generate("q", evidence, request_id="request"))
    assert await asyncio.to_thread(entered.wait, 3)
    evidence[0]["text_content"] = "changed after estimation"
    release.set()
    await task
    assert captured == [[{"text_content": "original"}]]
    await adapter.aclose()


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
    with pytest.raises(ValueError, match="INVALID_REQUEST_ID_STATE"):
        await store.record("r1", rows, scope)


@pytest.mark.asyncio
async def test_capture_isolates_requests_rejects_reuse_and_out_of_scope():
    entered = asyncio.Event()
    release = asyncio.Event()
    scope = {"indexes": [{"document_id": "d", "content_version_id": "c", "index_version_id": "i"}]}
    def row(source_id, document_id="d"):
        return {"document_id": document_id, "content_version_id": "c", "index_version_id": "i",
                "source_id": source_id, "locator": {"kind": "text_range", "unit": "unicode_code_point", "start": 0, "end": 1}, "text_sha256": "a" * 64}
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
async def test_capture_rejects_locator_with_unexpected_private_data():
    scope = {"indexes": [{"document_id": "d", "content_version_id": "c", "index_version_id": "i"}]}
    row = {"document_id": "d", "content_version_id": "c", "index_version_id": "i", "source_id": "src",
           "locator": {"kind": "text_range", "unit": "unicode_code_point", "start": 0, "end": 1, "text": "private"},
           "text_sha256": "a" * 64}
    class Retriever:
        async def retrieve(self, *args, **kwargs): return [row]
    store = capture.CaptureStore()
    with pytest.raises(ValueError, match="INVALID_RETRIEVAL_TRACE"):
        await capture.CapturingRetriever(Retriever(), store).retrieve("q", scope, "r")
    with pytest.raises(ValueError, match="INVALID_REQUEST_ID_STATE"):
        await store.record("r", [{**row, "locator": {k: v for k, v in row["locator"].items() if k != "text"}}], scope)


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
