import asyncio
import json
from pathlib import Path
import re
import socket
import struct
import threading
import time

import httpx
import psycopg
import pytest

from knowflow_ai.adapters import ProcessingError
from knowflow_ai.answering import (
    AnswerService,
    DeepSeekAdapter,
    LlmSettings,
    ReadOnlyRetriever,
    _has_question_content_overlap,
    answer_repair_enabled,
)
from knowflow_ai.citation_verify import (
    _claim_units,
    citations_are_grounded,
    prune_claims,
    prune_ungrounded_claims,
)
from knowflow_ai.config import ConfigurationError
from knowflow_ai.embedding import EmbeddingSettings, SiliconFlowEmbeddingAdapter
from knowflow_ai.protocol import CONTRACT_VERSION, ContractConsumer, InvalidMessage


ROOT = Path(__file__).resolve().parents[3]
KEY = "synthetic-deepseek-key-" + "x" * 32
EMBEDDING_KEY = "synthetic-embedding-key-" + "x" * 32


class FakeRetriever:
    def __init__(self, rows):
        self.rows = rows

    async def retrieve(self, question, scope, request_id, *, deadline=None):
        return self.rows


class FakeLlm:
    def __init__(self, result):
        self.result = result

    async def generate(self, question, evidence, *, request_id):
        return self.result

    async def aclose(self):
        return None


def _request():
    return {"contract_version": CONTRACT_VERSION, "request_id": "answer-test-01",
            "question": "索引何时可检索？", "scope": {
                "owner_id": "user-example-a", "knowledge_base_id": "kb-example-a",
                "snapshot_id": "snapshot-example-1", "indexes": [{
                    "document_id": "doc-example-1", "content_version_id": "content-example-1",
                    "index_version_id": "index-example-1"}]}}


def _evidence():
    return [{"source_id": "src-evidence-1", "document_id": "doc-example-1",
             "content_version_id": "content-example-1", "index_version_id": "index-example-1",
             "chunk_id": "chunk-example-1", "text_content": "原始资料说明索引 READY 后才可检索。",
             "locator": {"kind": "text_range", "start": 12, "end": 32,
                         "unit": "unicode_code_point"}}]


def _contract():
    return ContractConsumer(ROOT / "contracts/schemas/protocol.schema.json")


def _contract_rejecting_answer(answer):
    contract = _contract()
    validate = contract.validate

    def reject_matching_answer(definition, payload):
        if definition == "AnswerResponse" and payload.get("answer") == answer:
            raise InvalidMessage("INVALID_MESSAGE")
        return validate(definition, payload)

    contract.validate = reject_matching_answer
    return contract


def _pg_message(tag, payload=b""):
    return tag + struct.pack("!I", len(payload) + 4) + payload


def _pg_row_description(name, type_oid):
    column = (name.encode() + b"\0" + struct.pack("!IhIhih", 0, 0, type_oid,
                                                   4 if type_oid == 23 else -1, -1, 0))
    return _pg_message(b"T", struct.pack("!H", 1) + column)


class _PostgresBlackhole:
    """Tiny PostgreSQL protocol peer that hangs on the retrieval query."""

    def __init__(self):
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen()
        self.listener.settimeout(0.1)
        self.url = (f"postgresql://readonly:secret@127.0.0.1:{self.listener.getsockname()[1]}"
                    "/test?sslmode=disable")
        self.query_started = threading.Event()
        self.disconnected = threading.Event()
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    @staticmethod
    def _read_exact(connection, size):
        value = bytearray()
        while len(value) < size:
            part = connection.recv(size - len(value))
            if not part:
                return None
            value.extend(part)
        return bytes(value)

    @classmethod
    def _read_message(cls, connection):
        header = cls._read_exact(connection, 5)
        if header is None:
            return None, None
        tag = header[:1]
        length = struct.unpack("!I", header[1:])[0]
        body = cls._read_exact(connection, length - 4)
        return (tag, body) if body is not None else (None, None)

    @staticmethod
    def _ready(connection, status=b"I"):
        connection.sendall(_pg_message(b"Z", status))

    def _startup(self, connection):
        header = self._read_exact(connection, 4)
        if header is None:
            return False
        length = struct.unpack("!I", header)[0]
        body = self._read_exact(connection, length - 4)
        if body is None:
            return False
        if body[:4] == struct.pack("!I", 80877103):
            connection.sendall(b"N")
            header = self._read_exact(connection, 4)
            if header is None:
                return False
            length = struct.unpack("!I", header)[0]
            if self._read_exact(connection, length - 4) is None:
                return False
        startup = [_pg_message(b"R", struct.pack("!I", 0))]
        for key, value in ((b"server_version", b"16.0"),
                           (b"client_encoding", b"UTF8"),
                           (b"standard_conforming_strings", b"on")):
            startup.append(_pg_message(b"S", key + b"\0" + value + b"\0"))
        startup.extend((_pg_message(b"K", struct.pack("!II", 1, 1)),
                        _pg_message(b"Z", b"I")))
        connection.sendall(b"".join(startup))
        return True

    def _serve(self):
        connection = None
        try:
            connection, _ = self.listener.accept()
            connection.settimeout(0.1)
            if not self._startup(connection):
                return
            query = b""
            in_transaction = False
            while not self.stopped.is_set():
                try:
                    tag, body = self._read_message(connection)
                except TimeoutError:
                    continue
                if tag is None:
                    self.disconnected.set()
                    return
                if tag == b"P":
                    _, query, _ = body.split(b"\0", 2)
                    connection.sendall(_pg_message(b"1"))
                elif tag == b"B":
                    connection.sendall(_pg_message(b"2"))
                elif tag == b"D" and b"set_config" in query:
                    connection.sendall(_pg_row_description("set_config", 25))
                elif tag == b"E":
                    if b"set_config" not in query:
                        self.query_started.set()
                        while not self.stopped.is_set():
                            try:
                                if not connection.recv(1):
                                    self.disconnected.set()
                                    return
                            except TimeoutError:
                                continue
                    else:
                        value = b"5000ms"
                        row = struct.pack("!Hi", 1, len(value)) + value
                        connection.sendall(_pg_message(b"D", row)
                                           + _pg_message(b"C", b"SELECT 1\0"))
                elif tag == b"S":
                    self._ready(connection, b"T" if in_transaction else b"I")
                elif tag == b"Q":
                    query = body.rstrip(b"\0")
                    if query.strip().upper() == b"BEGIN":
                        in_transaction = True
                        connection.sendall(_pg_message(b"C", b"BEGIN\0"))
                        self._ready(connection, b"T")
                    elif b"set_config" not in query:
                        self.query_started.set()
                        while not self.stopped.is_set():
                            try:
                                if not connection.recv(1):
                                    self.disconnected.set()
                                    return
                            except TimeoutError:
                                continue
                    else:
                        value = b"5000ms"
                        row = struct.pack("!Hi", 1, len(value)) + value
                        connection.sendall(_pg_row_description("set_config", 25)
                                           + _pg_message(b"D", row)
                                           + _pg_message(b"C", b"SELECT 1\0"))
                        self._ready(connection, b"T" if in_transaction else b"I")
        except OSError:
            if not self.stopped.is_set():
                raise
        finally:
            if connection is not None:
                connection.close()
            self.disconnected.set()
            self.listener.close()

    def close(self):
        self.stopped.set()
        self.listener.close()
        self.thread.join(timeout=1)


