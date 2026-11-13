"""Shared retry semantics through the pinned SDKs, without network or real delays."""
import asyncio

import anthropic
import httpx
import httpx2
import openai
import pytest

from knowflow_ai import langchain_answer
from knowflow_ai.adapters import ProcessingError
from knowflow_ai.answering import LlmSettings
from knowflow_ai.provider_retry import (
    ProviderRetryPolicy, classify_provider_failure, run_provider_with_retry,
)
from provider_test_helpers import LangChainAnswerModel, runtime_factory
from test_langchain_models import model_config
from test_provider_completion import fixture_case, wire_bytes, forbid_wire_network


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    forbid_wire_network(monkeypatch)


@pytest.fixture
def reservations(monkeypatch):
    reserved = []

    async def reserve(provider, model, payload):
        reserved.append((provider, model, payload['max_tokens']))

    monkeypatch.setattr(langchain_answer, 'reserve_provider_call', reserve)
    return reserved


def make_model(monkeypatch, handler, protocol='deepseek', *, runtime=None, sleep=None):
    runtime = runtime or runtime_factory()
    lib = httpx2 if protocol == 'anthropic_messages' else httpx
    settings = LlmSettings(api_key='x' * 40) if protocol == 'deepseek' else model_config(protocol)
    model = LangChainAnswerModel(settings, runtime=runtime, transport=lib.MockTransport(handler))
    delays = []

    async def fake_sleep(delay):
        delays.append(delay)
        runtime.clock.__self__.advance(delay)
        if sleep is not None:
            await sleep(delay)

    async def retry(operation, **kwargs):
        return await run_provider_with_retry(operation, sleep=fake_sleep, **kwargs)

    monkeypatch.setattr(langchain_answer, 'run_provider_with_retry', retry)
    return model, delays


def invoke(model):
    return model._invoke(lambda: model.model.ainvoke([{'role': 'user', 'content': 'synthetic'}]))


def normal(protocol='deepseek'):
    lib = httpx2 if protocol == 'anthropic_messages' else httpx
    return lib.Response(200, headers={'content-type': 'text/event-stream'},
                        content=wire_bytes(fixture_case(protocol, 'normal_stream', True)))


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [301, 302, 307, 308, 400, 401, 403, 404, 408, 422, 429, 500, 501, 505, 599])
async def test_langchain_retry_uses_shared_classification(monkeypatch, reservations, status):
    calls, decisions = [], []
    shared = classify_provider_failure

    def classify(**kwargs):
        decision = shared(**kwargs)
        decisions.append((kwargs, decision))
        return decision

    monkeypatch.setattr(langchain_answer, 'classify_provider_failure', classify)

    def handler(request):
        calls.append(request)
        return httpx.Response(status, headers={'Retry-After': '0'}, json={'error': 'SECRET'})

    model, delays = make_model(monkeypatch, handler)
    try:
        with pytest.raises(ProcessingError) as caught:
            await invoke(model)
        expected = shared(status=status).retryable
        assert (caught.value.code, caught.value.status, caught.value.retryable) == ('AI_PROCESSING_FAILED', 502, expected)
        assert len(calls) == (3 if expected else 1)
        assert len(reservations) == len(calls) and len(delays) == len(calls) - 1
        # Redirects are rejected in the response hook before the SDK handles them.
        assert status < 400 or any(args['status'] == status for args, _ in decisions)
        assert not model.runtime.users and not model.runtime.models
    finally:
        await model.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize('protocol', ['chat_completions', 'anthropic_messages', 'responses'])
