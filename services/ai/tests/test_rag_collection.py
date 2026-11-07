import importlib.util
import asyncio
import json
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from threading import Barrier, Event
from types import SimpleNamespace

import pytest
import sqlite3
import subprocess
import sys

from knowflow_ai.repair_gate import REPAIR_GATE_REASONS


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
prediction = load("prediction")
NOW = datetime(2026, 11, 2, tzinfo=timezone.utc)
QUOTE = {"provider": "synthetic", "model": "model-a", "input_cny_per_million": "1",
         "output_cny_per_million": "2", "source_url": "https://example.test/prices",
         "verified_by": "test", "verified_at": "2026-11-01T00:00:00Z",
         "valid_until": "2026-11-03T00:00:00Z"}


def reserve(ledger, request_id, *, tokens=1_000_000, quote=None, model="model-a"):
    return ledger.reserve(request_id, provider="synthetic", model=model, input_tokens_upper=tokens,
                          output_tokens_upper=0, quote=quote if quote is not None else QUOTE, now=NOW)


def test_three_yuan_budget_summary_persists_and_closes_connections(tmp_path):
    path = tmp_path / "budget.sqlite3"
    ledger = budget.BudgetLedger(path, limit_microyuan=3_000_000)
    reserve(ledger, "attempt-1", tokens=1_000_000)
    reserve(ledger, "attempt-2", tokens=500_000)
    reopened = budget.BudgetLedger(path, limit_microyuan=3_000_000)
    assert reopened.summary() == {
        "limit_microyuan": 3_000_000, "reserved_microyuan": 1_500_000,
        "remaining_microyuan": 1_500_000, "paid_reservations": 2,
        "zero_price_reservations": 0,
    }
    with pytest.raises(ValueError, match="BUDGET_EXCEEDED"):
        reserve(reopened, "attempt-3", tokens=1_500_001)
    with closing(sqlite3.connect(path, timeout=0)) as db:
        db.execute("BEGIN EXCLUSIVE")


def current_quote():
    now = datetime.now(timezone.utc)
    return {**QUOTE, "verified_at": (now - timedelta(hours=1)).isoformat(),
            "valid_until": (now + timedelta(hours=1)).isoformat()}


def test_estimate_cli_stops_at_soft_limit_without_touching_a_ledger(tmp_path):
    path = tmp_path / "requests.json"
    path.write_text(json.dumps([
        {"request_id": f"request-{i}", "provider": "synthetic", "model": "model-a",
         "input_tokens_upper": 4_000_000, "output_tokens_upper": 0,
         "quote": current_quote()}
        for i in range(3)
    ]), encoding="utf-8")
    result = subprocess.run([sys.executable, str(ROOT / "evaluation/collector/estimate.py"), str(path)],
                            capture_output=True, text=True, encoding="utf-8", check=False)
    assert result.returncode == 1
    output = json.loads(result.stdout)
    assert output["reason"] == "BUDGET_SOFT_STOP"
    assert output["stopped_at"] == 2
    assert output["summary"]["reserved_microyuan"] == 8_000_000
    assert list(tmp_path.iterdir()) == [path]


def verified_bounds(function):
    function.policy_id = "synthetic-test-policy"
    return function


@pytest.mark.asyncio
async def test_response_request_id_mismatch_does_not_consume_trace():
    store = capture.CaptureStore()
    await store.begin("expected")
    await store.record("expected", [], {"indexes": []})
    with pytest.raises(ValueError, match="ANSWER_TRACE_REQUEST_MISMATCH"):
        await prediction.bind_response(trace_store=store, request_id="expected", question_id="q",
                                       runtime_question_id="unused", mappings={},
                                       response={"request_id": "different"}, latency_ms=0)
    assert await store.take("expected") == []


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


