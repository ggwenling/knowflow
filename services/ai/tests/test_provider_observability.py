"""Physical-attempt accounting and whole-log redaction with offline SDK replays."""
import asyncio
import importlib
import json
import logging
from pathlib import Path
import re
from types import SimpleNamespace

import httpx
import httpx2
import pytest

from knowflow_ai import langchain_answer
from knowflow_ai.adapters import ProcessingError
from knowflow_ai.answering import LlmSettings
from knowflow_ai.langchain_answer import LangChainAnswerModel as ProductionModel
from knowflow_ai.provider_observability import (
    FAILURE_CATEGORIES, install_safe_logging, normalize_usage,
)
from knowflow_ai.provider_retry import ProviderRetryPolicy
from provider_test_helpers import LangChainAnswerModel, call_context, runtime_factory, ControlledByteStream
from test_langchain_models import model_config, chat, OUTPUT
from test_provider_completion import PROTOCOLS, fixture_case, wire_bytes, forbid_wire_network, TOOL_SCHEMA

REQUIRED = {'event', 'request_id', 'protocol', 'model_id', 'duration_ms', 'first_token_latency_ms',
            'first_token_observation', 'token_usage', 'outcome', 'failure_category',
            'call_id', 'attempt', 'purpose', 'provider_called'}
SECRETS = ('sk-SENTINEL-PRIVATE-KEY-0123456789abcdef', 'PRIVATE_PROMPT', 'PRIVATE_EVIDENCE', 'PRIVATE_COMPLETION',
           'PRIVATE_TOOL_ARGS', 'PRIVATE_PROVIDER_ERROR', 'https://private-provider.example.com/prefix',
           'PRIVATE_USER:PRIVATE_PASSWORD', 'https://private-proxy.example.com',
           'fixture-key', 'https://provider.example.com/prefix', 'https://api.deepseek.com')


@pytest.fixture(autouse=True)
def offline(monkeypatch, caplog):
    forbid_wire_network(monkeypatch)
    caplog.set_level(logging.DEBUG)
    async def reserve(*args):
        pass
    monkeypatch.setattr(langchain_answer, 'reserve_provider_call', reserve)


def records(caplog):
    rows = []
    for record in caplog.records:
        assert not record.getMessage().startswith('llm_call ')
        if record.name == 'knowflow_ai.provider_observability':
            row = json.loads(record.getMessage())
            assert set(row) == REQUIRED
            assert row['event'] == 'llm_call'
            assert row['failure_category'] in FAILURE_CATEGORIES | {None}
            assert row['outcome'] == ('success' if row['failure_category'] is None else 'failure')
            assert type(row['duration_ms']) is int and row['duration_ms'] >= 0
            assert len(row['call_id']) == 32
            assert record.exc_info is None
            rows.append(row)
    for secret in SECRETS:
        assert secret not in caplog.text
    return rows


def make_model(protocol='chat_completions', *, handler=None, runtime=None, settings=None, probe=False):
    settings = settings or (LlmSettings(api_key=SECRETS[0]) if protocol == 'deepseek' else model_config(protocol))
    lib = httpx2 if protocol == 'anthropic_messages' else httpx
    if handler is None:
        case = fixture_case(protocol, 'normal_stream', True)
        handler = lambda _: lib.Response(200, headers={'content-type': 'text/event-stream'}, content=wire_bytes(case))
    model = LangChainAnswerModel(settings, runtime=runtime, transport=lib.MockTransport(handler), probe=probe)
    model.retry_policy = ProviderRetryPolicy(max_attempts=1, base_seconds=0)
    return model


def invoke(model):
    return model._invoke(lambda: model.model.ainvoke([{'role': 'user', 'content': SECRETS[1]}]))


