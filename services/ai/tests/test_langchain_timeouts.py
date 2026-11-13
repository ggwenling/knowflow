import asyncio
from dataclasses import replace
from types import SimpleNamespace

import httpx
import httpx2
import pytest

from knowflow_ai.adapters import ProcessingError
from knowflow_ai.answering import LlmSettings
from knowflow_ai.provider_retry import ProviderRetryPolicy
from knowflow_ai.provider_completion import CompletionObserver
from knowflow_ai.provider_runtime import TurnState, BreakerToken, Breaker
from provider_test_helpers import (
    LangChainAnswerModel, runtime_factory, call_context, ControlledByteStream,
)
from test_langchain_models import model_config
from test_provider_completion import fixture_case, wire_bytes, PROTOCOLS, forbid_wire_network, TOOL_SCHEMA


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    forbid_wire_network(monkeypatch)
    async def reserve(*args, **kwargs):
        pass
    monkeypatch.setattr('knowflow_ai.langchain_answer.reserve_provider_call', reserve)


def setup(protocol, stream=None, *, handler=None, streaming=True):
    runtime = runtime_factory()
    settings = LlmSettings(api_key='x' * 40) if protocol == 'deepseek' else model_config(protocol)
    lib = httpx2 if protocol == 'anthropic_messages' else httpx
    if handler is None:
        async def handler(request):
            return lib.Response(200, headers={'content-type': 'text/event-stream' if streaming else 'application/json'},
                                stream=stream)
    model = LangChainAnswerModel(settings, runtime=runtime, transport=lib.MockTransport(handler))
    model.retry_policy = ProviderRetryPolicy(max_attempts=1, base_seconds=0)
    model.model.streaming = streaming
    return runtime, model


def operation(model):
    return lambda: model.model.ainvoke([{'role': 'user', 'content': 'synthetic'}])


async def expect_timeout(task, kind):
    with pytest.raises(ProcessingError) as caught:
        await asyncio.wait_for(task, 2)
    assert (caught.value.status, caught.value.code, caught.value.retry_reason) == (504, 'PROCESSING_TIMEOUT', kind)


@pytest.mark.asyncio
@pytest.mark.parametrize('protocol', PROTOCOLS)
async def test_connect_timeout_is_bounded(protocol):
    lib = httpx2 if protocol == 'anthropic_messages' else httpx
    calls = []
    def handle(request):
        calls.append(request)
        assert request.extensions['timeout'] == {'connect': 3, 'read': 25, 'write': 25, 'pool': 25}
        raise lib.ConnectTimeout('SECRET', request=request)
    runtime, model = setup(protocol, handler=handle)
    try:
        await expect_timeout(asyncio.create_task(model._invoke(operation(model))), 'connect_timeout')
        assert len(calls) == 1
        assert model.http.timeout.connect == 3
        assert not runtime.users and not runtime.models
    finally:
        await model.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize('protocol', PROTOCOLS)
