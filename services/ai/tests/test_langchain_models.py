import asyncio
import json
import socket
from uuid import uuid4

import httpx
import httpx2
import pytest

from knowflow_ai.adapters import ProcessingError
from knowflow_ai.answering import AnswerService, LlmSettings
from knowflow_ai.langchain_answer import CustomModel, LangChainAnswerModel
from knowflow_ai import langchain_answer, model_egress


OUTPUT = {"answer": "The observatory opens at 09:45 [source-1].", "has_answer": True,
          "source_ids": ["source-1"]}


def sse(*events, response_class=httpx.Response):
    return response_class(200, headers={"content-type": "text/event-stream"}, content="".join(
        (f"event: {item['type']}\n" if "type" in item else "") + f"data: {json.dumps(item)}\n\n"
        for item in events))


def chat(delta, finish="stop"):
    return sse({"id": "chat-1", "model": "test-model", "object": "chat.completion.chunk", "created": 0,
                "choices": [{"index": 0, "delta": {"role": "assistant", **delta}, "finish_reason": finish}]})


def anthropic_events(text):
    return sse(
        {"type": "message_start", "message": {"id": "msg_1", "type": "message", "model": "test-model",
         "role": "assistant", "content": [], "usage": {"input_tokens": 10, "output_tokens": 0},
         "stop_reason": None, "stop_sequence": None}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
         "usage": {"output_tokens": 10}},
        {"type": "message_stop"},
        response_class=httpx2.Response,
    )


def responses_events(text):
    block = {"type": "output_text", "text": text, "annotations": [], "logprobs": []}
    message = {"type": "message", "id": "msg_1", "status": "completed", "role": "assistant", "content": [block]}
    response = {"id": "resp_1", "object": "response", "model": "test-model", "status": "completed",
                "created_at": 0, "output": [message], "parallel_tool_calls": False, "tool_choice": "auto", "tools": []}
    return sse(
        {"type": "response.output_item.added", "sequence_number": 1, "output_index": 0,
         "item": {**message, "content": [], "status": "in_progress"}},
        {"type": "response.output_text.delta", "sequence_number": 2, "item_id": "msg_1",
         "output_index": 0, "content_index": 0, "delta": text, "logprobs": []},
        {"type": "response.completed", "sequence_number": 3, "response": response},
    )


def model_config(protocol="chat_completions", *, tools=False):
    return CustomModel(id=uuid4(), model_id="test-model", protocol=protocol, supports_tools=tools,
                       base_url="https://provider.example.com/prefix", api_key="fixture-key")


@pytest.mark.asyncio
@pytest.mark.parametrize(("protocol", "path", "response"), [
    ("chat_completions", "/prefix/chat/completions", lambda text: chat({"content": text})),
    ("responses", "/prefix/responses", responses_events),
    ("anthropic_messages", "/prefix/v1/messages", anthropic_events),
])
async def test_protocol_stream(protocol, path, response):
    async def handle(request):
        assert request.url.path == path
        assert request.url.host == "provider.example.com"
        assert request.headers.get("x-api-key" if protocol == "anthropic_messages" else "authorization").endswith("fixture-key")
        payload = json.loads(request.content)
        assert payload["stream"] is True
        assert payload["model"] == "test-model"
        if protocol == "responses":
            assert payload["store"] is False
        return response(json.dumps(OUTPUT))

    transport = httpx2.MockTransport if protocol == "anthropic_messages" else httpx.MockTransport
    model = LangChainAnswerModel(model_config(protocol), transport=transport(handle))
    try:
        assert await model.generate("What time?", [], request_id="question") == OUTPUT
    finally:
        await model.aclose()