@pytest.mark.asyncio
@pytest.mark.parametrize('protocol', PROTOCOLS)
@pytest.mark.parametrize('failure', [None, 'auth', 'model_mismatch', 'length_truncation', 'content_filter', 'invalid_completion'])
async def test_call_log_has_required_structured_fields(protocol, failure, caplog):
    lib = httpx2 if protocol == 'anthropic_messages' else httpx
    if failure == 'auth':
        handler = lambda _: lib.Response(401, json={'error': {'message': SECRETS[5]}})
    elif failure:
        fixture_id = {'model_mismatch': 'wrong_model_id', 'invalid_completion': 'missing_terminator'}.get(failure, failure)
        case = fixture_case(protocol, fixture_id, True)
        handler = lambda _: lib.Response(200, headers={'content-type': case['content_type']}, content=wire_bytes(case))
    else:
        handler = None
    model = make_model(protocol, handler=handler)
    try:
        if failure:
            with pytest.raises(ProcessingError):
                await invoke(model)
        else:
            assert (await invoke(model)).text
    finally:
        await model.aclose()
    row, = records(caplog)
    assert row['protocol'] == protocol and row['request_id'] == 'provider-test'
    assert row['model_id'] == model.model_id
    assert (row['attempt'], row['provider_called'], row['purpose']) == (1, True, 'answer')
    assert row['failure_category'] == failure
    if failure == 'auth':
        assert row['first_token_observation'] is row['first_token_latency_ms'] is None
    elif not failure:
        assert row['first_token_observation'] == 'content_event'
        assert type(row['first_token_latency_ms']) is int
        assert row['token_usage'] == fixture_case(protocol, 'normal_stream', True)['expected_usage']


@pytest.mark.asyncio
async def test_one_call_log_per_attempt_including_tools_retry_repair_and_probe(caplog):
    calls = []
    def handle(request):
        calls.append(json.loads(request.content))
        if len(calls) == 1:
            return httpx.Response(503, json={'error': {'message': SECRETS[5]}})
        if len(calls) == 2:
            return chat({'tool_calls': [{'index': 0, 'id': 'tool-1', 'type': 'function',
                         'function': {'name': 'search_knowledge_base',
                                      'arguments': json.dumps({'query': SECRETS[4]})}}]},
                        'tool_calls', model_id='deepseek-flash')
        return chat({'content': json.dumps({**OUTPUT, 'answer': SECRETS[3]})}, model_id='deepseek-flash')
    model = make_model('deepseek', handler=handle)
    model.retry_policy = ProviderRetryPolicy(max_attempts=3, base_seconds=0)
    async def search(query):
        assert query == SECRETS[4]
        return [{'source_id': 'source-1', 'text': SECRETS[2]}]
    model.set_search(search)
    try:
        await model.generate(SECRETS[1], [], request_id='unused')
        await model.generate_repair(SECRETS[1], [], OUTPUT, request_id='unused')
    finally:
        await model.aclose()
    rows = records(caplog)
    assert len(rows) == len(calls) == 4
    assert [row['attempt'] for row in rows] == [1, 2, 1, 1]
    assert [row['purpose'] for row in rows] == ['answer', 'answer', 'answer', 'repair']
    assert rows[0]['call_id'] == rows[1]['call_id']
    assert len({row['call_id'] for row in rows}) == 3
    caplog.clear()
    for tools in (False, True):
        calls.clear()
        def probe_handler(request):
            calls.append(json.loads(request.content))
            if len(calls) == 1:
                if not tools:
                    return httpx.Response(400, json={'error': {'message': SECRETS[5]}})
                return chat({'tool_calls': [{'index': 0, 'id': 'ready-1', 'type': 'function',
                             'function': {'name': 'report_ready', 'arguments': '{}'}}]}, 'tool_calls')
            return chat({'content': 'READY'})
        model = make_model(handler=probe_handler, probe=True)
        try:
            assert await model.probe_capabilities() is tools
        finally:
            await model.aclose()
        rows = records(caplog)
        assert len(rows) == len(calls) == 2
        assert all(row['purpose'] == 'probe' and row['request_id'] == 'provider-test' for row in rows)
        assert len({row['call_id'] for row in rows}) == 2
        caplog.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize('protocol', PROTOCOLS)