def test_injected_app_uses_same_guarded_factories_for_sync_and_stream(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from knowflow_ai import app as ai_app
    from knowflow_ai.answering import ReadOnlyRetriever
    from knowflow_ai.config import Settings
    from knowflow_ai.embedding import EmbeddingSettings
    from knowflow_ai.protocol import CONTRACT_VERSION
    wiring = load('wiring')
    ledger_path = tmp_path / 'budget.sqlite3'
    calls = []

    class Embedding:
        settings = SimpleNamespace(model='model-a')
        async def embed(self, texts, *, request_id):
            calls.append(('embed', request_id))
            return {'data': [{'embedding': [1.0] * 1024} for _ in texts]}
        async def aclose(self): pass

    class Llm:
        settings = SimpleNamespace(model='model-a')
        async def generate(self, question, evidence, *, request_id):
            calls.append(('generate', request_id))
            assert len(evidence) == 5
            return {'answer': 'insufficient', 'has_answer': False, 'source_ids': []}
        async def stream_content(self, question, evidence, *, request_id):
            calls.append(('stream', request_id))
            assert len(evidence) == 5
            yield '{"answer":"insufficient","has_answer":false,"source_ids":[]}'
        async def aclose(self): pass

    def fetch(_url, _query, params, _deadline=None, _cancellation=None):
        assert params[-1] == 10
        return [{'document_id': 'd', 'content_version_id': 'c', 'index_version_id': 'i',
                 'text_content': 'a', 'text_sha256': sha256(b'a').hexdigest(),
                 'locator_kind': 'text_range', 'source_start': 0, 'source_end': 1,
                 'source_page': None, 'chunk_id': str(i)} for i in range(10)]

    monkeypatch.setattr(ReadOnlyRetriever, '_fetch_rows', staticmethod(fetch))
    monkeypatch.setattr(EmbeddingSettings, 'from_environment',
                        staticmethod(lambda: EmbeddingSettings(api_key='e' * 40)))
    monkeypatch.setattr(ai_app.LlmSettings, 'from_environment',
                        staticmethod(lambda: SimpleNamespace(model='model-a')))
    common = {'provider': 'synthetic', 'model': 'model-a', 'quote': current_quote(),
              'bound_evidence': current_bound_evidence()}
    secret = 'test-only-' + 'a' * 40
    app = wiring.create_evaluation_app(
        Settings(secret, ai_database_url='postgresql://unused.invalid/db'),
        control_secret='control-' + 'c' * 40,
        ledger=wiring.BudgetLedger(ledger_path),
        embedding={**common, 'adapter_factory': Embedding, 'token_bounds': verified_bounds(lambda *_: (100, 0))},
        llm={**common, 'adapter_factory': Llm, 'token_bounds': verified_bounds(lambda *_: (100, 1024))})
    payload = {'contract_version': CONTRACT_VERSION, 'request_id': 'sync', 'question': 'question?',
               'scope': {'owner_id': 'owner-1', 'knowledge_base_id': 'kb-1', 'snapshot_id': 'snap-1',
                         'indexes': [{'document_id': 'd', 'content_version_id': 'c', 'index_version_id': 'i'}]}}
    headers = {'Authorization': f'Bearer {secret}', 'X-Request-ID': 'sync'}
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        async def index_probe():
            adapter = app.state.index_worker._embedding_factory()
            try: await adapter.embed(['index'], request_id='index')
            finally: await adapter.aclose()
        asyncio.run(index_probe())
        response = client.post('/internal/v1/answers', headers=headers, json=payload)
        assert response.status_code == 200 and response.json()['has_answer'] is False
        capture_url = '/internal/evaluation/results/sync'
        assert client.post(capture_url, headers=headers).status_code == 403
        control_headers = {**headers, 'X-Evaluation-Secret': 'control-' + 'c' * 40}
        captured = client.post(capture_url, headers=control_headers)
        assert captured.status_code == 200
        assert len(captured.json()['trace']) == 10
        assert captured.json()['response']['request_id'] == 'sync'
        citation = captured.json()['citation']
        assert citation['decision'] == 'refused' and citation['reason'] == 'model_declined'
        assert citation['repair_attempt'] == 0
        # The decline now goes through the common eligibility decision, so an
        # unparseable question reports the parser's registered rejection.
        assert citation['repair_gate_reason'] == 'unsupported_question'
        assert set(citation) == {
            'decision', 'reason', 'repairable', 'repair_gate_reason', 'claims',
            'kept_claims', 'uncited_claims',
            'dropped_claims', 'repaired_claims', 'pruned_markers', 'repair_attempt',
            'repair_outcome'}
        assert citation['repair_gate_reason'] in REPAIR_GATE_REASONS
        assert 'insufficient' not in json.dumps(citation)
        assert 'src-evidence' not in json.dumps(citation)
        assert client.post(capture_url, headers=control_headers).status_code == 404
        payload['request_id'] = 'stream'
        response = client.post('/internal/v1/answers/stream', headers={**headers, 'X-Request-ID': 'stream'}, json=payload)
        assert response.status_code == 200 and 'event: completed' in response.text
    assert calls == [('embed', 'index'), ('embed', 'sync'), ('generate', 'sync'),
                     ('embed', 'stream'), ('stream', 'stream')]
    with closing(sqlite3.connect(ledger_path)) as db:
        assert db.execute('SELECT count(*) FROM reservations').fetchone()[0] == 5


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
async def test_guard_forwards_the_citation_reask_after_the_same_reservation(tmp_path):
    path = tmp_path / "budget.sqlite3"
    ledger = budget.BudgetLedger(path)
    calls = []

    def reserved_count():
        with closing(sqlite3.connect(path)) as db:
            return db.execute("SELECT count(*) FROM reservations").fetchone()[0]

    class Adapter:
        settings = SimpleNamespace(model="model-a")

        async def generate(self, question, evidence, *, request_id):
            calls.append(("generate", reserved_count(), evidence[0]["source_id"]))
            return {}

        async def generate_repair(self, question, evidence, previous_answer, *, request_id):
            calls.append(("repair", reserved_count(), previous_answer))
            return {}

        async def aclose(self): pass

    @verified_bounds
    def bounds(operation, *_args):
        return (100, 0 if operation == "embed" else 1024)

    llm = guarded.GuardedLlm(
        adapter_factory=Adapter, ledger=ledger, provider="synthetic", model="model-a",
        quote=current_quote(), token_bounds=bounds, bound_evidence=current_bound_evidence())
    evidence = [{"source_id": "src-1", "text_content": "证据"}]
    await llm.generate("q", evidence, request_id="reask")
    await llm.generate_repair("q", evidence, "上一版答案", request_id="reask")

    assert calls == [("generate", 1, "src-1"), ("repair", 2, "上一版答案")]
    assert evidence == [{"source_id": "src-1", "text_content": "证据"}]
    await llm.aclose()


@pytest.mark.asyncio
async def test_guard_reask_falls_back_for_adapters_without_a_repair_path(tmp_path):
    path = tmp_path / "budget.sqlite3"
    ledger = budget.BudgetLedger(path)
    calls = []

    class LegacyAdapter:
        settings = SimpleNamespace(model="model-a")

        async def generate(self, question, evidence, *, request_id):
            calls.append("generate")
            return {}

        async def aclose(self): pass

    @verified_bounds
    def bounds(operation, *_args):
        return (100, 0 if operation == "embed" else 1024)

    llm = guarded.GuardedLlm(
        adapter_factory=lambda: LegacyAdapter(), ledger=ledger, provider="synthetic",
        model="model-a", quote=current_quote(), token_bounds=bounds,
        bound_evidence=current_bound_evidence())
    await llm.generate_repair("q", [{"source_id": "src-1", "text_content": "证据"}],
                              "上一版答案", request_id="reask")

    assert calls == ["generate"]
    await llm.aclose()


@pytest.mark.asyncio
async def test_guard_rejects_factory_using_a_different_model_before_call(tmp_path):
    path = tmp_path / "budget.sqlite3"
    calls = []
    class WrongModel:
        settings = SimpleNamespace(model="different-model")
        async def embed(self, texts, *, request_id): calls.append("network")
        async def aclose(self): calls.append("closed")
    wiring = load("wiring")
    ledger = wiring.BudgetLedger(path)
    config = {"adapter_factory": lambda: WrongModel(), "provider": "synthetic", "model": "model-a",
              "quote": current_quote(), "token_bounds": verified_bounds(lambda *_: (100, 0)),
              "bound_evidence": current_bound_evidence()}
    factories = wiring.EvaluationFactories(ledger=ledger, embedding=config, llm=config)
    factories.preflight()
    adapter = factories.embedding_factory()
    with pytest.raises(ValueError, match="ADAPTER_MODEL_MISMATCH"):
        await adapter.embed(["a"], request_id="request")
    assert calls == ["closed"]
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT count(*) FROM reservations").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_guard_checks_authoritative_adapter_ledger_path_before_reservation(monkeypatch, tmp_path):
    wiring = load("wiring")
    ledger_path = tmp_path / "ledger.sqlite3"
    monkeypatch.setenv("KNOWFLOW_BUDGET_LEDGER_PATH", str(tmp_path / "different.sqlite3"))
    closed = []
    class ProductAdapter:
        budgeted_provider_adapter = True
        settings = SimpleNamespace(model="model-a")
        async def embed(self, *_args, **_kwargs): pytest.fail("must reject before HTTP")
        async def aclose(self): closed.append(True)

    config = {"adapter_factory": lambda: ProductAdapter(), "provider": "synthetic", "model": "model-a",
              "quote": current_quote(), "token_bounds": verified_bounds(lambda *_: (100, 0)),
              "bound_evidence": current_bound_evidence()}
    factories = wiring.EvaluationFactories(ledger=wiring.BudgetLedger(ledger_path),
                                           embedding=config, llm=config)
    factories.preflight()
    guard = factories.embedding_factory()
    with pytest.raises(ValueError, match="BUDGET_LEDGER_CONFIGURATION_MISMATCH"):
        await guard.embed(["synthetic"], request_id="r")
    assert closed == [True]
    with closing(sqlite3.connect(ledger_path)) as db:
        assert db.execute("SELECT count(*) FROM reservations").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_guard_fails_closed_before_factory_for_unknown_price_or_bound(tmp_path):
    ledger = budget.BudgetLedger(tmp_path / "budget.sqlite3")
    calls = []
    class Adapter:
        settings = SimpleNamespace(model="model-a")
        async def embed(self, *_args, **_kwargs): pass
        async def generate(self, *_args, **_kwargs): pass
        async def stream_content(self, *_args, **_kwargs):
            if False: yield None
        async def aclose(self): pass
    def factory():
        calls.append("factory")
        return Adapter()
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
    assert calls == ["factory"]


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
    class Adapter:
        settings = SimpleNamespace(model="model-a")
        async def embed(self, *_args, **_kwargs): called.append("http")
        async def aclose(self): pass
    adapter = guarded.GuardedEmbedding(adapter_factory=Adapter, ledger=BlockingLedger(),
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
    result = reserve(budget.BudgetLedger(path), "request-1", tokens=8_000_000)
    assert result["remaining_microyuan"] == 2_000_000
    reopened = budget.BudgetLedger(path)
    with pytest.raises(ValueError, match="DUPLICATE_REQUEST_ID"):
        reserve(reopened, "request-1", tokens=1)
    with pytest.raises(ValueError, match="BUDGET_SOFT_STOP"):
        reserve(reopened, "retry-2", tokens=1_000_001)
    with pytest.raises(ValueError, match="BUDGET_SOFT_STOP"):
        reserve(reopened, "retry-3")
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
    assert sorted(results) == ["BUDGET_SOFT_STOP", "reserved", "reserved"]


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
    assert mapping.normalize_question_id("550E8400-E29B-41D4-A716-446655440000") == "550e8400-e29b-41d4-a716-446655440000"


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


def _prediction_fixture():
    question_id = "550e8400-e29b-41d4-a716-446655440000"
    key = ("runtime-document", "runtime-content", "runtime-index")
    source = "evidence text".encode("utf-8")
    entry = {"dataset_document_id": "dataset-doc", "dataset_content_version_id": "dataset-version",
             "source_bytes": source, "source_sha256": sha256(source).hexdigest()}
    rows = [{
        "document_id": key[0], "content_version_id": key[1], "index_version_id": key[2],
        "source_id": f"src-{index}", "locator": {
            "kind": "text_range", "unit": "unicode_code_point", "start": 0, "end": 8},
        "text_sha256": sha256(source[:8]).hexdigest(),
    } for index in range(6)]
    mappings = {key: entry}
    scope = {"indexes": [{"document_id": key[0], "content_version_id": key[1],
                          "index_version_id": key[2]}]}
    return question_id, rows, mappings, scope


@pytest.mark.parametrize("answer", [
    "索引就绪[src-a.v1][src-b]。",
    "索引就绪[550e8400-e29b-41d4-a716-446655440000][src-b]。",
])
def test_collector_claim_keeps_dotted_and_uuid_parallel_markers_in_one_unit(answer):
    markers = list(prediction._MARKER.finditer(answer))

    assert len(markers) == 2
    assert [prediction._claim(answer, marker.start(), marker.end()) for marker in markers] == [
        answer, answer]


def test_collector_claim_keeps_decimal_numbers_inside_the_claim():
    answer = "任务上限为 1.5 MB[src-a.v1]。"
    marker = prediction._MARKER.search(answer)

    assert prediction._claim(answer, marker.start(), marker.end()) == answer


@pytest.mark.parametrize("answer, expected", [
    ("甲公司2023年净利润为18亿元。[src-a.v1]", "甲公司2023年净利润为18亿元。[src-a.v1]"),
    ("甲公司2023年净利润为18亿元。 [src-a.v1]", "甲公司2023年净利润为18亿元。 [src-a.v1]"),
    ("第一句。第二句。[src-a.v1]", "第二句。[src-a.v1]"),
    ("第一句。[src-a.v1]第二句。", "第一句。[src-a.v1]"),
])
def test_collector_claim_keeps_annotated_sentence_when_marker_follows_boundary(answer, expected):
    marker = prediction._MARKER.search(answer)

    assert marker is not None
    assert prediction._claim(answer, marker.start(), marker.end()) == expected


@pytest.mark.parametrize("answer", [
    "请访问 https://docs.example.test/start[src-a.v1]。",
    "联系 help@example.test[src-a.v1]。",
])
def test_collector_claim_keeps_url_and_email_inside_the_claim(answer):
    marker = prediction._MARKER.search(answer)

    assert marker is not None
    assert prediction._claim(answer, marker.start(), marker.end()) == answer


@pytest.mark.asyncio
async def test_prediction_binds_single_trace_remaps_every_citation_occurrence(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "runner_v2_test", ROOT / "evaluation" / "runner" / "runner_v2.py")
    runner_v2 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner_v2)

    question_id, rows, mappings, scope = _prediction_fixture()
    wiring = load("wiring")
    factories = wiring.EvaluationFactories(
        ledger=wiring.BudgetLedger(tmp_path / "prediction-ledger.sqlite3"), embedding={}, llm={})
    store = factories.traces
    await store.begin("req-answer")
    await store.record("req-answer", rows, scope)
    response = {
        "request_id": "req-answer", "answer": "事实[src-0]成立，再由[src-4]佐证[src-0]。",
        "has_answer": True,
        "sources": [{
            "source_id": source_id, "document_id": rows[index]["document_id"],
            "content_version_id": rows[index]["content_version_id"],
            "index_version_id": rows[index]["index_version_id"],
            "locator": rows[index]["locator"],
        } for index, source_id in ((0, "src-0"), (4, "src-4"))],
    }

    result = await factories.prediction_from_response(
        request_id="req-answer", question_id=question_id,
        runtime_question_id=question_id, mappings=mappings,
        response=response, latency_ms=123.5)

    public_ids = [mapping.public_source_id(question_id, "src-0"),
                  mapping.public_source_id(question_id, "src-4")]
    assert result["outcome"] == "answered"
    assert result["answer"].count("[" + public_ids[0] + "]") == 2
    assert result["answer"].count("[" + public_ids[1] + "]") == 1
    assert result["answer_sha256"] == sha256(result["answer"].encode()).hexdigest()
    assert [cite["marker_index"] for cite in result["citations"]] == [0, 1, 2]
    assert [cite["evidence_index"] for cite in result["citations"]] == [0, 4, 0]
    assert [(cite["source_id"], cite["evidence_index"]) for cite in result["citations"]] == [
        (public_ids[0], 0), (public_ids[1], 4), (public_ids[0], 0)]
    assert runner_v2.SOURCE_ID.fullmatch(public_ids[0])
    assert runner_v2.MARKER.findall(result["answer"]) == [public_ids[0], public_ids[1], public_ids[0]]
    assert set(result) == {
        "question_id", "outcome", "answer", "answer_sha256", "retrieved_evidence",
        "citations", "latency_ms", "error_code",
    }
    with pytest.raises(ValueError, match="TRACE_NOT_AVAILABLE"):
        await store.take("req-answer")


@pytest.mark.parametrize("answer", ["测试结论[src-0]。", "The emoji range is [2,3). [src-0]", "括号文本 [中文]、[bad marker] 与右括号 ]。[src-0]"])
def test_collected_citation_claim_passes_runner_v2_score_entry(tmp_path, answer):
    spec = importlib.util.spec_from_file_location(
        "runner_v2_claim_test", ROOT / "evaluation" / "runner" / "runner_v2.py")
    runner_v2 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner_v2)
    dataset_root = ROOT / "evaluation" / "data" / "seed-v2-reviewed"
    manifest, questions, _documents, sources, dataset_sha = runner_v2.legacy._load_dataset(
        dataset_root)
    question = next(item for item in questions
                    if item["split"] == "development" and item["answerable"] and item["evidence"])
    gold = question["evidence"][0]
    runtime = ("runtime-document", "runtime-content", "runtime-index")
    source = sources[gold["document_id"]].encode("utf-8")
    locator = {"kind": "text_range", "unit": "unicode_code_point",
               "start": gold["start"], "end": gold["end"]}
    span_sha256 = sha256(sources[gold["document_id"]][gold["start"]:gold["end"]]
                         .encode("utf-8")).hexdigest()
    trace = [{"document_id": runtime[0], "content_version_id": runtime[1],
              "index_version_id": runtime[2], "source_id": "src-0", "locator": locator,
              "text_sha256": span_sha256}]
    result = prediction.answer_prediction(
        question_id=question["id"],
        runtime_question_id="550e8400-e29b-41d4-a716-446655440000", trace=trace,
        mappings={runtime: {"dataset_document_id": gold["document_id"],
                            "dataset_content_version_id": gold["content_version_id"],
                            "source_bytes": source,
                            "source_sha256": sha256(source).hexdigest()}},
        response={"request_id": "req-runner-v2", "answer": answer,
                  "has_answer": True,
                  "sources": [{"source_id": "src-0", "document_id": runtime[0],
                               "content_version_id": runtime[1], "index_version_id": runtime[2],
                               "locator": locator}]},
        latency_ms=1)
    public_id = result["citations"][0]["source_id"]
    assert result["answer"] == answer.replace("[src-0]", f"[{public_id}]")
    assert len(result["citations"]) == 1
    rows = [{"question_id": item["id"], "outcome": "refused", "answer": "资料不足",
             "answer_sha256": sha256("资料不足".encode("utf-8")).hexdigest(),
             "retrieved_evidence": [], "citations": [], "latency_ms": 0,
             "error_code": None} for item in questions if item["split"] == "development"]
    rows = [result if item["question_id"] == question["id"] else item for item in rows]
    payload = {"prediction_version": 2, "dataset_id": manifest["dataset_id"],
               "dataset_sha256": dataset_sha,
               "run": {"code_sha": "a" * 40, "schema_sha256": "b" * 64,
                       "model": "fixture", "config_sha256": "c" * 64,
                       "prompt_sha256": "d" * 64},
               "predictions": rows}
    predictions_path = tmp_path / "runner-v2-claim-predictions.json"
    predictions_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    report = runner_v2.evaluate(predictions_path, split="development", dataset_root=dataset_root)

    assert report["sample_count"] == sum(item["split"] == "development" for item in questions)
    assert report["quality_gate"]["status"] == "incomplete"