@pytest.mark.parametrize('failure', [429, 503, 'reset', 'timeout'])
async def test_custom_models_never_retry(monkeypatch, reservations, protocol, failure):
    lib = httpx2 if protocol == 'anthropic_messages' else httpx
    calls = []

    def handler(request):
        calls.append(request)
        if failure == 'reset':
            raise lib.ReadError('SECRET', request=request)
        if failure == 'timeout':
            raise lib.ReadTimeout('SECRET', request=request)
        return lib.Response(failure, headers={'Retry-After': '0'}, json={'error': 'SECRET'})

    model, delays = make_model(monkeypatch, handler, protocol)
    try:
        assert model.retry_policy is None and model.model.max_retries == 0
        with pytest.raises(ProcessingError) as caught:
            await invoke(model)
        assert (caught.value.code, caught.value.status) == (
            ('PROCESSING_TIMEOUT', 504) if failure == 'timeout' else ('AI_PROCESSING_FAILED', 502))
        assert len(calls) == 1 and not delays and not reservations
        assert 'SECRET' not in str(caught.value)
    finally:
        await model.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['reset', 'connect', 'connect_timeout', 'read_timeout', 'invalid_url',
                                     'unsupported', 'encoding', 'local_protocol', 'transport', 'pool_timeout', 'write_timeout'])
@pytest.mark.parametrize('wrapper', ['httpx', 'openai', 'httpx2', 'anthropic'])
async def test_retry_classification_table(monkeypatch, reservations, failure, wrapper):
    # SDK wrappers must preserve underlying local/decoding failures as final.
    lib = httpx2 if wrapper in ('httpx2', 'anthropic') else httpx
    errors = {'reset': lib.ReadError, 'connect': lib.ConnectError,
              'connect_timeout': lib.ConnectTimeout, 'read_timeout': lib.ReadTimeout,
              'invalid_url': lib.InvalidURL, 'unsupported': lib.UnsupportedProtocol,
              'encoding': lib.DecodingError, 'local_protocol': lib.LocalProtocolError,
              'transport': lib.TransportError, 'pool_timeout': lib.PoolTimeout, 'write_timeout': lib.WriteTimeout}
    calls = []
    model, delays = make_model(monkeypatch, lambda request: normal())

    async def operation():
        calls.append(True)
        cause = errors[failure]('SECRET')
        if wrapper in ('openai', 'anthropic'):
            sdk = openai if wrapper == 'openai' else anthropic
            error_type = sdk.APITimeoutError if failure.endswith('timeout') else sdk.APIConnectionError
            raise error_type(request=lib.Request('POST', 'https://provider.example.test')) from cause
        raise cause

    try:
        with pytest.raises(ProcessingError) as caught:
            await model._invoke(operation)
        transient = failure in ('reset', 'connect', 'connect_timeout', 'read_timeout')
        assert len(calls) == (3 if transient else 1) and len(delays) == len(calls) - 1
        assert caught.value.retryable is transient
        assert caught.value.status == (504 if failure.endswith('timeout') else 502)
        assert 'SECRET' not in str(caught.value)
    finally:
        await model.aclose()


class InterruptedStream(httpx.AsyncByteStream):
    def __init__(self, prefix, failure):
        self.prefix, self.failure, self.closed = prefix, failure, asyncio.Event()

    async def __aiter__(self):
        yield self.prefix
        raise self.failure('SECRET')

    async def aclose(self):
        self.closed.set()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', [httpx.ReadError, httpx.ReadTimeout])
@pytest.mark.parametrize('content', [False, True], ids=['heartbeat-only', 'provider-content'])
async def test_provider_output_started_blocks_retry(monkeypatch, reservations, failure, content):
    prefix = (b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n' if content else b': heartbeat\n\n')
    stream = InterruptedStream(prefix, failure)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, headers={'content-type': 'text/event-stream'}, stream=stream) if len(calls) == 1 else normal()

    model, delays = make_model(monkeypatch, handler)
    try:
        if content:
            with pytest.raises(ProcessingError):
                await invoke(model)
        else:
            assert (await invoke(model)).text
        assert len(calls) == (1 if content else 2) and len(delays) == len(calls) - 1
        assert stream.closed.is_set() and len(reservations) == len(calls)
    finally:
        await model.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', [429, 599, 'reset', 'timeout'])
