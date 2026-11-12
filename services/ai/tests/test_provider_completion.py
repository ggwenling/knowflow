"""Offline recorded-wire regressions across the validator, SDKs, and ASGI routes."""
from contextlib import asynccontextmanager
import json
import logging
from pathlib import Path
import socket

import httpx
import httpx2
import pytest

from knowflow_ai.adapters import ProcessingError
from knowflow_ai.answering import AnswerService, LlmSettings
from provider_test_helpers import LangChainAnswerModel
from knowflow_ai.provider_completion import validate_completion
from test_answering import FakeRetriever, _contract, _evidence, _request
from test_langchain_models import model_config


WIRE_ROOT = Path(__file__).parent / 'fixtures' / 'provider_wire'
CASES = json.loads((WIRE_ROOT / 'manifest.json').read_text(encoding='utf-8'))['cases']
PROTOCOLS = ('deepseek', 'chat_completions', 'anthropic_messages', 'responses')
TOOLS = [case for case in CASES if case['expected_category'] == 'tool_call']
ABNORMAL = [case for case in CASES if case['expected_category'] == 'invalid_completion']
STREAM_ABNORMAL = [case for case in ABNORMAL if case['streaming']]
TOOL_SCHEMA = {'name': 'search_knowledge_base', 'description': 'Search synthetic evidence.',
               'strict': True,
               'parameters': {'type': 'object', 'properties': {'query': {'type': 'string'}},
                              'required': ['query']}}


def fixture_case(protocol, fixture_id, streaming):
    return next(case for case in CASES if (case['protocol'], case['fixture_id'], case['streaming'])
                == (protocol, fixture_id, streaming))


def wire_bytes(case):
    return (WIRE_ROOT / case['path']).read_bytes()


def forbid_wire_network(monkeypatch):
    """Scoped to fixture replays; old local-server/process tests keep their sockets."""
    async def reject_http(*args, **kwargs):
        pytest.fail('Recorded-wire test attempted an unmocked HTTP transport', pytrace=False)

    def guarded_connect(original):
        def connect(sock, address):
            # Preserve loopback for test runners; block accidental tracing/sync SDK use.
            if isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1'):
                return original(sock, address)
            pytest.fail('Recorded-wire test attempted an external socket', pytrace=False)
        return connect

    monkeypatch.setattr(socket.socket, 'connect', guarded_connect(socket.socket.connect))
    monkeypatch.setattr(socket.socket, 'connect_ex', guarded_connect(socket.socket.connect_ex))
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', reject_http)
    monkeypatch.setattr(httpx2.AsyncHTTPTransport, 'handle_async_request', reject_http)

    def reject_sync(*args, **kwargs):
        pytest.fail('Recorded-wire test attempted an unmocked sync HTTP transport', pytrace=False)

    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', reject_sync)
    monkeypatch.setattr(httpx2.HTTPTransport, 'handle_request', reject_sync)


@pytest.fixture
def wire_network_guard(monkeypatch):
    forbid_wire_network(monkeypatch)


@pytest.fixture(autouse=True)
def _recorded_tests_are_offline(wire_network_guard):
    pass


@pytest.fixture(autouse=True)
def recorded_budget(monkeypatch):
    """Record the reservation boundary without exercising SQLite's worker thread."""
    from knowflow_ai import langchain_answer
    reservations = []

    async def reserve(provider, model_id, payload):
        reservations.append((provider, model_id, payload['max_tokens']))

    monkeypatch.setattr(langchain_answer, 'reserve_provider_call', reserve)
    return reservations