@pytest.mark.asyncio
async def test_read_only_database_query_runs_in_a_worker_thread(monkeypatch):
    query_rows = [{
        "chunk_id": "chunk-example-1",
        "document_id": "doc-example-1",
        "content_version_id": "content-example-1",
        "index_version_id": "index-example-1",
        "text_content": "verified source text",
        "text_sha256": "0" * 64,
        "locator_kind": "text_range",
        "source_page": None,
        "source_start": 0,
        "source_end": 20,
        "distance": 0.0,
    }]
    calls = {}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, query, params):
            calls["query"] = query
            calls["params"] = params

        def fetchall(self):
            calls["thread_id"] = threading.get_ident()
            return query_rows

    class FakeConnection:
        def set_request_control(self, _cancellation, _deadline):
            return None

        def close(self):
            return None

        def cursor(self, *, row_factory):
            return FakeCursor()

    def connect(database_url, *, options, connect_timeout):
        calls["database_url"] = database_url
        calls["options"] = options
        calls["connect_timeout"] = connect_timeout
        calls["row_factory"] = psycopg.rows.dict_row
        return FakeConnection()

    import knowflow_ai.answering as answering
    monkeypatch.setattr(answering._CancellableConnection, "connect", staticmethod(connect))

    class FakeEmbedding:
        async def embed(self, texts, *, request_id):
            return {"data": [{"embedding": [0.125] * 1024}]}

        async def aclose(self):
            return None

    main_thread_id = threading.get_ident()
    retriever = ReadOnlyRetriever(
        "postgresql://readonly.invalid/db", embedding_factory=FakeEmbedding,
        embedding_settings=EmbeddingSettings(api_key=EMBEDDING_KEY))
    evidence = await retriever.retrieve("question", {
        "owner_id": "user-example-a",
        "knowledge_base_id": "kb-example-a",
        "indexes": [{
            "document_id": "doc-example-1",
            "content_version_id": "content-example-1",
            "index_version_id": "index-example-1",
        }],
    }, "answer-test-01")

    assert calls["thread_id"] != main_thread_id
    assert calls["options"] == (
        "-c default_transaction_read_only=on -c statement_timeout=5000")
    assert calls["connect_timeout"] == 5
    assert "iv.status IN ('READY', 'RETIRED')" in calls["query"]
    assert "iv.cleaned_at IS NULL" in calls["query"]
    assert "d.active_index_version_id = c.index_version_id" not in calls["query"]
    assert "d.current_content_version_id = c.content_version_id" not in calls["query"]
    assert "kb.status = 'ACTIVE'" in calls["query"]
    assert "d.status = 'ACTIVE'" in calls["query"]
    assert evidence[0]["text_content"] == "verified source text"
    assert evidence[0]["locator"]["unit"] == "unicode_code_point"


@pytest.mark.parametrize("length", [800, 801, 16000])
@pytest.mark.asyncio
async def test_answer_service_accepts_questions_up_to_shared_contract_limit(length):
    service = AnswerService("unused", _contract(), retriever=FakeRetriever([]))
    request = _request()
    request["question"] = "问" * length

    response = await service.answer(request)

    assert response["has_answer"] is False


@pytest.mark.asyncio
async def test_answer_service_leaves_over_limit_rejection_to_shared_contract():
    service = AnswerService("unused", _contract(), retriever=FakeRetriever([]))
    request = _request()
    request["question"] = "问" * 16001

    with pytest.raises(InvalidMessage):
        await service.answer(request)


@pytest.mark.parametrize("stage", ["retrieve", "generate"])
@pytest.mark.asyncio
async def test_answer_deadline_cancels_every_stage_and_closes_model(monkeypatch, stage):
    from knowflow_ai import answering

    monkeypatch.setattr(answering, "ANSWER_DEADLINE_SECONDS", 0.01)
    cancelled = asyncio.Event()

    class SlowRetriever:
        async def retrieve(self, question, scope, request_id, *, deadline=None):
            if stage == "retrieve":
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()
            return _evidence()

    class SlowLlm:
        async def generate(self, question, evidence, *, request_id):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        async def aclose(self):
            closed.set()

    closed = asyncio.Event()
    service = AnswerService("unused", _contract(), llm_factory=SlowLlm,
                            retriever=SlowRetriever())

    with pytest.raises(ProcessingError, match="PROCESSING_TIMEOUT"):
        await service.answer(_request())

    assert cancelled.is_set()
    assert closed.is_set() is (stage == "generate")


@pytest.mark.asyncio
async def test_database_statement_timeout_uses_remaining_answer_deadline(monkeypatch):
    from knowflow_ai import answering

    deadline = time.monotonic() + 2.5
    captured = {}

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, query, params):
            if query.startswith("SELECT set_config"):
                captured["statement_timeout"] = int(params[0][:-2])
                captured["configured_at"] = time.monotonic()
            elif captured.get("cancel_query"):
                raise psycopg.errors.QueryCanceled("statement timeout")

        def fetchall(self):
            return []

    class FakeConnection:
        def set_request_control(self, _cancellation, _deadline):
            time.sleep(0.02)

        def close(self):
            captured["closed"] = True

        def cursor(self, *, row_factory):
            return FakeCursor()

    def connect(database_url, *, options, connect_timeout):
        captured["options"] = options
        captured["connect_timeout"] = connect_timeout
        return FakeConnection()

    monkeypatch.setattr(answering._CancellableConnection, "connect", staticmethod(connect))

    rows = ReadOnlyRetriever._fetch_rows("postgresql://readonly.invalid/db",
                                         "SELECT 1", [], deadline)

    assert rows == []
    assert captured["options"].startswith(
        "-c default_transaction_read_only=on -c statement_timeout=")
    assert captured["connect_timeout"] == 2
    initial_timeout = int(captured["options"].rsplit("=", 1)[1])
    assert 0 < initial_timeout <= 500
    remaining_ms = int((deadline - captured["configured_at"]) * 1000)
    assert 0 < captured["statement_timeout"] <= min(5000, remaining_ms)
    assert captured["closed"] is True

    captured["cancel_query"] = True
    captured["closed"] = False
    with pytest.raises(psycopg.errors.QueryCanceled):
        ReadOnlyRetriever._fetch_rows("postgresql://readonly.invalid/db",
                                      "SELECT 1", [], time.monotonic() + 2.5)
    assert captured["closed"] is True


@pytest.mark.parametrize("cancel_twice", [False, True])
@pytest.mark.asyncio
async def test_cancelling_retrieval_closes_unresponsive_database_socket(
        monkeypatch, cancel_twice):
    from knowflow_ai import answering

    server = _PostgresBlackhole()
    cancellation_seen = threading.Event()
    database_thread_finished = threading.Event()
    original_cancel = answering._DatabaseCancellation.cancel
    original_fetch = ReadOnlyRetriever._fetch_rows

    def tracked_cancel(cancellation):
        original_cancel(cancellation)
        cancellation_seen.set()

    def tracked_fetch(*args, **kwargs):
        try:
            return original_fetch(*args, **kwargs)
        finally:
            database_thread_finished.set()

    monkeypatch.setattr(answering._DatabaseCancellation, "cancel", tracked_cancel)
    monkeypatch.setattr(ReadOnlyRetriever, "_fetch_rows", staticmethod(tracked_fetch))
    class FakeEmbedding:
        async def embed(self, texts, *, request_id):
            return {"data": [{"embedding": [0.125] * 1024} for _ in texts]}

        async def aclose(self):
            return None

    retriever = ReadOnlyRetriever(
        server.url, embedding_factory=FakeEmbedding,
        embedding_settings=EmbeddingSettings(api_key=EMBEDDING_KEY))
    task = asyncio.create_task(retriever.retrieve("question", {
        "owner_id": "user-example-a", "knowledge_base_id": "kb-example-a",
        "indexes": [{"document_id": "doc-example-1",
                     "content_version_id": "content-example-1",
                     "index_version_id": "index-example-1"}],
    }, "answer-test-01", deadline=time.monotonic() + 10))
    try:
        assert await asyncio.to_thread(server.query_started.wait, 2)
        task.cancel()
        assert await asyncio.to_thread(cancellation_seen.wait, 1)
        if cancel_twice:
            task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=2)

        assert await asyncio.to_thread(database_thread_finished.wait, 1)
        assert await asyncio.to_thread(server.disconnected.wait, 1)
    finally:
        server.close()