@pytest.mark.asyncio
async def test_prediction_rejects_citation_outside_generation_top5_and_request_mismatch():
    question_id, rows, mappings, scope = _prediction_fixture()
    store = capture.CaptureStore()
    await store.begin("req-rank")
    await store.record("req-rank", rows, scope)
    response = {
        "request_id": "req-rank", "answer": "事实[src-5]成立。",
        "has_answer": True,
        "sources": [{"source_id": "src-5", "document_id": rows[5]["document_id"],
                     "content_version_id": rows[5]["content_version_id"],
                     "index_version_id": rows[5]["index_version_id"],
                     "locator": rows[5]["locator"]}],
    }
    with pytest.raises(ValueError, match="CITATION_OUTSIDE_TOP5"):
        await prediction.bind_response(
            trace_store=store, request_id="req-rank", question_id=question_id,
            runtime_question_id=question_id, mappings=mappings,
            response=response, latency_ms=10)

    await store.begin("req-wrong")
    await store.record("req-wrong", rows, scope)
    with pytest.raises(ValueError, match="ANSWER_TRACE_REQUEST_MISMATCH"):
        await prediction.bind_response(
            trace_store=store, request_id="req-wrong", question_id=question_id,
            runtime_question_id=question_id, mappings=mappings,
            response={**response, "request_id": "other"},
            latency_ms=10)
    assert len(await store.take("req-wrong")) == len(rows)