@asynccontextmanager
async def recorded_model(*replay, fragment_size=None, crlf=False):
    """Serve exact bytes, assert SDK request shape, and account for every POST."""
    first = replay[0]
    library = httpx2 if first['protocol'] == 'anthropic_messages' else httpx
    calls = []

    def handle(request):
        assert len(calls) < len(replay), 'Unexpected retry or extra model turn'
        case = replay[len(calls)]
        payload = json.loads(request.content)
        calls.append(payload)
        assert request.method == 'POST'
        assert request.url.path == case['endpoint']
        assert payload['model'] == case['model_id']
        assert bool(payload.get('stream')) == case['streaming']
        if case['expected_category'] != 'invalid_completion':
            assert bool(payload.get('tools')) == case['allow_tools']
        body = wire_bytes(case)
        if crlf:
            body = body.replace(b'\n', b'\r\n')
        if fragment_size:
            class Fragmented(library.AsyncByteStream):
                async def __aiter__(self):
                    for offset in range(0, len(body), fragment_size):
                        yield body[offset:offset + fragment_size]

            return library.Response(case['http_status'], headers={'content-type': case['content_type']},
                                    stream=Fragmented())
        return library.Response(case['http_status'], headers={'content-type': case['content_type']},
                                content=body)

    settings = (LlmSettings(api_key='synthetic-key-' + 'x' * 32) if first['protocol'] == 'deepseek'
                else model_config(first['protocol'], tools=True))
    model = LangChainAnswerModel(settings, transport=library.MockTransport(handle))
    model.model.streaming = first['streaming']
    try:
        yield model, calls
        assert len(calls) == len(replay)
    finally:
        await model.aclose()
        assert model.http.is_closed


def check_completion(case, *, body=None, allow_tools=None):
    validate_completion(wire_bytes(case) if body is None else body,
                        protocol=case['protocol'],
                        model_id=case['model_id'], streaming=case['streaming'],
                        allow_tools=case['allow_tools'] if allow_tools is None else allow_tools)


def assert_sanitized_error(error, case, caplog):
    assert (error.code, error.status, error.retryable) == ('AI_PROCESSING_FAILED', 502, False)
    assert str(error) == 'AI_PROCESSING_FAILED'
    assert case['sentinel'] not in str(error)
    assert case['sentinel'] not in caplog.text


def test_wire_fixture_matrix_is_complete():
    assert len(CASES) == len({case['id'] for case in CASES}) == 56
    assert len({case['path'] for case in CASES}) == len(CASES)
    sentinels = [case['sentinel'] for case in ABNORMAL]
    assert len(sentinels) == len(set(sentinels)) == 40
    required = {'normal_stream', 'normal_non_stream', 'tool_call', 'missing_terminator',
                'wrong_model_id', 'length_truncation', 'content_filter', 'garbage_body'}
    for protocol in PROTOCOLS:
        cases = [case for case in CASES if case['protocol'] == protocol]
        assert {case['fixture_id'] for case in cases} == required
        assert len(cases) == 14
        for kind in required - {'normal_stream', 'normal_non_stream'}:
            assert {case['streaming'] for case in cases if case['fixture_id'] == kind} == {True, False}
    for case in CASES:
        assert set(case) == {'id', 'fixture_id', 'protocol', 'path', 'endpoint', 'model_id',
                             'streaming', 'allow_tools', 'http_status', 'content_type',
                             'expected_category', 'expected_status', 'expected_result',
                             'expected_usage', 'sentinel'}
        assert type(case['streaming']) is bool and type(case['allow_tools']) is bool
        assert case['id'] == f"{case['protocol']}-{case['fixture_id']}-{'stream' if case['streaming'] else 'non_stream'}"
        assert case['path'].startswith(case['protocol'] + '/')
        assert (WIRE_ROOT / case['path']).resolve().is_relative_to(WIRE_ROOT.resolve())
        assert case['model_id'] == ('deepseek-flash' if case['protocol'] == 'deepseek' else 'test-model')
        assert case['http_status'] == 200
        assert case['content_type'] == ('text/event-stream' if case['streaming'] else 'application/json')
        assert case['allow_tools'] == (case['fixture_id'] == 'tool_call')
        if case['sentinel']:
            assert case['expected_category'] == 'invalid_completion'
            assert case['expected_status'] == 502 and case['expected_result'] is None
            assert case['sentinel'].encode() in wire_bytes(case)
        else:
            assert case['expected_status'] == 200 and case['expected_result']
    files = {path.relative_to(WIRE_ROOT).as_posix() for protocol in PROTOCOLS
             for path in (WIRE_ROOT / protocol).iterdir() if path.is_file()}
    assert files == {case['path'] for case in CASES}


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['id'])
def test_validate_recorded_completion(case, caplog):
    if case['expected_category'] != 'invalid_completion':
        check_completion(case)
    else:
        with pytest.raises(ProcessingError) as caught:
            check_completion(case)
        assert_sanitized_error(caught.value, case, caplog)