@pytest.mark.asyncio
async def test_cancellation_during_database_connect_closes_before_query(monkeypatch):
    from knowflow_ai import answering

    connect_started = threading.Event()
    allow_connect = threading.Event()
    cancellation_seen = threading.Event()
    connection_closed = threading.Event()
    executed = []
    original_cancel = answering._DatabaseCancellation.cancel

    def tracked_cancel(cancellation):
        original_cancel(cancellation)
        cancellation_seen.set()

    class FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, query, params):
            executed.append(query)

    class FakeConnection:
        def set_request_control(self, _cancellation, _deadline):
            return None

        def cursor(self, *, row_factory):
            return FakeCursor()

        def close(self):
            connection_closed.set()

    def connect(*_args, **_kwargs):
        connect_started.set()
        if not allow_connect.wait(timeout=2):
            raise AssertionError("test did not release connection setup")
        return FakeConnection()

    monkeypatch.setattr(answering._DatabaseCancellation, "cancel", tracked_cancel)
    monkeypatch.setattr(answering._CancellableConnection, "connect", staticmethod(connect))

    class FakeEmbedding:
        async def embed(self, texts, *, request_id):
            return {"data": [{"embedding": [0.125] * 1024} for _ in texts]}

        async def aclose(self):
            return None

    retriever = ReadOnlyRetriever(
        "postgresql://readonly.invalid/db", embedding_factory=FakeEmbedding,
        embedding_settings=EmbeddingSettings(api_key=EMBEDDING_KEY))
    task = asyncio.create_task(retriever.retrieve("question", {
        "owner_id": "user-example-a", "knowledge_base_id": "kb-example-a",
        "indexes": [{"document_id": "doc-example-1",
                     "content_version_id": "content-example-1",
                     "index_version_id": "index-example-1"}],
    }, "answer-test-01", deadline=time.monotonic() + 10))

    assert await asyncio.to_thread(connect_started.wait, 1)
    task.cancel()
    assert await asyncio.to_thread(cancellation_seen.wait, 1)
    allow_connect.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=1)

    assert executed == []
    assert connection_closed.is_set()


@pytest.mark.asyncio
async def test_database_deadline_closes_an_unresponsive_connected_socket(monkeypatch):
    server = _PostgresBlackhole()

    class FakeEmbedding:
        async def embed(self, texts, *, request_id):
            return {"data": [{"embedding": [0.125] * 1024} for _ in texts]}

        async def aclose(self):
            return None

    retriever = ReadOnlyRetriever(
        server.url, embedding_factory=FakeEmbedding,
        embedding_settings=EmbeddingSettings(api_key=EMBEDDING_KEY))
    database_thread_finished = threading.Event()
    original_fetch = ReadOnlyRetriever._fetch_rows

    def tracked_fetch(*args, **kwargs):
        try:
            return original_fetch(*args, **kwargs)
        finally:
            database_thread_finished.set()

    monkeypatch.setattr(ReadOnlyRetriever, "_fetch_rows", staticmethod(tracked_fetch))
    started = time.monotonic()
    try:
        with pytest.raises(ProcessingError, match="PROCESSING_TIMEOUT"):
            await asyncio.wait_for(retriever.retrieve("question", {
                "owner_id": "user-example-a", "knowledge_base_id": "kb-example-a",
                "indexes": [{"document_id": "doc-example-1",
                             "content_version_id": "content-example-1",
                             "index_version_id": "index-example-1"}],
            }, "answer-test-01", deadline=started + 1.2), timeout=2)

        elapsed = time.monotonic() - started
        assert elapsed <= 1.8
        assert server.query_started.is_set()
        assert await asyncio.to_thread(database_thread_finished.wait, 1)
        assert await asyncio.to_thread(server.disconnected.wait, 1)
    finally:
        server.close()


@pytest.mark.asyncio
async def test_retriever_batches_full_question_and_combines_vectors_by_segment_length(monkeypatch):
    embedded_batches = []
    vectors = iter([1.0, 3.0, 5.0, 7.0])

    class FakeEmbedding:
        async def embed(self, texts, *, request_id):
            embedded_batches.append(texts)
            return {"data": [{"embedding": [next(vectors)] * 1024} for _ in texts]}

        async def aclose(self):
            return None

    captured = {}
    def fetch_rows(_url, query, params, _deadline=None, _cancellation=None):
        captured["query"] = query
        captured["params"] = params
        return []

    monkeypatch.setattr(ReadOnlyRetriever, "_fetch_rows", staticmethod(fetch_rows))
    settings = EmbeddingSettings(api_key=EMBEDDING_KEY, max_text_codepoints=3,
                                 max_batch_items=2)
    retriever = ReadOnlyRetriever("postgresql://readonly.invalid/db",
                                  embedding_factory=FakeEmbedding,
                                  embedding_settings=settings)

    rows = await retriever.retrieve("abcdefghij", {
        "owner_id": "user-example-a", "knowledge_base_id": "kb-example-a",
        "indexes": [{"document_id": "doc-example-1",
                     "content_version_id": "content-example-1",
                     "index_version_id": "index-example-1"}],
    }, "answer-test-01", top_k=10)

    assert rows == []
    assert embedded_batches == [["abc", "def"], ["ghi", "j"]]
    assert captured["params"][0] == "[3.4," + ",".join(["3.4"] * 1023) + "]"
    assert captured["params"][-1] == 10
    assert "LIMIT %s" in captured["query"]


@pytest.mark.parametrize("top_k", [0, 11, True, 5.0])
@pytest.mark.asyncio
async def test_retriever_rejects_invalid_top_k_before_embedding(top_k):
    def unexpected_embedding():
        raise AssertionError("invalid retrieval limits must be rejected first")

    retriever = ReadOnlyRetriever("postgresql://readonly.invalid/db",
                                  embedding_factory=unexpected_embedding,
                                  embedding_settings=EmbeddingSettings(api_key=EMBEDDING_KEY))
    with pytest.raises(ValueError, match="INVALID_RETRIEVAL_LIMIT"):
        await retriever.retrieve("question", {"indexes": []}, "answer-test-01", top_k=top_k)