@pytest.mark.asyncio
async def test_prediction_distinguishes_refusal_from_error_and_requires_trace(tmp_path):
    question_id, _rows, mappings, scope = _prediction_fixture()
    wiring = load("wiring")
    factories = wiring.EvaluationFactories(
        ledger=wiring.BudgetLedger(tmp_path / "prediction-ledger.sqlite3"), embedding={}, llm={})
    store = factories.traces
    await store.begin("req-refused")
    await store.record("req-refused", [], scope)
    refused = await factories.prediction_from_response(
        request_id="req-refused", question_id=question_id,
        runtime_question_id=question_id, mappings=mappings,
        response={"request_id": "req-refused", "answer": "没有足够证据。",
                  "has_answer": False, "sources": []},
        latency_ms=8)
    assert refused["outcome"] == "refused" and refused["error_code"] is None

    await store.begin("req-error")
    await store.record("req-error", [], scope)
    error = await factories.prediction_from_error(
        request_id="req-error", question_id=question_id, runtime_question_id=question_id,
        mappings=mappings, error_code="MODEL_TIMEOUT", latency_ms=30)
    assert error["outcome"] == "error" and error["answer"] == ""
    assert error["citations"] == [] and error["error_code"] == "MODEL_TIMEOUT"
    with pytest.raises(ValueError, match="INVALID_QUESTION_ID"):
        prediction.answer_prediction(
            question_id=question_id, runtime_question_id="dataset-question-id", trace=[],
            mappings={}, response={"request_id": "req-invalid-runtime", "answer": "资料不足",
                                  "has_answer": False, "sources": []},
            latency_ms=1)
    with pytest.raises(ValueError, match="TRACE_NOT_AVAILABLE"):
        await factories.prediction_from_error(
            request_id="missing", question_id=question_id, runtime_question_id=question_id,
            mappings=mappings, error_code="MODEL_TIMEOUT", latency_ms=30)