async def test_client_output_started_blocks_retry_even_for_transient_error(monkeypatch, reservations, failure):
    calls = []
    model, delays = make_model(monkeypatch, lambda request: normal())

    async def operation():
        calls.append(True)
        model._attempt.get().mark_client_output_started()
        if failure == 'reset':
            raise httpx.ReadError('SECRET')
        if failure == 'timeout':
            raise httpx.ReadTimeout('SECRET')
        raise openai.APIStatusError('SECRET', response=httpx.Response(failure,
                                   request=httpx.Request('POST', 'https://provider.example.test')), body=None)

    try:
        with pytest.raises(ProcessingError):
            await model._invoke(operation)
        assert len(calls) == 1 and not delays
    finally:
        await model.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize('client', [False, True])
async def test_output_flag_is_rechecked_after_retry_delay(monkeypatch, reservations, client):
    states, calls = [], []

    async def sleep(delay):
        if client:
            states[-1].mark_client_output_started()
        else:
            states[-1].observe_content()

    model, delays = make_model(monkeypatch, lambda request: normal(), sleep=sleep)

    async def operation():
        calls.append(True)
        states.append(model._attempt.get())
        raise httpx.ConnectError('SECRET')

    try:
        with pytest.raises(ProcessingError):
            await model._invoke(operation)
        assert calls == [True] and delays == [0.5]
    finally:
        await model.aclose()


@pytest.mark.asyncio
async def test_retry_deadline_never_extends_model_total_deadline(monkeypatch, reservations):
    runtime = runtime_factory(total=2)
    calls = []

    def handler(request):
        calls.append(runtime.clock())
        return httpx.Response(429, headers={'Retry-After': '1'})

    model, delays = make_model(monkeypatch, handler, runtime=runtime)
    model.retry_policy = ProviderRetryPolicy(total_seconds=60)
    try:
        with pytest.raises(ProcessingError) as caught:
            await invoke(model)
        assert caught.value.status == 502  # Preserve the provider HTTP mapping.
        assert calls == [0, 1] and delays == [1] and runtime.clock() == 1
        assert not runtime.deadline_runner.pending
    finally:
        await model.aclose()


@pytest.mark.asyncio
async def test_each_builtin_attempt_reserves_budget_once(monkeypatch, reservations):
    calls = []

    def handler(request):
        calls.append(request)
        return normal() if len(calls) % 3 == 0 else httpx.Response(503)

    model, delays = make_model(monkeypatch, handler)
    try:
        assert model.model.max_retries == 0
        assert (await invoke(model)).text
        assert (await invoke(model)).text
        assert len(calls) == 6 and reservations == [('deepseek', 'deepseek-flash', 1024)] * 6
        assert len(delays) == 4
    finally:
        await model.aclose()


@pytest.mark.asyncio
async def test_half_open_probe_has_one_attempt_even_with_default_retry_policy(monkeypatch, reservations):
    runtime, calls = runtime_factory(failure_threshold=1), []

    def handler(request):
        calls.append(request)
        return httpx.Response(503)

    model, delays = make_model(monkeypatch, handler, runtime=runtime)
    try:
        assert model.retry_policy == ProviderRetryPolicy()
        with pytest.raises(ProcessingError):
            await invoke(model)
        assert len(calls) == 3
        with pytest.raises(ProcessingError) as caught:
            await invoke(model)
        assert caught.value.retry_reason == 'circuit_open' and len(reservations) == 3
        runtime.clock.__self__.advance(runtime.limits.cooldown)
        with pytest.raises(ProcessingError):
            await invoke(model)
        assert len(calls) == len(reservations) == 4 and len(delays) == 2
        assert not runtime.users and not runtime.models
    finally:
        await model.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize('library', [httpx, httpx2])
@pytest.mark.parametrize('status', [408, 429, 501, 599])
async def test_http_status_error_uses_shared_classification(monkeypatch, reservations, library, status):
    calls = []
    model, delays = make_model(monkeypatch, lambda request: normal())

    async def operation():
        calls.append(True)
        response = library.Response(status, request=library.Request('POST', 'https://provider.example.test'))
        response.raise_for_status()

    try:
        with pytest.raises(ProcessingError) as caught:
            await model._invoke(operation)
        assert caught.value.status == 502 and caught.value.provider_status == status
        assert len(calls) == (1 if status == 408 else 3) and len(delays) == len(calls) - 1
    finally:
        await model.aclose()