@pytest.mark.parametrize('streaming', [False, True])
async def test_first_token_latency_comes_from_wire_not_buffered_sdk_callback(protocol, streaming, caplog):
    runtime = runtime_factory()
    clock = runtime.clock.__self__
    lib = httpx2 if protocol == 'anthropic_messages' else httpx
    case = fixture_case(protocol, 'normal_stream' if streaming else 'normal_non_stream', streaming)
    body = wire_bytes(case)
    class TimedWire(lib.AsyncByteStream):
        async def __aiter__(self):
            clock.advance(0.125)
            yield body if streaming else body[:1]
            clock.advance(0.875)
            if not streaming:
                yield body[1:]
    model = make_model(protocol, runtime=runtime, handler=lambda _: lib.Response(
        200, headers={'content-type': case['content_type']}, stream=TimedWire()))
    model.model.streaming = streaming
    async def parse():
        result = await model.model.ainvoke([{'role': 'user', 'content': SECRETS[1]}])
        clock.advance(0.5)  # SDK-side work after the entire response was buffered.
        return result
    try:
        await model._invoke(parse)
    finally:
        await model.aclose()
    row, = records(caplog)
    assert row['first_token_latency_ms'] == 125
    assert row['duration_ms'] == 1500
    assert row['first_token_observation'] == ('content_event' if streaming else 'body_byte')


@pytest.mark.asyncio
@pytest.mark.parametrize('empty_success', [False, True])
async def test_missing_usage_and_first_token_are_null(empty_success, caplog):
    model = make_model(handler=lambda _: chat({'content': ''}) if empty_success else httpx.Response(
        400, json={'error': {'message': SECRETS[5]}}))
    try:
        if empty_success:
            await invoke(model)
        else:
            with pytest.raises(ProcessingError):
                await invoke(model)
    finally:
        await model.aclose()
    row, = records(caplog)
    assert row['token_usage'] is None
    assert row['first_token_latency_ms'] is None and row['first_token_observation'] is None


@pytest.mark.asyncio
async def test_usage_is_numeric_allowlist_and_is_reset_between_attempts(caplog):
    assert normalize_usage({'input_tokens': True, 'output_tokens': -1, 'total_tokens': '7',
                            'private': SECRETS[3]}) is None
    calls = []
    def handle(request):
        calls.append(request)
        if len(calls) == 2:
            return httpx.Response(503, json={'error': {'message': SECRETS[5]}})
        return chat({'content': json.dumps(OUTPUT)}, model_id='deepseek-flash')
    model = make_model('deepseek', handler=handle)
    model.retry_policy = ProviderRetryPolicy(max_attempts=2, base_seconds=0)
    async def successful_usage():
        result = await model.model.ainvoke([{'role': 'user', 'content': SECRETS[1]}])
        return SimpleNamespace(usage_metadata={'input_tokens': 8, 'output_tokens': 3, 'total_tokens': 11,
                                              'nested': {'secret': SECRETS[3]}})
    try:
        await model._invoke(successful_usage)
        await invoke(model)
        assert model.last_usage is None
    finally:
        await model.aclose()
    first, failed, retry = records(caplog)
    assert first['token_usage'] == {'input_tokens': 8, 'output_tokens': 3, 'total_tokens': 11}
    assert failed['token_usage'] is retry['token_usage'] is None
    assert failed['call_id'] == retry['call_id'] and [failed['attempt'], retry['attempt']] == [1, 2]