@pytest.mark.parametrize("length", [801, 16000])
@pytest.mark.asyncio
async def test_long_question_runs_through_embedding_http_and_llm_without_truncation(
        length, monkeypatch):
    question = "问" * 799 + "😀" + "问" * (length - 800)
    embedding_batches = []
    generated_questions = []
    evidence = _evidence()

    async def embedding_handler(request):
        payload = json.loads(request.content)
        embedding_batches.append(payload["input"])
        return httpx.Response(200, json={
            "model": "BAAI/bge-m3",
            "data": [{"index": index, "embedding": [0.125] * 1024}
                     for index, _ in enumerate(payload["input"])],
        })

    async def llm_handler(request):
        payload = json.loads(request.content)
        user_payload = json.loads(payload["messages"][1]["content"])
        generated_questions.append(user_payload["question"])
        source_id = user_payload["evidence"][0]["source_id"]
        return httpx.Response(200, json={
            "model": "deepseek-flash",
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({
                "answer": f"索引 READY 后才可检索[{source_id}]。", "has_answer": True,
                "source_ids": [source_id],
            })}}],
        })

    monkeypatch.setattr(ReadOnlyRetriever, "_fetch_rows", staticmethod(
        lambda _url, _query, _params, _deadline=None, _cancellation=None: [{
            "chunk_id": evidence[0]["chunk_id"],
            "document_id": evidence[0]["document_id"],
            "content_version_id": evidence[0]["content_version_id"],
            "index_version_id": evidence[0]["index_version_id"],
            "text_content": evidence[0]["text_content"],
            "text_sha256": "0" * 64,
            "locator_kind": "text_range",
            "source_page": None,
            "source_start": 12,
            "source_end": 32,
        }]))
    embedding_client = httpx.AsyncClient(transport=httpx.MockTransport(embedding_handler))
    llm_client = httpx.AsyncClient(transport=httpx.MockTransport(llm_handler))
    settings = EmbeddingSettings(api_key=EMBEDDING_KEY, max_batch_items=4)
    embedding = SiliconFlowEmbeddingAdapter(settings, embedding_client)
    llm = DeepSeekAdapter(LlmSettings(api_key=KEY), llm_client)
    closed = {"embedding": False, "llm": False}
    embedding_aclose = embedding.aclose
    llm_aclose = llm.aclose

    async def close_embedding():
        closed["embedding"] = True
        await embedding_aclose()

    async def close_llm():
        closed["llm"] = True
        await llm_aclose()

    embedding.aclose = close_embedding
    llm.aclose = close_llm
    retriever = ReadOnlyRetriever(
        "postgresql://readonly.invalid/db",
        embedding_factory=lambda: embedding,
        embedding_settings=settings)
    service = AnswerService("unused", _contract(), llm_factory=lambda: llm,
                            retriever=retriever)
    request = _request()
    request["question"] = question

    try:
        response = await service.answer(request)

        assert response["has_answer"] is True
        assert "".join(segment for batch in embedding_batches for segment in batch) == question
        assert all(len(segment) <= settings.max_text_codepoints
                   for batch in embedding_batches for segment in batch)
        assert [len(batch) for batch in embedding_batches] == (
            [2] if length == 801 else [4, 4, 4, 4, 4])
        assert generated_questions == [question]
        assert closed == {"embedding": True, "llm": True}
    finally:
        await embedding_client.aclose()
        await llm_client.aclose()


@pytest.mark.asyncio
async def test_answer_service_returns_only_cited_scope_sources():
    rows = _evidence()
    model = FakeLlm({"answer": "索引 READY 后才可检索[src-evidence-1]。",
                     "has_answer": True, "source_ids": ["src-evidence-1"]})
    model_profile = {"embedding_model_profile_id": "BAAI/bge-m3",
                     "llm_model_profile_id": "deepseek-flash"}
    service = AnswerService("unused", _contract(), llm_factory=lambda: model,
                            retriever=FakeRetriever(rows), model_profile=model_profile)
    response = await service.answer(_request())
    assert response["has_answer"] is True
    assert [source["source_id"] for source in response["sources"]] == ["src-evidence-1"]
    assert response["sources"][0]["quote"] == rows[0]["text_content"]
    assert response["model_profile"] == model_profile
    _contract().validate("AnswerResponse", response)


def _citation_response(answer, source_texts):
    rows = []
    for index, (source_id, text_content) in enumerate(source_texts.items(), 1):
        rows.append({"source_id": source_id, "document_id": "doc-example-1",
                     "content_version_id": "content-example-1",
                     "index_version_id": "index-example-1", "chunk_id": f"chunk-{index}",
                     "text_content": text_content,
                     "locator": {"kind": "text_range", "start": 0, "end": len(text_content),
                                 "unit": "unicode_code_point"}})
    service = AnswerService("unused", _contract(), retriever=FakeRetriever(rows))
    generated = {"answer": answer, "has_answer": True,
                 "source_ids": list(source_texts)}
    return service._response_from_generated(_request(), rows, generated)


def test_citation_verifier_accepts_a_supported_single_citation():
    response = _citation_response(
        "索引 READY 后才可检索[src-evidence-1]。",
        {"src-evidence-1": "索引 READY 后才可检索。"})

    assert response["has_answer"] is True
    assert [source["source_id"] for source in response["sources"]] == ["src-evidence-1"]


def test_citation_verifier_prunes_uncited_preface_before_supported_claim():
    response = _citation_response(
        "先说明一个简短背景。索引 READY 后才可检索[src-evidence-1]。",
        {"src-evidence-1": "索引 READY 后才可检索。"})

    assert response["has_answer"] is True
    assert response["answer"] == "索引 READY 后才可检索[src-evidence-1]。"


def test_citation_verifier_attaches_marker_only_unit_to_previous_claim():
    assert citations_are_grounded(
        "索引 READY 后才可检索。[src-evidence-1]",
        {"src-evidence-1": "索引 READY 后才可检索。"})


def test_citation_verifier_rejects_marker_only_unit_without_previous_claim():
    assert not citations_are_grounded(
        "[src-evidence-1]。索引 READY 后才可检索。",
        {"src-evidence-1": "索引 READY 后才可检索。"})


def test_citation_verifier_rejects_answer_with_no_cited_claims():
    assert not citations_are_grounded(
        "索引 READY 后才可检索。",
        {"src-evidence-1": "索引 READY 后才可检索。"})


def test_citation_verifier_refuses_parallel_markers_that_only_support_half_the_claim():
    response = _citation_response(
        "索引 READY 后才可检索，缓存默认关闭[src-evidence-1][src-evidence-2]。",
        {"src-evidence-1": "索引 READY 后才可检索。",
         "src-evidence-2": "缓存默认关闭。"})

    assert response["has_answer"] is False
    assert response["answer"] == "没有足够的资料证据回答这个问题。"
    assert response["sources"] == []


def test_citation_verifier_keeps_only_parallel_sources_containing_the_full_claim():
    answer = "生产环境支持批量导入，缓存关闭[src-evidence-1][src-evidence-2]"
    partial = _citation_response(answer, {
        "src-evidence-1": "生产环境支持批量导入。",
        "src-evidence-2": "生产环境支持批量导入，缓存关闭。",
    })
    complete = _citation_response(answer, {
        "src-evidence-1": "记录：生产环境支持批量导入，缓存关闭。",
        "src-evidence-2": "生产环境支持批量导入，缓存关闭。",
    })

    assert partial["has_answer"] is True
    assert partial["answer"] == "生产环境支持批量导入，缓存关闭[src-evidence-2]"
    assert [source["source_id"] for source in partial["sources"]] == ["src-evidence-2"]
    assert complete["has_answer"] is True


def test_citation_verifier_prunes_unsupported_marker_from_a_stack():
    response = _citation_response(
        "并发上限为 5 个任务且缓存关闭[src-evidence-1][src-evidence-2]。",
        {"src-evidence-1": "并发上限为 5 个任务。",
         "src-evidence-2": "并发上限为 5 个任务且缓存关闭。"})

    assert response["has_answer"] is True
    assert response["answer"] == "并发上限为 5 个任务且缓存关闭[src-evidence-2]。"
    assert [source["source_id"] for source in response["sources"]] == ["src-evidence-2"]


def test_citation_verifier_prunes_stacked_marker_with_negation_mismatch():
    response = _citation_response(
        "该操作支持导出且审计开启[src-evidence-1][src-evidence-2]。",
        {"src-evidence-1": "该操作不支持导出。",
         "src-evidence-2": "该操作支持导出且审计开启。"})

    assert response["has_answer"] is True
    assert response["answer"] == "该操作支持导出且审计开启[src-evidence-2]。"
    assert [source["source_id"] for source in response["sources"]] == ["src-evidence-2"]


def test_citation_verifier_drops_unsupported_claim_but_keeps_grounded_content():
    response = _citation_response(
        "索引 READY 后才可检索[src-evidence-1]。缓存默认开启[src-evidence-2][src-evidence-3]。",
        {"src-evidence-1": "索引 READY 后才可检索。",
         "src-evidence-2": "缓存默认关闭。",
         "src-evidence-3": "索引 READY 后才可检索。"})

    assert response["has_answer"] is True
    assert response["answer"] == "索引 READY 后才可检索[src-evidence-1]。"
    assert [source["source_id"] for source in response["sources"]] == ["src-evidence-1"]
    assert {source["source_id"] for source in response["sources"]} == {
        marker[1:-1] for marker in re.findall(r"\[[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\]",
                                               response["answer"])}


