import json
from pathlib import Path
import threading

import httpx
import psycopg
import pytest

from knowflow_ai.adapters import ProcessingError
from knowflow_ai.answering import (
    AnswerService,
    DeepSeekAdapter,
    LlmSettings,
    ReadOnlyRetriever,
)
from knowflow_ai.config import ConfigurationError
from knowflow_ai.protocol import ContractConsumer


ROOT = Path(__file__).resolve().parents[3]
KEY = "synthetic-deepseek-key-" + "x" * 32


class FakeRetriever:
    def __init__(self, rows):
        self.rows = rows

    async def retrieve(self, question, scope, request_id):
        return self.rows


class FakeLlm:
    def __init__(self, result):
        self.result = result

    async def generate(self, question, evidence, *, request_id):
        return self.result

    async def aclose(self):
        return None


def _request():
    return {"contract_version": "0.2.0-draft.6", "request_id": "answer-test-01",
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
        def __enter__(self):
            return self

        def __exit__(self, *args):
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
    monkeypatch.setattr(answering.psycopg, "connect", connect)

    class FakeEmbedding:
        async def embed(self, texts, *, request_id):
            return {"data": [{"embedding": [0.125] * 1024}]}

        async def aclose(self):
            return None

    main_thread_id = threading.get_ident()
    retriever = ReadOnlyRetriever(
        "postgresql://readonly.invalid/db", embedding_factory=FakeEmbedding)
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
    assert "d.active_index_version_id = c.index_version_id" in calls["query"]
    assert evidence[0]["text_content"] == "verified source text"
    assert evidence[0]["locator"]["unit"] == "unicode_code_point"


@pytest.mark.asyncio
async def test_answer_service_returns_only_cited_scope_sources():
    rows = _evidence()
    model = FakeLlm({"answer": "索引 READY 后才可检索。[src-evidence-1]",
                     "has_answer": True, "source_ids": ["src-evidence-1"]})
    service = AnswerService("unused", _contract(), llm_factory=lambda: model,
                            retriever=FakeRetriever(rows))
    response = await service.answer(_request())
    assert response["has_answer"] is True
    assert [source["source_id"] for source in response["sources"]] == ["src-evidence-1"]
    assert response["sources"][0]["quote"] == rows[0]["text_content"]
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