@pytest.mark.asyncio
async def test_agent_only_searches_once_and_reserves_each_deepseek_call(monkeypatch):
    calls, reservations, searches = [], [], []

    async def reserve(provider, model, payload):
        reservations.append((provider, model, payload["max_tokens"]))

    monkeypatch.setattr(langchain_answer, "reserve_provider_call", reserve)

    async def handle(request):
        payload = json.loads(request.content)
        calls.append(payload)
        assert payload["max_tokens"] == 1024 and "max_completion_tokens" not in payload
        if len(calls) == 1:
            assert payload["thinking"] == {"type": "disabled"}
            assert payload["tools"][0]["function"]["name"] == "search_knowledge_base"
            return chat({"tool_calls": [
                {"index": index, "id": f"tool-{index}", "type": "function",
                 "function": {"name": "search_knowledge_base", "arguments": '{"query":"Saturday hours"}'}}
                for index in range(2)
            ]}, "tool_calls")
        assert not payload.get("tools")
        assert any(item["role"] == "tool" and "09:45" in item["content"] for item in payload["messages"])
        return chat({"content": json.dumps(OUTPUT)})

    async def search(query):
        searches.append(query)
        await asyncio.sleep(0)
        return [{"source_id": "source-1", "text": "09:45"}]

    model = LangChainAnswerModel(LlmSettings(api_key="a" * 32), transport=httpx.MockTransport(handle))
    model.set_search(search)
    try:
        assert await model.generate("What time?", [], request_id="question") == OUTPUT
    finally:
        await model.aclose()
    assert searches == ["Saturday hours"]
    assert reservations == [("deepseek", "deepseek-flash", 1024)] * 2


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [302, 401])
async def test_custom_provider_never_retries_redirects_or_bad_keys(status):
    seen = []

    async def handle(request):
        seen.append(request.url.host)
        return httpx.Response(status, headers={"Location": "https://private.example.com"}, json={"error": "secret"})

    model = LangChainAnswerModel(model_config(), transport=httpx.MockTransport(handle))
    try:
        with pytest.raises(ProcessingError, match="AI_PROCESSING_FAILED"):
            await model.generate("question", [], request_id="question")
    finally:
        await model.aclose()
    assert seen == ["provider.example.com"]


@pytest.mark.asyncio
async def test_probe_falls_back_to_text_when_provider_rejects_tools():
    calls = []

    async def handle(request):
        calls.append(json.loads(request.content))
        if len(calls) == 1:
            return httpx.Response(400, json={"error": {"message": "unsupported tools"}})
        return chat({"content": "READY"})

    model = LangChainAnswerModel(model_config(), transport=httpx.MockTransport(handle), probe=True)
    try:
        assert await model.probe_capabilities() is False
    finally:
        await model.aclose()
    assert calls[0].get("tools") and not calls[1].get("tools")


@pytest.mark.asyncio
async def test_cancellation_interrupts_the_provider_request():
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    async def handle(_request):
        entered.set()
        try:
            await asyncio.Future()
        finally:
            cancelled.set()

    model = LangChainAnswerModel(model_config(), transport=httpx.MockTransport(handle))
    try:
        task = asyncio.create_task(model.generate("question", [], request_id="question"))
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cancelled.is_set()
    finally:
        await model.aclose()


@pytest.mark.asyncio
async def test_supplemental_retrieval_keeps_the_snapshot_and_rejects_outside_chunks():
    authorized = {"document_id": "document", "content_version_id": "content", "index_version_id": "index"}
    scope = {"indexes": [authorized]}
    evidence = [{**authorized, "chunk_id": "one", "source_id": "source-1", "text_content": "First"}]

    class Model:
        def set_search(self, search):
            self.search = search

    class Retriever:
        async def retrieve(self, query, actual_scope, request_id, *, deadline):
            assert actual_scope is scope and request_id == "request" and deadline == 10
            if query == "outside":
                return [{**authorized, "index_version_id": "other"}]
            return [{**evidence[0], "source_id": "duplicate"},
                    {**authorized, "chunk_id": "two", "source_id": "source-2", "text_content": "Second"}]

    service = AnswerService("unused", None, llm_factory=Model, retriever=Retriever())
    model = service._generation_model({"scope": scope, "request_id": "request"}, evidence, 10)
    assert await model.search("inside") == [{"source_id": "source-2", "text": "Second"}]
    with pytest.raises(ProcessingError):
        await model.search("outside")
    assert [item["source_id"] for item in evidence] == ["source-1", "source-2"]


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "100.64.0.1", "198.18.0.1",
                               "168.63.129.16", "192.0.0.9",
                               "::1", "::ffff:8.8.8.8", "64:ff9b::a9fe:a9fe", "fc00::1", "fe80::1", "ff02::1"])
def test_proxy_rejects_private_and_special_ips(ip):
    assert not model_egress.allowed_address(ip)


@pytest.mark.asyncio
async def test_proxy_checks_all_answers_and_dials_the_checked_numeric_ip(monkeypatch):
    records = ["8.8.8.8", "127.0.0.1"]
    connects = []

    async def lookup(host, port, **_):
        assert host == "public.example.com."
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, port)) for ip in records]

    async def connect(host, port, **options):
        connects.append((host, port, options["flags"]))
        return (None, None)

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", lookup)
    monkeypatch.setattr(asyncio, "open_connection", connect)
    with pytest.raises(ValueError):
        await model_egress.connect_public("public.example.com", ())
    assert connects == []
    records[:] = ["8.8.8.8"]
    await model_egress.connect_public("public.example.com", ())
    assert connects == [("8.8.8.8", 443, socket.AI_NUMERICHOST)]