def test_citation_pruner_returns_false_when_all_claims_are_ungrounded():
    result = prune_ungrounded_claims(
        "索引 READY 后才可检索[src-evidence-1][src-evidence-2]。",
        {"src-evidence-1": "索引可以查询。", "src-evidence-2": "后台提供管理功能。"})

    assert result == {"pruned_answer": "", "kept_source_ids": [], "ok": False}


def test_citation_verifier_allows_single_marker_when_source_text_is_present():
    # Unrelated single-marker paraphrases are not hard-refused by the verifier.
    response = _citation_response(
        "数据库采用 PostgreSQL 存储[src-evidence-1]。",
        {"src-evidence-1": "系统支持文档索引与语义搜索。"})

    assert response["has_answer"] is True
    assert response["sources"][0]["source_id"] == "src-evidence-1"


def test_citation_verifier_accepts_a_high_overlap_paraphrase():
    response = _citation_response(
        "索引 READY 后即可检索[src-evidence-1]。",
        {"src-evidence-1": "索引 READY 后才可检索。"})

    assert response["has_answer"] is True
    assert response["sources"][0]["quote"] == "索引 READY 后才可检索。"


def test_citation_verifier_accepts_paraphrase_supported_across_the_full_chunk():
    response = _citation_response(
        "READY 状态使索引可检索，任务发布后内容可查询[src-evidence-1]。",
        {"src-evidence-1": "READY 状态使索引能够检索。任务发布后内容可以查询。"})

    assert response["has_answer"] is True


def test_citation_verifier_ignores_negation_in_an_unrelated_source_sentence():
    response = _citation_response(
        "索引 READY 后即可检索[src-evidence-1]。",
        {"src-evidence-1": "未授权访客不得访问后台。索引 READY 后才可检索。"})

    assert response["has_answer"] is True


@pytest.mark.parametrize(("answer", "claim"), [
    ("请访问 https://docs.example.test/start[src-evidence-1]。",
     "请访问 https://docs.example.test/start"),
    ("联系 help@example.test[src-evidence-1]。",
     "联系 help@example.test"),
])
def test_citation_verifier_keeps_url_and_email_dots_inside_the_claim(answer, claim):
    units = _claim_units(answer)
    response = _citation_response(answer, {"src-evidence-1": claim + "。"})

    assert [unit_claim for unit_claim, _ in units] == [claim]
    assert response["has_answer"] is True
    assert [source["source_id"] for source in response["sources"]] == ["src-evidence-1"]


@pytest.mark.parametrize("url", [
    "https://docs.example.test/search?q=cache",
    "https://docs.example.test/items;view=all",
])
def test_citation_pruning_and_response_preserve_url_boundary_characters(url):
    answer = f"请访问 {url}[src-evidence-1]。"
    evidence = f"请访问 {url}。"

    result = prune_ungrounded_claims(answer, {"src-evidence-1": evidence})
    response = _citation_response(answer, {"src-evidence-1": evidence})

    assert [claim for claim, _ in _claim_units(answer)] == [f"请访问 {url}"]
    assert result == {"pruned_answer": answer,
                      "kept_source_ids": ["src-evidence-1"], "ok": True}
    assert response["has_answer"] is True
    assert response["answer"] == answer
    assert [source["source_id"] for source in response["sources"]] == ["src-evidence-1"]


@pytest.mark.parametrize("quote", ['"', '`'])
@pytest.mark.parametrize("separator", [";", "!", "?"])
def test_citation_pruning_stops_url_at_a_closing_quote(quote, separator):
    answer = (f"参考 {quote}https://docs.example.test/start{quote}{separator}"
              "缓存默认关闭[src-evidence-1][src-evidence-2]。")
    evidence = {"src-evidence-1": "缓存默认关闭。",
                "src-evidence-2": "缓存默认开启。"}

    result = prune_ungrounded_claims(answer, evidence)
    response = _citation_response(answer, evidence)

    assert result == {"pruned_answer": "缓存默认关闭[src-evidence-1]。",
                      "kept_source_ids": ["src-evidence-1"], "ok": True}
    assert response["has_answer"] is True
    assert response["answer"] == "缓存默认关闭[src-evidence-1]。"
    assert [source["source_id"] for source in response["sources"]] == ["src-evidence-1"]


@pytest.mark.parametrize(("quote", "second_url"), [
    ('"', "https://docs.example.test/search?q=cache"),
    ('"', "https://docs.example.test/items;view=all"),
    ("`", "https://docs.example.test/search?q=cache"),
    ("`", "https://docs.example.test/items;view=all"),
])
@pytest.mark.asyncio
async def test_answer_service_rescans_each_quoted_url(quote, second_url):
    claim = (f"入口{quote}https://docs.example.test/start{quote}和"
             f"{quote}{second_url}{quote}")
    answer = claim + "[src-evidence-1]。"
    evidence_text = claim + "。"
    rows = _evidence()
    rows[0]["text_content"] = evidence_text
    model = FakeLlm({"answer": answer, "has_answer": True,
                     "source_ids": ["src-evidence-1"]})
    service = AnswerService("unused", _contract(), llm_factory=lambda: model,
                            retriever=FakeRetriever(rows))

    result = prune_ungrounded_claims(answer, {"src-evidence-1": evidence_text})
    response = await service.answer(_request())

    assert result == {"pruned_answer": answer,
                      "kept_source_ids": ["src-evidence-1"], "ok": True}
    assert response["has_answer"] is True
    assert response["answer"] == answer
    assert [source["source_id"] for source in response["sources"]] == ["src-evidence-1"]


@pytest.mark.parametrize("email", [
    "help!desk@example.test",
    "help?desk@example.test",
    '"help;desk"@example.test',
])
def test_citation_pruning_preserves_internal_email_boundary_characters(email):
    answer = f"联系 {email}[src-evidence-1]。"
    evidence = f"联系 {email}。"
    response = _citation_response(answer, {"src-evidence-1": evidence})

    assert [claim for claim, _ in _claim_units(answer)] == [f"联系 {email}"]
    assert response["has_answer"] is True
    assert response["answer"] == answer


@pytest.mark.parametrize("url", [
    "https://docs.example.test/search?q=cache",
    "https://docs.example.test/items;view=all",
])
def test_sentence_terminator_outside_url_still_splits_claims(url):
    units = _claim_units(f"先访问 {url}。后续说明")

    assert [(claim, markers) for claim, markers in units] == [
        (f"先访问 {url}", []), ("后续说明", [])]


@pytest.mark.asyncio
async def test_answer_refusal_includes_validated_model_profile_without_provider_call():
    model_profile = {"embedding_model_profile_id": "BAAI/bge-m3",
                     "llm_model_profile_id": "deepseek-flash"}

    def unexpected_model_call():
        raise AssertionError("empty retrieval must not call the model")

    service = AnswerService("unused", _contract(), llm_factory=unexpected_model_call,
                            retriever=FakeRetriever([]), model_profile=model_profile)
    response = await service.answer(_request())

    assert response["has_answer"] is False
    assert response["model_profile"] == model_profile
    _contract().validate("AnswerResponse", response)


@pytest.mark.parametrize("field", ["document_id", "content_version_id", "index_version_id"])
@pytest.mark.asyncio
async def test_out_of_scope_evidence_is_rejected_before_generation(field):
    rows = _evidence()
    rows[0][field] = "out-of-scope-version"

    def unexpected_model_call():
        raise AssertionError("out-of-scope evidence must not reach the generation model")

    service = AnswerService("unused", _contract(), llm_factory=unexpected_model_call,
                            retriever=FakeRetriever(rows))
    with pytest.raises(ProcessingError, match="AI_PROCESSING_FAILED"):
        await service.answer(_request())