def test_verified_zero_price_embedding_is_persisted_deduplicated_and_not_budget_exempt(tmp_path):
    path = tmp_path / "zero-budget.sqlite3"
    ledger = budget.BudgetLedger(path, limit_microyuan=1)
    quote = {"provider": "siliconflow", "model": "BAAI/bge-m3",
             "input_cny_per_million": "0", "output_cny_per_million": "0",
             "source_url": "https://siliconflow.cn/pricing", "verified_by": "reviewer",
             "verified_at": "2026-11-01T00:00:00Z", "valid_until": "2026-11-03T00:00:00Z"}
    arguments = {"provider": "siliconflow", "model": "BAAI/bge-m3",
                 "input_tokens_upper": 100, "output_tokens_upper": 0, "quote": quote, "now": NOW}

    with pytest.raises(ValueError, match="UNVERIFIED_PRICE"):
        ledger.reserve("free-embedding", **arguments)
    with pytest.raises(ValueError, match="UNVERIFIED_PRICE"):
        ledger.reserve("misused-zero-embedding", **{
            **arguments, "provider": "deepseek", "model": "deepseek-flash",
            "quote": {**quote, "provider": "deepseek", "model": "deepseek-flash",
                      "input_cny_per_million": "0", "output_cny_per_million": "8",
                      "source_url": "https://api-docs.deepseek.com/pricing"},
            "output_tokens_upper": 1024,
        }, allow_zero_price_embedding=True)
    result = ledger.reserve("free-embedding", **arguments, allow_zero_price_embedding=True)
    assert result == {"reserved_microyuan": 0, "total_reserved_microyuan": 0,
                      "remaining_microyuan": 1}

    reopened = budget.BudgetLedger(path, limit_microyuan=1)
    with pytest.raises(ValueError, match="DUPLICATE_REQUEST_ID"):
        reopened.reserve("free-embedding", **arguments, allow_zero_price_embedding=True)
    with pytest.raises(ValueError, match="DUPLICATE_REQUEST_ID"):
        reserve(reopened, "free-embedding", tokens=1)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT count(*) FROM zero_price_reservations").fetchone()[0] == 1
        assert db.execute("SELECT COALESCE(SUM(microyuan), 0) FROM reservations").fetchone()[0] == 0

    reserve(reopened, "paid-embedding", tokens=1)
    assert reopened.summary() == {
        "limit_microyuan": 1, "reserved_microyuan": 1, "remaining_microyuan": 0,
        "paid_reservations": 1, "zero_price_reservations": 1,
    }
    with pytest.raises(ValueError, match="BUDGET_EXCEEDED"):
        reserve(reopened, "over-limit", tokens=1)