@pytest.mark.asyncio
@pytest.mark.parametrize('case', CASES, ids=lambda case: case['id'])
async def test_recorded_wire_through_langchain_sdk(case, caplog, recorded_budget):
    caplog.set_level(logging.INFO)
    async with recorded_model(case) as (model, calls):
        runnable = model.model.bind_tools([TOOL_SCHEMA]) if case['allow_tools'] else model.model
        operation = lambda: runnable.ainvoke([{'role': 'user', 'content': 'Synthetic fixture question'}])
        if case['expected_category'] == 'invalid_completion':
            with pytest.raises(ProcessingError) as caught:
                await model._invoke(operation)
            assert_sanitized_error(caught.value, case, caplog)
        else:
            result = await model._invoke(operation)
            if case['allow_tools']:
                assert result.tool_calls == [{**call, 'type': 'tool_call'}
                                             for call in case['expected_result']['tool_calls']]
                assert not result.invalid_tool_calls
            else:
                assert json.loads(result.text) == case['expected_result']
            assert {key: result.usage_metadata[key] for key in case['expected_usage']} == case['expected_usage']
        assert len(calls) == 1
        assert len(recorded_budget) == (1 if model.default else 0)


@pytest.mark.asyncio
@pytest.mark.parametrize('case', TOOLS, ids=lambda case: case['id'])
async def test_recorded_tool_call_requires_allow_tools(case, caplog):
    check_completion(case, allow_tools=True)
    with pytest.raises(ProcessingError) as caught:
        check_completion(case, allow_tools=False)
    assert (caught.value.status, caught.value.retryable) == (502, False)
    assert str(caught.value) == 'AI_PROCESSING_FAILED'
    # Tool payloads cannot evade the flag by claiming an ordinary text stop.
    wire = wire_bytes(case).replace(b'"finish_reason": "tool_calls"', b'"finish_reason": "stop"')
    wire = wire.replace(b'"stop_reason": "tool_use"', b'"stop_reason": "end_turn"')
    with pytest.raises(ProcessingError):
        check_completion(case, body=wire, allow_tools=False)
    # The response hook derives permission from the actual outbound SDK request.
    async with recorded_model({**case, 'allow_tools': False}) as (model, calls):
        with pytest.raises(ProcessingError) as caught:
            await model._invoke(lambda: model.model.ainvoke([{'role': 'user', 'content': 'No tools'}]))
        assert (caught.value.status, caught.value.retryable) == (502, False)
        assert str(caught.value) == 'AI_PROCESSING_FAILED'
        assert len(calls) == 1
    assert 'WIRE_PRIVATE_' not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize('case', [case for case in TOOLS if case['streaming']], ids=lambda case: case['id'])