@pytest.mark.asyncio
async def test_answer_service_rejects_forged_model_citation():
    model = FakeLlm({"answer": "未经检索的引用。[src-forged]",
                     "has_answer": True, "source_ids": ["src-forged"]})
    service = AnswerService("unused", _contract(), llm_factory=lambda: model,
                            retriever=FakeRetriever(_evidence()))
    with pytest.raises(ProcessingError, match="MODEL_FAILURE"):
        await service.answer(_request())


@pytest.mark.asyncio
async def test_empty_retrieval_refuses_without_a_generation_call():
    def unexpected_model_call():
        raise AssertionError("must not call the generation model without evidence")
    service = AnswerService("unused", _contract(), llm_factory=unexpected_model_call,
                            retriever=FakeRetriever([]))
    response = await service.answer(_request())
    assert response["has_answer"] is False and response["sources"] == []


@pytest.mark.asyncio
async def test_deepseek_adapter_uses_fixed_host_and_disabled_thinking():
    captured = []

    async def handler(request):
        captured.append(request)
        return httpx.Response(200, json={"model": "deepseek-flash", "choices": [{
            "finish_reason": "stop", "message": {"content": json.dumps({
                "answer": "有证据。[src-evidence-1]", "has_answer": True,
                "source_ids": ["src-evidence-1"]})}}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = DeepSeekAdapter(LlmSettings(api_key=KEY), client)
    result = await adapter.generate("问题", _evidence(), request_id="answer-001")
    payload = json.loads(captured[0].content)
    assert str(captured[0].url) == "https://api.deepseek.com/chat/completions"
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["response_format"] == {"type": "json_object"}
    assert result["source_ids"] == ["src-evidence-1"]
    assert captured[0].headers["Authorization"] == "Bearer " + KEY
    await client.aclose()


def test_deepseek_prompt_refuses_when_core_question_is_not_supported():
    adapter = object.__new__(DeepSeekAdapter)
    adapter.settings = LlmSettings(api_key=KEY)

    system_prompt = adapter._payload("问题", _evidence())["messages"][0]["content"]

    assert "问题的核心所问无法被资料充分支持或确定" in system_prompt
    assert "即使资料能提供相关背景" in system_prompt
    assert "has_answer=false 和空 source_ids" in system_prompt
    assert "不要用背景信息冒充对核心问题的回答" in system_prompt
    assert "每个可核查断言都必须紧邻 [source_id]，放在断言后、句末标点前" in system_prompt
    assert "不同事实用独立句或分号分隔并分别引用" in system_prompt
    assert "禁止多事实合一句后在句末堆 [s1][s2]" in system_prompt
    assert "每个引用必须独立支持其所附着的完整断言" in system_prompt
    assert "尽量沿用资料中的完整短句" in system_prompt
    assert "不要添加无引用的背景前言或总结" in system_prompt


def test_llm_settings_maps_invalid_port_to_configuration_error():
    with pytest.raises(ConfigurationError, match="LLM_BASE_URL_INVALID"):
        LlmSettings(base_url="https://api.deepseek.com:invalid", api_key=KEY)


@pytest.mark.parametrize("provider", [[], {"model": "deepseek-flash", "choices": [[]]}])
@pytest.mark.asyncio
async def test_deepseek_adapter_rejects_invalid_provider_shapes(provider):
    async def handler(request):
        return httpx.Response(200, json=provider)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = DeepSeekAdapter(LlmSettings(api_key=KEY), client)
    with pytest.raises(ProcessingError, match="MODEL_FAILURE"):
        await adapter.generate("问题", _evidence(), request_id="answer-invalid-provider")
    await client.aclose()


# --- prune reason codes and claim-level repair -------------------------------


@pytest.mark.parametrize("environ", [
    {},
    {"KNOWFLOW_ANSWER_REPAIR": ""},
    {"KNOWFLOW_ANSWER_REPAIR": "  "},
    {"KNOWFLOW_ANSWER_REPAIR": "sometimes"},
])
def test_answer_repair_is_disabled_when_unset_empty_or_unrecognized(environ):
    assert answer_repair_enabled(environ) is False


@pytest.mark.parametrize("value", ["on", "ON", "true", "1", "yes"])
def test_answer_repair_requires_an_explicit_enable_value(value):
    assert answer_repair_enabled({"KNOWFLOW_ANSWER_REPAIR": value}) is True


def test_repair_numeric_coverage_ignores_numbers_inside_source_markers():
    assert not _has_question_content_overlap(
        "缓存默认关闭 2027 吗？", "缓存默认关闭[src-evidence-2027]。")


def test_repair_relevance_requires_half_of_question_content_tokens():
    assert not _has_question_content_overlap(
        "公司 2027 年净利润是多少？", "公司缓存默认关闭 2027")


def test_answer_service_repair_is_off_when_the_switch_is_unset(monkeypatch):
    monkeypatch.delenv("KNOWFLOW_ANSWER_REPAIR", raising=False)
    service = AnswerService("unused", _contract(), retriever=FakeRetriever([]))

    assert service._repair_enabled is False


def _two_evidence():
    rows = _evidence()
    rows.append({**rows[0], "source_id": "src-evidence-2", "chunk_id": "chunk-example-2",
                 "text_content": "原始资料说明缓存默认关闭。"})
    return rows


def test_prune_claims_reports_grounded_reason_and_counts():
    result = prune_claims(
        "索引 READY 后才可检索[src-evidence-1]。背景说明。",
        {"src-evidence-1": "原始资料说明索引 READY 后才可检索。"})

    assert result["ok"] is True
    assert result["reason"] == "grounded"
    assert result["claims"] == 2
    assert result["kept_claims"] == 1
    assert result["uncited_claims"] == 1
    assert result["dropped_claims"] == 1
    assert result["repaired_claims"] == 0
    assert result["pruned_markers"] == 0


def test_prune_claims_reports_empty_after_prune_and_pruned_markers():
    result = prune_claims(
        "索引 READY 后才可检索，缓存默认关闭[src-evidence-1][src-evidence-2]。",
        {"src-evidence-1": "索引可以查询。", "src-evidence-2": "后台提供管理功能。"})

    assert result["ok"] is False
    assert result["reason"] == "empty_after_prune"
    assert result["pruned_markers"] == 2
    assert result["kept_source_ids"] == []


def test_prune_claims_reports_no_cited_claims_for_an_unmarked_answer():
    result = prune_claims("索引 READY 后才可检索。",
                          {"src-evidence-1": "索引 READY 后才可检索。"})

    assert result["ok"] is False
    assert result["reason"] == "no_cited_claims"


def test_prune_claims_counts_deleted_marker_without_a_claim():
    result = prune_claims("[src-evidence-1]", {"src-evidence-1": "索引 READY 后才可检索。"})

    assert result["ok"] is False
    assert result["pruned_markers"] == 1


def test_prune_claims_reattaches_an_uncited_claim_to_a_declared_source():
    result = prune_claims(
        "索引 READY 后才可检索[src-evidence-1]。缓存默认关闭。",
        {"src-evidence-1": "原始资料说明索引 READY 后才可检索。缓存默认关闭。"})

    assert result["ok"] is True
    assert result["reason"] == "grounded"
    assert result["repaired_claims"] == 1
    assert result["pruned_answer"] == ("索引 READY 后才可检索[src-evidence-1]。 "
                                       "缓存默认关闭[src-evidence-1]。")
    assert result["kept_source_ids"] == ["src-evidence-1"]
    # The newly attached citation is not counted as a deleted input marker.
    assert result["pruned_markers"] == 0


def test_prune_claims_reattaches_a_stacked_claim_to_an_already_declared_source():
    # Both stacked markers miss the full claim; a declared source carries it.
    result = prune_claims(
        "索引可检索[src-evidence-3]。缓存默认关闭[src-evidence-1][src-evidence-2]。",
        {"src-evidence-1": "原始资料说明缓存默认开启。",
         "src-evidence-2": "原始资料说明索引可检索。",
         "src-evidence-3": "原始资料说明索引可检索。原始资料说明缓存默认关闭。"})

    assert result["ok"] is True
    assert result["repaired_claims"] == 1
    assert result["pruned_answer"] == ("索引可检索[src-evidence-3]。 "
                                       "缓存默认关闭[src-evidence-3]。")
    assert result["kept_source_ids"] == ["src-evidence-3"]
    # Two unsupported input markers were removed while one new one was added.
    assert result["pruned_markers"] == 2


def test_prune_claims_never_reattaches_without_verbatim_evidence():
    result = prune_claims(
        "索引 READY 后才可检索，缓存默认关闭[src-evidence-1][src-evidence-2]。",
        {"src-evidence-1": "索引 READY 后才可检索。",
         "src-evidence-2": "缓存默认关闭。"})

    assert result["ok"] is False
    assert result["reason"] == "empty_after_prune"
    assert result["repaired_claims"] == 0


def test_prune_claims_does_not_reattach_when_an_answer_cites_nothing():
    result = prune_claims("缓存默认关闭。", {"src-evidence-1": "原始资料说明缓存默认关闭。"})

    assert result["ok"] is False
    assert result["repaired_claims"] == 0
    assert result["kept_source_ids"] == []


class RepairLlm:
    """First generation fails citation validation; the re-ask can differ."""

    def __init__(self, first, repaired, *, repair_error=None):
        self.first = first
        self.repaired = repaired
        self.repair_error = repair_error
        self.generate_calls = 0
        self.repair_calls = 0
        self.previous_answers = []

    async def generate(self, question, evidence, *, request_id):
        self.generate_calls += 1
        return self.first

    async def generate_repair(self, question, evidence, previous_answer, *, request_id):
        self.repair_calls += 1
        self.previous_answers.append(previous_answer)
        if self.repair_error is not None:
            raise self.repair_error
        return self.repaired

    async def aclose(self):
        return None


def _ungrounded_generated():
    return {"answer": "索引 READY 后才可检索，缓存默认关闭[src-evidence-1][src-evidence-2]。",
            "has_answer": True, "source_ids": ["src-evidence-1", "src-evidence-2"]}


def _grounded_generated():
    return {"answer": "原始资料说明索引 READY 后才可检索[src-evidence-1]。",
            "has_answer": True, "source_ids": ["src-evidence-1"]}


_LONG_SOURCE_ID = "src-00000000-0000-0000-0000-000000000001"


def _length_expanding_generated(source_id=_LONG_SOURCE_ID):
    return {"answer": f"a[{source_id}]。" + "a。" * 400,
            "has_answer": True, "source_ids": [source_id]}


def _length_expanding_evidence(source_id=_LONG_SOURCE_ID):
    return [{**_evidence()[0], "source_id": source_id, "text_content": "a。"}]


def test_prune_claims_rejects_answer_that_exceeds_limit_after_reattachment():
    generated = _length_expanding_generated()
    result = prune_claims(generated["answer"], {_LONG_SOURCE_ID: "a。"})

    assert len(generated["answer"]) < 16000
    assert len(result["pruned_answer"]) > 16000
    assert result["ok"] is False
    assert result["reason"] == "answer_too_long_after_prune"
    assert result["repaired_claims"] == 400
    assert result["pruned_markers"] == 0


@pytest.mark.asyncio
async def test_answer_service_refuses_when_first_generation_expands_past_answer_limit(
        monkeypatch):
    monkeypatch.setenv("KNOWFLOW_ANSWER_REPAIR", "off")
    model = RepairLlm(_length_expanding_generated(), _length_expanding_generated())
    service = AnswerService("unused", _contract(), llm_factory=lambda: model,
                            retriever=FakeRetriever(_length_expanding_evidence()))

    response = await service.answer(_request())

    assert response["has_answer"] is False
    assert response["answer"] == "没有足够的资料证据回答这个问题。"
    assert model.repair_calls == 0
    assert service.last_diagnostics["reason"] == "answer_too_long_after_prune"


@pytest.mark.asyncio
async def test_answer_service_keeps_refusal_when_repair_expands_past_answer_limit(monkeypatch):
    monkeypatch.setenv("KNOWFLOW_ANSWER_REPAIR", "on")
    evidence = [*_two_evidence(), *_length_expanding_evidence()]
    model = RepairLlm(_ungrounded_generated(), _length_expanding_generated())
    service = AnswerService("unused", _contract(), llm_factory=lambda: model,
                            retriever=FakeRetriever(evidence))

    response = await service.answer(_request())

    assert response["has_answer"] is False
    assert response["answer"] == "没有足够的资料证据回答这个问题。"
    assert model.repair_calls == 1
    assert service.last_diagnostics["repair_attempt"] == 1
    assert service.last_diagnostics["repair_outcome"] == "still_ungrounded"
    assert service.last_diagnostics["reason"] == "empty_after_prune"


@pytest.mark.asyncio
async def test_answer_service_reasks_once_and_prefers_the_grounded_repair(monkeypatch):
    monkeypatch.setenv("KNOWFLOW_ANSWER_REPAIR", "on")
    evidence = _two_evidence()
    evidence[0]["text_content"] = "原始资料说明 2027 年索引 READY 后才可检索。"
    repaired = {"answer": "原始资料说明 2027 年索引 READY 后才可检索[src-evidence-1]。",
                "has_answer": True, "source_ids": ["src-evidence-1"]}
    model = RepairLlm(_ungrounded_generated(), repaired)
    service = AnswerService("unused", _contract(), llm_factory=lambda: model,
                            retriever=FakeRetriever(evidence))
    request = _request()
    request["question"] = "2027 年索引何时可检索？"

    response = await service.answer(request)

    assert response["has_answer"] is True
    assert response["answer"] == repaired["answer"]
    assert [source["source_id"] for source in response["sources"]] == ["src-evidence-1"]
    assert model.generate_calls == 1 and model.repair_calls == 1
    assert model.previous_answers == [_ungrounded_generated()["answer"]]
    assert service.last_diagnostics["repair_outcome"] == "answered"
    assert service.last_diagnostics["reason"] == "grounded"


@pytest.mark.asyncio
async def test_answer_service_rejects_grounded_repair_unrelated_to_question(monkeypatch):
    monkeypatch.setenv("KNOWFLOW_ANSWER_REPAIR", "on")
    request = _request()
    request["question"] = "公司 2027 年净利润是多少？"
    unrelated = {"answer": "原始资料说明缓存默认关闭[src-evidence-2]。",
                 "has_answer": True, "source_ids": ["src-evidence-2"]}
    model = RepairLlm(_ungrounded_generated(), unrelated)
    service = AnswerService("unused", _contract(), llm_factory=lambda: model,
                            retriever=FakeRetriever(_two_evidence()))

    # The relevance gate belongs to repaired-output acceptance only.
    initial_response = service._response_from_generated(request, _two_evidence(), unrelated)
    assert initial_response["has_answer"] is True

    response = await service.answer(request)

    assert response["has_answer"] is False
    assert response["answer"] == "没有足够的资料证据回答这个问题。"
    assert response["sources"] == []
    assert model.generate_calls == 1 and model.repair_calls == 1
    assert service.last_diagnostics["repair_attempt"] == 1
    assert service.last_diagnostics["repair_outcome"] == "failed_unrelated"
    assert service.last_diagnostics["decision"] == "refused"


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["shared_company", "shared_cache_background"])
async def test_answer_service_rejects_grounded_repair_missing_question_core(case):
    request = _request()
    evidence = _two_evidence()
    if case == "shared_company":
        request["question"] = "公司 2027 年净利润是多少？"
        evidence[1]["text_content"] = "原始资料说明公司缓存默认关闭。"
        repaired = {"answer": "公司缓存默认关闭[src-evidence-2]。",
                    "has_answer": True, "source_ids": ["src-evidence-2"]}
    else:
        request["question"] = "缓存默认关闭时，公司 2027 年净利润是多少？"
        repaired = {"answer": "缓存默认关闭[src-evidence-2]。",
                    "has_answer": True, "source_ids": ["src-evidence-2"]}

    model = RepairLlm(_ungrounded_generated(), repaired)
    service = AnswerService("unused", _contract(), llm_factory=lambda: model,
                            retriever=FakeRetriever(evidence))
    service._repair_enabled = True

    repaired_response, repaired_diagnostics = service._evaluate_generated(
        request, evidence, repaired)
    assert repaired_diagnostics["decision"] == "answered"
    assert repaired_response["has_answer"] is True

    response = await service.answer(request)

    assert response["answer"] == "没有足够的资料证据回答这个问题。"
    assert response["has_answer"] is False and response["sources"] == []
    assert model.repair_calls == 1
    assert service.last_diagnostics["repair_outcome"] == "failed_unrelated"


@pytest.mark.asyncio
async def test_answer_service_refuses_after_an_ungrounded_repair_without_a_third_call(
        monkeypatch):
    monkeypatch.setenv("KNOWFLOW_ANSWER_REPAIR", "on")
    model = RepairLlm(_ungrounded_generated(), _ungrounded_generated())
    service = AnswerService("unused", _contract(), llm_factory=lambda: model,
                            retriever=FakeRetriever(_two_evidence()))

    response = await service.answer(_request())

    assert response["has_answer"] is False
    assert response["answer"] == "没有足够的资料证据回答这个问题。"
    assert response["sources"] == []
    assert model.generate_calls == 1 and model.repair_calls == 1
    assert service.last_diagnostics["repair_outcome"] == "still_ungrounded"
    assert service.last_diagnostics["reason"] == "empty_after_prune"


@pytest.mark.asyncio
async def test_answer_service_records_a_declined_repair_as_such(monkeypatch):
    monkeypatch.setenv("KNOWFLOW_ANSWER_REPAIR", "on")
    model = RepairLlm(_ungrounded_generated(),
                      {"answer": "没有足够的资料证据回答这个问题。",
                       "has_answer": False, "source_ids": []})
    service = AnswerService("unused", _contract(), llm_factory=lambda: model,
                            retriever=FakeRetriever(_two_evidence()))

    response = await service.answer(_request())

    assert response["has_answer"] is False
    assert service.last_diagnostics["repair_outcome"] == "declined"
    assert service.last_diagnostics["repair_attempt"] == 1


@pytest.mark.asyncio
async def test_answer_service_does_not_reask_when_the_model_declines(monkeypatch):
    monkeypatch.setenv("KNOWFLOW_ANSWER_REPAIR", "on")
    model = RepairLlm({"answer": "没有足够的资料证据回答这个问题。",
                       "has_answer": False, "source_ids": []}, _grounded_generated())
    service = AnswerService("unused", _contract(), llm_factory=lambda: model,
                            retriever=FakeRetriever(_two_evidence()))

    response = await service.answer(_request())

    assert response["has_answer"] is False
    assert model.repair_calls == 0


@pytest.mark.asyncio
async def test_answer_service_keeps_the_refusal_when_the_repair_call_fails(monkeypatch):
    monkeypatch.setenv("KNOWFLOW_ANSWER_REPAIR", "on")
    model = RepairLlm(_ungrounded_generated(), _grounded_generated(),
                      repair_error=ProcessingError("MODEL_FAILURE", 502, retryable=True))
    service = AnswerService("unused", _contract(), llm_factory=lambda: model,
                            retriever=FakeRetriever(_two_evidence()))

    response = await service.answer(_request())

    assert response["has_answer"] is False
    assert response["answer"] == "没有足够的资料证据回答这个问题。"
    assert model.repair_calls == 1


@pytest.mark.asyncio
async def test_answer_service_keeps_the_refusal_when_the_repair_is_malformed(monkeypatch):
    monkeypatch.setenv("KNOWFLOW_ANSWER_REPAIR", "on")
    model = RepairLlm(_ungrounded_generated(), {"answer": "x", "has_answer": True})
    service = AnswerService("unused", _contract(), llm_factory=lambda: model,
                            retriever=FakeRetriever(_two_evidence()))

    response = await service.answer(_request())

    assert response["has_answer"] is False
    assert model.repair_calls == 1


@pytest.mark.asyncio
async def test_answer_service_keeps_refusal_when_repair_contract_validation_fails(monkeypatch):
    monkeypatch.setenv("KNOWFLOW_ANSWER_REPAIR", "on")
    repaired = _grounded_generated()
    model = RepairLlm(_ungrounded_generated(), repaired)
    service = AnswerService("unused", _contract_rejecting_answer(repaired["answer"]),
                            llm_factory=lambda: model,
                            retriever=FakeRetriever(_two_evidence()))

    response = await service.answer(_request())

    assert response["has_answer"] is False
    assert response["answer"] == "没有足够的资料证据回答这个问题。"
    assert model.repair_calls == 1
    assert service.last_diagnostics["repair_attempt"] == 1
    assert service.last_diagnostics["repair_outcome"] == "failed_contract_validation"


@pytest.mark.asyncio
async def test_answer_service_skips_the_repair_without_deadline_headroom(monkeypatch):
    monkeypatch.setenv("KNOWFLOW_ANSWER_REPAIR", "on")
    model = RepairLlm(_ungrounded_generated(), _grounded_generated())
    service = AnswerService("unused", _contract(), llm_factory=lambda: model,
                            retriever=FakeRetriever(_two_evidence()))

    final = await service._finalize_generation(
        _request(), _two_evidence(), _ungrounded_generated(), time.monotonic() + 1)

    assert final["has_answer"] is False
    assert final["answer"] == "没有足够的资料证据回答这个问题。"
    assert model.repair_calls == 0


@pytest.mark.asyncio
async def test_answer_service_repair_switch_disables_the_reask(monkeypatch):
    monkeypatch.setenv("KNOWFLOW_ANSWER_REPAIR", "off")
    model = RepairLlm(_ungrounded_generated(), _grounded_generated())
    service = AnswerService("unused", _contract(), llm_factory=lambda: model,
                            retriever=FakeRetriever(_two_evidence()))

    response = await service.answer(_request())

    assert response["has_answer"] is False
    assert model.repair_calls == 0


def test_repair_payload_carries_the_previous_answer_and_no_new_evidence():
    adapter = object.__new__(DeepSeekAdapter)
    adapter.settings = LlmSettings(api_key=KEY)
    evidence = _evidence()

    plain = adapter._payload("问题", evidence)
    repair = adapter._payload("问题", evidence, previous_answer="上一版答案[src-evidence-1]。")

    assert "previous_answer" not in json.loads(plain["messages"][1]["content"])
    body = json.loads(repair["messages"][1]["content"])
    assert body["previous_answer"] == "上一版答案[src-evidence-1]。"
    assert body["evidence"] == json.loads(plain["messages"][1]["content"])["evidence"]
    assert set(body) == {"question", "evidence", "previous_answer"}
    assert "上一版答案未通过引用校验" in repair["messages"][0]["content"]
    assert "上一版答案未通过引用校验" not in plain["messages"][0]["content"]
    assert repair["max_tokens"] == plain["max_tokens"] == 1024