@pytest.mark.asyncio
@pytest.mark.parametrize('protocol', PROTOCOLS)
@pytest.mark.parametrize('failure', [False, True])
async def test_caplog_excludes_key_url_credentials_prompt_completion_and_tool_args(protocol, failure, caplog):
    lib = httpx2 if protocol == 'anthropic_messages' else httpx
    settings = (LlmSettings(api_key=SECRETS[0]) if protocol == 'deepseek'
                else model_config(protocol).model_copy(update={'base_url': SECRETS[6], 'api_key':
                    langchain_answer.SecretStr(SECRETS[0])}))
    case = fixture_case(protocol, 'tool_call', True)
    # Payload sent through the actual SDK carries prompt and tool arguments.
    body = wire_bytes(case).replace('索引 READY'.encode(), SECRETS[4].encode())
    if failure:
        handler = lambda _: lib.Response(403, json={'error': {'message': SECRETS[5] + SECRETS[0]}})
    else:
        handler = lambda _: lib.Response(200, headers={'content-type': 'text/event-stream'}, content=body)
    model = make_model(protocol, handler=handler, settings=settings)
    async def call():
        return await model.model.bind_tools([TOOL_SCHEMA]).ainvoke([
            {'role': 'user', 'content': SECRETS[1] + SECRETS[2]},
            {'role': 'assistant', 'content': SECRETS[3]}])
    try:
        if failure:
            with pytest.raises(ProcessingError):
                await model._invoke(call)
        else:
            result = await model._invoke(call)
            assert result.tool_calls[0]['args']['query'] == SECRETS[4]
    finally:
        await model.aclose()
    assert len(records(caplog)) == 1


def test_sdk_debug_logs_cannot_emit_provider_payloads(caplog):
    install_safe_logging()
    install_safe_logging()  # Idempotent across app/model construction.
    # Discover the pinned packages' actual sources, independently of our filter list.
    names = set()
    for module_name in ('openai._base_client', 'openai._response', 'openai._legacy_response',
                        'anthropic._base_client', 'anthropic._response', 'anthropic._tracing',
                        'httpx._client', 'httpx2._client'):
        module = importlib.import_module(module_name)
        names.add((module.log if hasattr(module, 'log') else module.logger).name)
    for package_name in ('httpcore', 'httpcore2'):
        root = Path(importlib.import_module(package_name).__file__).parent
        for source in root.rglob('*.py'):
            names.update(re.findall(r'logging.getLogger\(["\']([^"\']+)["\']\)', source.read_text()))
    assert {'httpcore.http11', 'httpcore2.http11', 'httpcore.proxy', 'httpcore2.socks'} <= names
    for name in names:
        logger = logging.getLogger(name)
        caplog.set_level(logging.DEBUG, logger=name)
        logger.debug('Authorization: %s x-api-key: %s body=%s url=%s proxy=%s',
                     SECRETS[0], SECRETS[0], SECRETS[1:6], SECRETS[7], SECRETS[8])
        logger.info('request %s', SECRETS[6])
    logging.getLogger('knowflow_ai.safe_test').info('safe own event')
    assert 'safe own event' in caplog.text
    assert not records(caplog)
    assert not any(record.name in names for record in caplog.records)