@pytest.mark.asyncio
async def test_zero_price_quote_is_enabled_only_for_embedding_guard(tmp_path):
    ledger = budget.BudgetLedger(tmp_path / "guard-zero.sqlite3")
    now = datetime.now(timezone.utc)
    quote = {"provider": "siliconflow", "model": "BAAI/bge-m3",
             "input_cny_per_million": "0", "output_cny_per_million": "0",
             "source_url": "https://siliconflow.cn/pricing", "verified_by": "reviewer",
             "verified_at": (now - timedelta(minutes=1)).isoformat(),
             "valid_until": (now + timedelta(minutes=1)).isoformat()}
    evidence = {key: quote[key] for key in ("provider", "model", "source_url", "verified_by",
                                             "verified_at", "valid_until")}
    evidence["policy_id"] = "synthetic-test-policy"
    bounds = verified_bounds(lambda *_: (100, 0))
    calls = []

    class SyntheticEmbedding:
        settings = SimpleNamespace(model="BAAI/bge-m3")
        async def embed(self, texts, *, request_id):
            calls.append(("embed", request_id))
            return {"data": [{"embedding": [1.0]} for _ in texts]}
        async def aclose(self): pass

    embedding = guarded.GuardedEmbedding(
        adapter_factory=SyntheticEmbedding, ledger=ledger, provider="siliconflow",
        model="BAAI/bge-m3", quote=quote, token_bounds=bounds, bound_evidence=evidence)
    await embedding.embed(["synthetic"], request_id="synthetic-embedding")
    await embedding.aclose()
    assert calls == [("embed", "synthetic-embedding")]

    llm_quote = {**quote, "provider": "deepseek", "model": "deepseek-flash",
                 "source_url": "https://deepseek.com/pricing"}
    llm_evidence = {key: llm_quote[key] for key in ("provider", "model", "source_url", "verified_by",
                                                    "verified_at", "valid_until")}
    llm_evidence["policy_id"] = "synthetic-test-policy"
    class UnusedLlm:
        settings = SimpleNamespace(model="deepseek-flash")
        async def generate(self, *_args, **_kwargs): pass
        async def stream_content(self, *_args, **_kwargs):
            if False: yield None
        async def aclose(self): pass
    llm = guarded.GuardedLlm(
        adapter_factory=UnusedLlm,
        ledger=ledger, provider="deepseek", model="deepseek-flash", quote=llm_quote,
        token_bounds=verified_bounds(lambda *_: (100, 1024)), bound_evidence=llm_evidence)
    with pytest.raises(ValueError, match="UNVERIFIED_PRICE"):
        await llm.generate("synthetic", [], request_id="synthetic-llm")
    with closing(sqlite3.connect(ledger.path)) as db:
        assert db.execute("SELECT count(*) FROM zero_price_reservations").fetchone()[0] == 1