@pytest.mark.parametrize('before_headers', [False, True], ids=['heartbeat-empty-usage', 'no-headers'])
async def test_first_token_deadline_ignores_headers_heartbeats_and_empty_deltas(protocol, before_headers):
    empty = {
        'deepseek': b'data: {"choices":[{"delta":{"content":""}}]}\n\ndata: {"choices":[],"usage":{}}\n\n',
        'chat_completions': b'data: {"choices":[{"delta":{"content":""}}]}\n\ndata: {"choices":[],"usage":{}}\n\n',
        'anthropic_messages': b'data: {"type":"ping"}\n\ndata: {"type":"content_block_delta","delta":{"text":""}}\n\n',
        'responses': b'data: {"type":"response.output_text.delta","delta":""}\n\n',
    }[protocol]
    stream = ControlledByteStream(b': heartbeat\n\n' + empty)
    entered, closed = asyncio.Event(), asyncio.Event()
    lib = httpx2 if protocol == 'anthropic_messages' else httpx
    async def no_headers(request):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            closed.set()
    runtime, model = setup(protocol, stream, handler=no_headers if before_headers else None)
    task = asyncio.create_task(model._invoke(operation(model)))
    try:
        await asyncio.wait_for((entered if before_headers else stream.entered).wait(), 2)
        await runtime.deadline_runner.advance(10)
        await expect_timeout(task, 'first_token_timeout')
        assert (closed if before_headers else stream.closed).is_set()
        assert not runtime.users and not runtime.models
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await model.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize('protocol', PROTOCOLS)
async def test_first_tool_content_satisfies_first_token_deadline(protocol):
    case = fixture_case(protocol, 'tool_call', True)
    stream = ControlledByteStream(wire_bytes(case))
    runtime, model = setup(protocol, stream)
    task = asyncio.create_task(model._invoke(lambda: model.model.bind_tools([TOOL_SCHEMA]).ainvoke(
        [{'role': 'user', 'content': 'synthetic'}])))
    try:
        await asyncio.wait_for(stream.entered.wait(), 2)
        await runtime.deadline_runner.advance(11)
        assert not task.done()
        stream.release.set()
        result = await asyncio.wait_for(task, 2)
        assert result.tool_calls and not runtime.users and not runtime.models
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await model.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize('protocol', PROTOCOLS)
@pytest.mark.parametrize('first_byte', [False, True])
async def test_non_stream_first_body_deadline(protocol, first_byte):
    body = wire_bytes(fixture_case(protocol, 'normal_non_stream', False))
    stream = ControlledByteStream(body[:1] if first_byte else b'', body[1:] if first_byte else body)
    runtime, model = setup(protocol, stream, streaming=False)
    task = asyncio.create_task(model._invoke(operation(model)))
    try:
        await asyncio.wait_for(stream.entered.wait(), 2)
        await runtime.deadline_runner.advance(11)
        if first_byte:
            assert not task.done()
            stream.release.set()
            assert (await asyncio.wait_for(task, 2)).text
        else:
            await expect_timeout(task, 'first_token_timeout')
        assert not runtime.users and not runtime.models
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await model.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize('protocol', PROTOCOLS)
@pytest.mark.parametrize('phase', ['body', 'sdk', 'retry_wait'])
async def test_total_deadline_includes_body_sdk_and_retry_wait(protocol, phase, monkeypatch):
    if phase == 'retry_wait' and protocol != 'deepseek':
        # Custom models have exactly one physical attempt, even on transient errors.
        calls = []
        lib = httpx2 if protocol == 'anthropic_messages' else httpx
        def handle(request):
            calls.append(request)
            return lib.Response(503, json={'error': 'SECRET'})
        runtime, model = setup(protocol, handler=handle)
        try:
            with pytest.raises(ProcessingError):
                await model._invoke(operation(model))
            assert len(calls) == 1
        finally:
            await model.aclose()
        return
    body = wire_bytes(fixture_case(protocol, 'normal_stream', True))
    stream = ControlledByteStream(body)
    runtime, model = setup(protocol, stream)
    entered, cancelled = asyncio.Event(), asyncio.Event()
    async def blocked():
        try:
            entered.set()
            await asyncio.Event().wait()
        finally:
            cancelled.set()
    if phase == 'sdk':
        async def sdk():
            await operation(model)()
            return await blocked()
        invoke = sdk
        stream.release.set()
    elif phase == 'retry_wait':
        async def wait_retry(delay):
            return await blocked()
        monkeypatch.setattr('knowflow_ai.provider_retry.asyncio', SimpleNamespace(sleep=wait_retry))
        model.retry_policy = ProviderRetryPolicy(max_attempts=3)
        async def handle(request):
            return httpx.Response(503, json={'error': 'SECRET'})
        model.http._transport = httpx.MockTransport(handle)
        invoke = operation(model)
    else:
        invoke = operation(model)
    task = asyncio.create_task(model._invoke(invoke))
    try:
        await asyncio.wait_for((stream.entered if phase == 'body' else entered).wait(), 2)
        await runtime.deadline_runner.advance(25)
        await expect_timeout(task, 'total_timeout')
        assert stream.closed.is_set() if phase == 'body' else cancelled.is_set()
        assert not runtime.users and not runtime.models
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await model.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize('protocol', PROTOCOLS)
@pytest.mark.parametrize('cancel', [False, True], ids=['timeout', 'cancel'])
async def test_timeout_and_cancellation_close_stream_and_release_leases(protocol, cancel):
    stream = ControlledByteStream(wire_bytes(fixture_case(protocol, 'normal_stream', True)))
    runtime, model = setup(protocol, stream)
    task = asyncio.create_task(model._invoke(operation(model)))
    try:
        await asyncio.wait_for(stream.entered.wait(), 2)
        if cancel:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            await runtime.deadline_runner.advance(25)
            await expect_timeout(task, 'total_timeout')
        assert stream.closed.is_set()
        assert not runtime.users and not runtime.models and not runtime.deadline_runner.pending
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await model.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize('protocol', PROTOCOLS)
async def test_breaker_counts_final_turn_and_half_open_uses_one_attempt(protocol, monkeypatch):
    lib = httpx2 if protocol == 'anthropic_messages' else httpx
    calls = []
    def handle(request):
        calls.append(request)
        return lib.Response(503, json={'error': 'SECRET'})
    runtime, model = setup(protocol, handler=handle)
    runtime.limits = replace(runtime.limits, failure_threshold=1)
    model.retry_policy = ProviderRetryPolicy(max_attempts=3)
    async def fake_sleep(seconds):
        runtime.clock.__self__.advance(seconds)
    monkeypatch.setattr('knowflow_ai.provider_retry.asyncio', SimpleNamespace(sleep=fake_sleep))
    try:
        with pytest.raises(ProcessingError):
            await model._invoke(operation(model))
        expected = 3 if protocol == 'deepseek' else 1
        assert len(calls) == expected
        breaker = next(iter(runtime.breakers.values()))
        assert breaker.state == 'OPEN' and breaker.failures == 1
        with pytest.raises(ProcessingError) as caught:
            await model._invoke(operation(model))
        assert caught.value.retry_reason == 'circuit_open' and len(calls) == expected
        runtime.clock.__self__.advance(30)
        with pytest.raises(ProcessingError):
            await model._invoke(operation(model))
        assert len(calls) == expected + 1 and breaker.state == 'OPEN' and breaker.failures == 2
    finally:
        await model.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize('protocol', PROTOCOLS)
@pytest.mark.parametrize('preloaded', [False, True])
async def test_provider_error_body_is_bounded_and_closed(protocol, preloaded):
    lib = httpx2 if protocol == 'anthropic_messages' else httpx
    stream = ControlledByteStream(b'X' * (1024 * 1024 + 1))
    stream.release.set()
    responses = []
    def handle(request):
        response = lib.Response(503, content=b'X' * (1024 * 1024 + 1)) if preloaded else lib.Response(503, stream=stream)
        responses.append(response)
        return response
    runtime, model = setup(protocol, handler=handle)
    try:
        with pytest.raises(ProcessingError) as caught:
            await model._invoke(operation(model))
        assert (caught.value.code, caught.value.status, caught.value.retryable) == ('AI_PROCESSING_FAILED', 502, False)
        assert len(responses) == 1 and responses[0].is_closed
        assert not runtime.users and not runtime.models
    finally:
        await model.aclose()