@pytest.mark.parametrize('fault', ['destination', 'proxy', 'constructor'])
def test_rejected_destination_and_constructor_failure_are_sanitized(fault, monkeypatch, caplog):
    settings = model_config().model_copy(update={'base_url':
        'https://' + SECRETS[7] + '@private-provider.example.com/prefix'}) if fault == 'destination' else model_config()
    if fault == 'proxy':
        monkeypatch.delenv('KNOWFLOW_CUSTOM_LLM_PROXY', raising=False)
    if fault == 'constructor':
        def broken(**kwargs):
            raise ValueError(SECRETS[0] + SECRETS[5])
        monkeypatch.setattr(langchain_answer, 'ChatOpenAI', broken)
    with pytest.raises((ProcessingError, ValueError)):
        ProductionModel(settings, runtime=runtime_factory(), call_context=call_context(settings),
                        transport=None if fault == 'proxy' else httpx.MockTransport(lambda _: chat({})))
    row, = records(caplog)
    assert (row['attempt'], row['provider_called'], row['failure_category']) == (0, False, 'configuration')


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['cancelled', 'busy', 'circuit_open', 'first_token_timeout', 'total_timeout', 'budget', 'route_answer', 'route_stream', 'route_probe'])
async def test_cancel_busy_and_open_circuit_emit_one_safe_failure_record(kind, monkeypatch, caplog):
    if kind.startswith('route_'):
        from knowflow_ai.app import create_app
        from knowflow_ai.config import Settings
        from test_service import SECRET, AUTH
        from test_answering import _request
        from provider_test_helpers import OWNER
        monkeypatch.setenv('KNOWFLOW_CUSTOM_LLM_ENABLED', 'true')
        monkeypatch.setenv('EMBEDING_KEY', 'e' * 40)
        monkeypatch.setenv('DEEPSEEK_API_KEY', 'd' * 40)
        app = create_app(Settings(SECRET, ai_database_url='unused'))
        app.state.question_admission.custom_active = app.state.question_admission.custom_limit
        config = model_config()
        connection = {**config.model_dump(mode='json'), 'api_key': SECRETS[0]}
        payload = _request()
        payload['scope']['owner_id'] = str(OWNER)
        if kind == 'route_probe':
            path, body = '/internal/v1/llm-models/probe', connection
        else:
            path = '/internal/v1/custom-answers' + ('/stream' if kind == 'route_stream' else '')
            body = {'request': payload, 'model': connection}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
            response = await client.post(path, json=body, headers={**AUTH, 'X-Request-ID': payload['request_id'],
                                         'X-KnowFlow-Owner-ID': str(OWNER)})
            assert response.status_code == 429
        row, = records(caplog)
        assert (row['attempt'], row['provider_called'], row['failure_category']) == (0, False, 'busy')
        assert row['purpose'] == ('probe' if kind == 'route_probe' else 'answer')
        assert row['request_id'] == payload['request_id']
        return
    runtime = runtime_factory()
    stream = ControlledByteStream(wire_bytes(fixture_case('chat_completions', 'normal_stream', True))
                                  if kind == 'total_timeout' else b'')
    model = make_model(runtime=runtime, handler=lambda _: httpx.Response(
        200, headers={'content-type': 'text/event-stream'}, stream=stream))
    if kind == 'busy':
        runtime.users[(model.call_context.owner_id, True)] = runtime.limits.per_user
    elif kind == 'circuit_open':
        token = runtime._breaker_token(model.model_key)
        runtime._open(token.entry)
        runtime.settle(token, 'neutral')
    elif kind == 'budget':
        await model.aclose()
        model = make_model('deepseek', runtime=runtime)
        async def reject(*args):
            raise ProcessingError('RESOURCE_LIMIT', 503, retryable=False)
        monkeypatch.setattr(langchain_answer, 'reserve_provider_call', reject)
    task = asyncio.create_task(invoke(model))
    try:
        if kind in ('cancelled', 'first_token_timeout', 'total_timeout'):
            await asyncio.wait_for(stream.entered.wait(), 2)
            if kind == 'cancelled':
                task.cancel()
            else:
                await runtime.deadline_runner.advance(25 if kind == 'total_timeout' else 10)
        with pytest.raises(asyncio.CancelledError if kind == 'cancelled' else ProcessingError):
            await asyncio.wait_for(task, 2)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await model.aclose()
    row, = records(caplog)
    assert row['failure_category'] == kind
    rejected = kind in ('busy', 'circuit_open', 'budget')
    assert row['attempt'] == (0 if rejected else 1)
    assert row['provider_called'] is not rejected
    if kind not in ('busy',):
        assert not runtime.users and not runtime.models


@pytest.mark.asyncio
@pytest.mark.parametrize('model_id', [SECRETS[0], 'sk-looks-like-a-key', 'https://user:password@host/model',
                                      'user:password@host', 'user@host', 'model\nFORGED_LOG', 'model\x1b[31m', 'x' * 161])
async def test_model_id_cannot_echo_key_or_inject_log_lines(model_id, caplog):
    settings = model_config().model_copy(update={'model_id': model_id, 'api_key': langchain_answer.SecretStr(SECRETS[0])})
    model = make_model(settings=settings, handler=lambda _: httpx.Response(401, json={'error': SECRETS[5]}))
    try:
        with pytest.raises(ProcessingError):
            await invoke(model)
    finally:
        await model.aclose()
    row, = records(caplog)
    assert row['model_id'] == '[redacted]'
    assert model_id not in caplog.text
    assert 'FORGED_LOG' not in caplog.text