async def test_recorded_tool_roundtrip_uses_search_once(case, recorded_budget):
    final = fixture_case(case['protocol'], 'normal_stream' if case['streaming'] else 'normal_non_stream', case['streaming'])
    searches = []

    async def search(query):
        searches.append(query)
        return _evidence()

    async with recorded_model(case, final) as (model, calls):
        model.set_search(search)
        assert await model.generate('索引何时可检索？', _evidence(), request_id='fixture-agent') == final['expected_result']
        assert searches == ['索引 READY']
        assert len(calls) == 2 and calls[0].get('tools') and not calls[1].get('tools')
        assert len(recorded_budget) == (2 if model.default else 0)
        if case['protocol'] == 'responses':
            results = [item for item in calls[1]['input'] if item.get('type') == 'function_call_output']
            assert len(results) == 1 and results[0]['call_id'] == 'call_search_1'
            assert 'src-evidence-1' in results[0]['output']
        elif case['protocol'] == 'anthropic_messages':
            results = [block for msg in calls[1]['messages'] for block in msg['content']
                       if isinstance(block, dict) and block.get('type') == 'tool_result']
            assert len(results) == 1 and results[0]['tool_use_id'] == 'call_search_1'
            assert 'src-evidence-1' in json.dumps(results[0]['content'])
        else:
            results = [msg for msg in calls[1]['messages'] if msg['role'] == 'tool']
            assert len(results) == 1 and results[0]['tool_call_id'] == 'call_search_1'
            assert 'src-evidence-1' in results[0]['content']


def recorded_app(monkeypatch, model):
    import knowflow_ai.app as ai_app
    from knowflow_ai.config import Settings
    from test_service import SECRET

    monkeypatch.setenv('EMBEDING_KEY', 'e' * 40)
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'd' * 40)
    monkeypatch.setenv('KNOWFLOW_CUSTOM_LLM_ENABLED', 'true')
    monkeypatch.setattr(ai_app, 'LangChainAnswerModel', lambda *_args, **_kwargs: model)
    service = AnswerService('unused', _contract(), retriever=FakeRetriever(_evidence()), llm_factory=lambda: model)
    app = ai_app.create_app(Settings(SECRET, ai_database_url='postgresql://unused.invalid/db'),
                            answer_service_factory=lambda *_args, **_kwargs: service)
    return app


async def recorded_http(client, model, *, stream=False):
    from test_service import SECRET

    payload = _request()
    payload['scope']['owner_id'] = str(model.call_context.owner_id)
    path = '/internal/v1/answers'
    if not model.default:
        path = '/internal/v1/custom-answers'
        payload = {'request': payload, 'model': {**model.settings.model_dump(mode='json'),
                                               'api_key': model.settings.api_key.get_secret_value()}}
    return await client.post(path + ('/stream' if stream else ''), json=payload,
                             headers={'Authorization': 'Bearer ' + SECRET,
                                      'X-Request-ID': _request()['request_id']})


@pytest.mark.asyncio
@pytest.mark.parametrize('case', STREAM_ABNORMAL, ids=lambda case: case['id'])
async def test_recorded_abnormal_completion_returns_sanitized_502(case, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    async with recorded_model(case) as (model, calls):
        # Exercise the application's production streaming SDK configuration.
        app = recorded_app(monkeypatch, model)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
            response = await recorded_http(client, model)
        assert response.status_code == 502
        assert response.json()['code'] == 'AI_PROCESSING_FAILED'
        assert response.json()['retryable'] is False
        assert case['sentinel'] not in response.text
        assert case['sentinel'] not in caplog.text
        assert len(calls) == 1 and app.state.question_admission.active == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('case', STREAM_ABNORMAL, ids=lambda case: case['id'])
async def test_recorded_abnormal_stream_has_one_error_and_no_answer_delta(case, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    async with recorded_model(case) as (model, calls):
        app = recorded_app(monkeypatch, model)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
            response = await recorded_http(client, model, stream=True)
        assert response.status_code == 200
        assert response.headers['content-type'].startswith('text/event-stream')
        events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
        assert [event['event'] for event in events] == ['started', 'error']
        assert events[-1]['code'] == 'AI_PROCESSING_FAILED'
        for event in events:
            _contract().validate('AnswerStreamEvent', event)
        assert case['sentinel'] not in response.text
        assert case['sentinel'] not in caplog.text
        assert len(calls) == 1 and app.state.question_admission.active == 0


@pytest.mark.parametrize('streaming', [False, True], ids=['non_stream', 'stream'])
def test_completion_rejects_unknown_protocol_and_refusal(streaming, caplog):
    normal = fixture_case('anthropic_messages', 'normal_stream' if streaming else 'normal_non_stream', streaming)
    for protocol in ('unknown', '', None):
        with pytest.raises(ProcessingError) as caught:
            validate_completion(wire_bytes(normal), protocol=protocol, model_id=normal['model_id'],
                                streaming=streaming, allow_tools=False)
        assert (caught.value.status, caught.value.retryable) == (502, False)
    for protocol in PROTOCOLS:
        refusal = fixture_case(protocol, 'content_filter', streaming)
        with pytest.raises(ProcessingError) as caught:
            check_completion(refusal)
        assert_sanitized_error(caught.value, refusal, caplog)


@pytest.mark.parametrize('fault', ['empty_output', 'reasoning_only', 'unknown_output', 'error',
                                 'incomplete', 'refusal', 'incomplete_item', 'empty_message'])
def test_responses_completed_rejects_unusable_output(fault, caplog):
    case = fixture_case('responses', 'normal_non_stream', False)
    result = json.loads(wire_bytes(case))
    if fault == 'empty_output':
        result['output'] = []
    elif fault == 'reasoning_only':
        result['output'] = [{'type': 'reasoning', 'summary': []}]
    elif fault == 'unknown_output':
        result['output'][0]['type'] = 'unknown'
    elif fault == 'error':
        result['error'] = {'code': 'server_error', 'message': 'WIRE_PRIVATE_ERROR'}
    elif fault == 'incomplete':
        result['incomplete_details'] = {'reason': 'content_filter'}
    elif fault == 'refusal':
        result['output'][0]['content'] = [{'type': 'refusal', 'refusal': 'WIRE_PRIVATE_REFUSAL'}]
    elif fault == 'incomplete_item':
        result['output'][0]['status'] = 'incomplete'
    else:
        result['output'][0]['content'] = []
    with pytest.raises(ProcessingError) as caught:
        check_completion(case, body=json.dumps(result).encode())
    assert str(caught.value) == 'AI_PROCESSING_FAILED'
    assert (caught.value.status, caught.value.retryable) == (502, False)
    assert 'WIRE_PRIVATE_' not in caplog.text


@pytest.mark.parametrize('fault', ['error', 'response.failed', 'response.incomplete',
                                 'response.refusal.delta', 'response.refusal.done',
                                 'refusal_part', 'refusal_item', 'response_error',
                                 'tool_item', 'tool_arguments'])
def test_responses_stream_rejects_abnormal_events_even_before_valid_completion(fault, caplog):
    case = fixture_case('responses', 'normal_stream', True)
    sentinel = 'WIRE_PRIVATE_INTERMEDIATE_' + fault
    if fault == 'refusal_part':
        event = {'type': 'response.content_part.added', 'part': {'type': 'refusal', 'refusal': sentinel}}
    elif fault == 'refusal_item':
        event = {'type': 'response.output_item.done', 'item': {'type': 'message',
                 'content': [{'type': 'refusal', 'refusal': sentinel}]}}
    elif fault == 'response_error':
        event = {'type': 'response.in_progress', 'response': {'model': 'test-model',
                 'status': 'in_progress', 'error': {'message': sentinel}}}
    elif fault == 'tool_item':
        event = {'type': 'response.output_item.added', 'item': {'type': 'function_call',
                 'name': 'search_knowledge_base', 'arguments': sentinel}}
    elif fault == 'tool_arguments':
        event = {'type': 'response.function_call_arguments.delta', 'delta': sentinel}
    else:
        event = {'type': fault, 'message': sentinel, 'delta': sentinel}
    body = ('data: ' + json.dumps(event) + '\n\n').encode() + wire_bytes(case)
    with pytest.raises(ProcessingError) as caught:
        check_completion(case, body=body)
    assert (caught.value.status, caught.value.retryable) == (502, False)
    assert str(caught.value) == 'AI_PROCESSING_FAILED'
    assert sentinel not in caplog.text
