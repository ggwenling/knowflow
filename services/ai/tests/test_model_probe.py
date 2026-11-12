"""Save-time probes: only synthetic wire responses and controlled DNS/connect."""
import asyncio
from datetime import datetime, timezone
import json
import socket

import httpx
import httpx2
import pytest

from knowflow_ai import app as app_module, model_egress
from knowflow_ai.app import create_app
from knowflow_ai.config import Settings
from knowflow_ai.langchain_answer import LangChainAnswerModel as ProductionModel
from knowflow_ai.model_probe import MESSAGES
from provider_test_helpers import runtime_factory, OWNER, ControlledByteStream
from test_langchain_models import model_config, chat, anthropic_events, responses_events
from test_provider_completion import forbid_wire_network
from test_service import SECRET, AUTH

PROTOCOLS = ('chat_completions', 'responses', 'anthropic_messages')
STAMP = datetime(2026, 11, 12, 1, 2, 3, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    forbid_wire_network(monkeypatch)
    monkeypatch.setenv('KNOWFLOW_CUSTOM_LLM_ENABLED', 'true')


async def request_probe(monkeypatch, handler, *, protocol='chat_completions', url=None, owner=str(OWNER), runtime=None):
    calls = []
    lib = httpx2 if protocol == 'anthropic_messages' else httpx

    def handle(request):
        calls.append(request)
        return handler(request, lib, len(calls))

    def factory(config, **kwargs):
        return ProductionModel(config, transport=lib.MockTransport(handle), **kwargs)

    monkeypatch.setattr(app_module, 'LangChainAnswerModel', factory)
    runtime = runtime or runtime_factory()
    app = create_app(Settings(SECRET), provider_runtime_factory=lambda _: runtime, probe_clock=lambda: STAMP)
    config = model_config(protocol)
    payload = config.model_dump(mode='json')
    payload['api_key'] = config.api_key.get_secret_value()
    if url is not None:
        payload['base_url'] = url
    headers = {**AUTH, 'X-Request-ID': 'safe-probe'}
    if owner is not None:
        headers['X-KnowFlow-Owner-ID'] = owner
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://local') as client:
        response = await client.post('/internal/v1/llm-models/probe', headers=headers, json=payload)
    assert app.state.question_admission.active == 0
    assert not runtime.users and not runtime.models
    return response, calls


def reject(response, code, status=422):
    assert response.status_code == status, response.text
    assert response.json() == {'contract_version': '0.2.0', 'request_id': 'safe-probe',
                               'code': code, 'message': MESSAGES[code], 'retryable': False}


@pytest.mark.asyncio
@pytest.mark.parametrize('url', ['http://api.example.com', 'https://localhost', 'https://127.0.0.1',
    'https://[::1]', 'https://user:secret@api.example.com', 'https://api.example.com:8443',
    'https://api.example.com?secret=1', 'https://api.example.com#secret', 'https://api.example.com:bad', 'https://api.example.com?', 'https://api.example.com#', 'https://api.example.com/' + 'x' * 1024])
async def test_probe_rejects_wrong_url_with_specific_reason(monkeypatch, url):
    response, calls = await request_probe(monkeypatch, lambda *_: pytest.fail('unsafe network'), url=url)
    reject(response, 'LLM_MODEL_URL_INVALID', 400)
    assert not calls


@pytest.mark.asyncio
@pytest.mark.parametrize('protocol', PROTOCOLS)
@pytest.mark.parametrize('status', [401, 403])
async def test_probe_rejects_wrong_key_with_specific_reason(monkeypatch, protocol, status):
    response, calls = await request_probe(monkeypatch, lambda r, lib, n: lib.Response(status,
        json={'error': {'code': 'model_not_found', 'param': 'tools', 'message': 'secret'}}), protocol=protocol)
    reject(response, 'LLM_MODEL_AUTH_FAILED')
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('evidence', [{'code': 'model_not_found'}, {'code': 'invalid_model'}, {'param': 'model'}])
async def test_probe_rejects_missing_model_with_specific_reason(monkeypatch, evidence):
    response, calls = await request_probe(monkeypatch, lambda r, lib, n: lib.Response(404, json={'error': evidence}))
    reject(response, 'LLM_MODEL_NOT_FOUND')
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('protocol', PROTOCOLS)
@pytest.mark.parametrize('status', [404, 405])
async def test_probe_ambiguous_404_does_not_claim_model_not_found(monkeypatch, protocol, status):
    response, calls = await request_probe(monkeypatch, lambda r, lib, n: lib.Response(status,
        json={'error': {'type': 'not_found_error', 'message': 'model_not_found invalid_model tools'}}), protocol=protocol)
    reject(response, 'LLM_MODEL_ENDPOINT_NOT_FOUND')
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('status,code', [(429, 'RATE_LIMITED'), (500, 'PROBE_FAILED'), (503, 'PROBE_FAILED'),
                                        (400, 'PROBE_FAILED'), (422, 'PROBE_FAILED')])
async def test_probe_errors_never_echo_provider_body_or_credentials(monkeypatch, caplog, status, code):
    secret = 'fixture-key https://user:password@provider.example.com PRIVATE_COMPLETION'
    response, calls = await request_probe(monkeypatch, lambda r, lib, n: lib.Response(status,
        json={'error': {'code': secret, 'type': secret, 'param': secret, 'message': secret}}))
    reject(response, 'LLM_MODEL_' + code)
    assert secret not in response.text + caplog.text
    assert 'fixture-key' not in caplog.text
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_probe_result_contains_checked_at_status_and_tool_support(monkeypatch):
    def handler(request, lib, n):
        payload = json.loads(request.content)
        if n == 1:
            assert payload['tools']
            return chat({'tool_calls': [{'index': 0, 'id': 'ready-1', 'type': 'function',
                'function': {'name': 'report_ready', 'arguments': '{}'}}]}, 'tool_calls')
        assert not payload.get('tools')
        assert any(m['role'] == 'tool' and m['tool_call_id'] == 'ready-1' for m in payload['messages'])
        return chat({'content': 'READY'})
    response, calls = await request_probe(monkeypatch, handler)
    assert response.status_code == 200, response.text
    assert response.json() == {'supports_tools': True, 'status': 'success', 'checked_at': '2026-11-12T01:02:03Z'}
    assert len(calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('protocol', PROTOCOLS)
async def test_probe_without_tools_can_succeed(monkeypatch, protocol):
    def handler(r, lib, n):
        if n == 1:
            return lib.Response(422, json={'error': {'param': 'tools', 'code': 'unsupported_parameter'}})
        return {'chat_completions': lambda: chat({'content': 'READY'}),
                'responses': lambda: responses_events('READY'),
                'anthropic_messages': lambda: anthropic_events('READY')}[protocol]()
    response, calls = await request_probe(monkeypatch, handler, protocol=protocol)
    assert response.status_code == 200, response.text
    assert response.json()['supports_tools'] is False
    assert len(calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('status,evidence,fallback', [
    (400, {'message': 'unsupported tools'}, False), (422, {}, False), (501, {}, False),
    (501, {'param': 'tools'}, False), (501, {'param': 'tools', 'code': 'not_implemented'}, True),
    (400, {'param': 'tool_choice'}, True), (400, {'param': 'tools', 'code': 'invalid_model'}, False)])
async def test_probe_fallback_requires_explicit_tools_rejection(monkeypatch, status, evidence, fallback):
    response, calls = await request_probe(monkeypatch, lambda r, lib, n: lib.Response(status,
        json={'error': evidence}) if n == 1 else chat({'content': 'READY'}))
    assert len(calls) == (2 if fallback else 1)
    assert response.status_code == (200 if fallback else 422)


@pytest.mark.asyncio
async def test_probe_fallback_failure_is_final(monkeypatch):
    response, calls = await request_probe(monkeypatch, lambda r, lib, n: lib.Response(400,
        json={'error': {'param': 'tools'}}))
    reject(response, 'LLM_MODEL_PROBE_FAILED')
    assert len(calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('owner', [None, '', 'not-a-uuid'])
async def test_probe_owner_header_is_required_and_validated(monkeypatch, owner):
    response, calls = await request_probe(monkeypatch, lambda *_: pytest.fail('untrusted owner'), owner=owner)
    assert response.status_code == 400
    assert response.json()['code'] == 'INVALID_REQUEST'
    assert not calls


@pytest.mark.parametrize('url', ['http://api.example.com', 'https://localhost', 'https://127.0.0.1',
    'https://[::ffff:8.8.8.8]', 'https://u:p@api.example.com', 'https://api.example.com:80',
    'https://api.example.com?q=1', 'https://api.example.com#fragment'])
def test_custom_destination_rejects_unsafe_urls_before_network(monkeypatch, url):
    def forbidden(*a, **kw):
        pytest.fail('network before validation')
    monkeypatch.setattr(socket, 'getaddrinfo', forbidden)
    config = model_config().model_copy(update={'base_url': url})
    from knowflow_ai.adapters import ProcessingError
    with pytest.raises(ProcessingError):
        config.validate_destination()


@pytest.mark.asyncio
@pytest.mark.parametrize('host,ips', [('metadata.google.internal', ['169.254.169.254']),
    ('public.example.com', ['8.8.8.8', '10.0.0.1']), ('metadata.example.com', ['168.63.129.16']),
    ('ipv6.example.com', ['::1']), ('ipv6.example.com', ['fc00::1']),
    ('ipv6.example.com', ['::ffff:8.8.8.8']), ('ipv6.example.com', ['64:ff9b::a9fe:a9fe']),
    ('ipv6.example.com', ['2002:0808:0808::1']), ('empty.example.com', [])])
async def test_proxy_rejects_metadata_dns_and_mixed_public_private_answers(monkeypatch, host, ips):
    async def lookup(name, port, **kw):
        assert name == host + '.'
        return [(socket.AF_INET6 if ':' in ip else socket.AF_INET, socket.SOCK_STREAM,
                 socket.IPPROTO_TCP, '', (ip, port)) for ip in ips]
    async def connect(*a, **kw):
        pytest.fail('unsafe upstream connect')
    monkeypatch.setattr(asyncio.get_running_loop(), 'getaddrinfo', lookup)
    monkeypatch.setattr(asyncio, 'open_connection', connect)
    with pytest.raises(ValueError):
        await model_egress.connect_public(host, ())


@pytest.mark.asyncio
@pytest.mark.parametrize('protocol', PROTOCOLS)
async def test_custom_redirect_is_never_followed_during_probe(monkeypatch, protocol):
    response, calls = await request_probe(monkeypatch, lambda r, lib, n: lib.Response(307,
        headers={'location': 'https://169.254.169.254/secret'}), protocol=protocol)
    reject(response, 'LLM_MODEL_UNREACHABLE')
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['ConnectError', 'ReadError', 'ProxyError', 'ConnectTimeout', 'ReadTimeout'])
@pytest.mark.parametrize('protocol', PROTOCOLS)
async def test_probe_transport_failures_are_safe(monkeypatch, kind, protocol):
    def handler(r, lib, n):
        raise getattr(lib, kind)('PRIVATE_TRANSPORT_SECRET')
    response, calls = await request_probe(monkeypatch, handler, protocol=protocol)
    reject(response, 'LLM_MODEL_TIMEOUT' if 'Timeout' in kind else 'LLM_MODEL_UNREACHABLE')
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('wire', [b'<html>secret</html>', b'data: [DONE]\n\n', b'junk'])
async def test_probe_rejects_invalid_success_protocol(monkeypatch, wire):
    response, calls = await request_probe(monkeypatch, lambda r, lib, n: lib.Response(200,
        headers={'content-type': 'text/event-stream'}, content=wire))
    reject(response, 'LLM_MODEL_PROTOCOL_ERROR')
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_probe_deadline_uses_fake_time_and_closes_stream(monkeypatch):
    runtime = runtime_factory()
    stream = ControlledByteStream()
    task = asyncio.create_task(request_probe(monkeypatch, lambda r, lib, n: lib.Response(200,
        headers={'content-type': 'text/event-stream'}, stream=stream), runtime=runtime))
    await asyncio.wait_for(stream.entered.wait(), 2)
    await runtime.deadline_runner.advance(11)
    response, calls = await asyncio.wait_for(task, 2)
    reject(response, 'LLM_MODEL_TIMEOUT')
    assert stream.closed.is_set() and len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('protocol', PROTOCOLS)
async def test_probe_wrong_returned_model_is_protocol_error(monkeypatch, protocol):
    def handler(r, lib, n):
        response = {'chat_completions': lambda: chat({'content': 'READY'}),
                    'responses': lambda: responses_events('READY'),
                    'anthropic_messages': lambda: anthropic_events('READY')}[protocol]()
        return lib.Response(200, headers=response.headers, content=response.content.replace(b'test-model', b'wrong-model'))
    response, calls = await request_probe(monkeypatch, handler, protocol=protocol)
    reject(response, 'LLM_MODEL_PROTOCOL_ERROR')
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('tool', [
    {'id': '', 'function': {'name': 'report_ready', 'arguments': '{}'}},
    {'id': 'ready', 'function': {'name': 'other_tool', 'arguments': '{}'}},
    {'id': 'ready', 'function': {'name': 'report_ready', 'arguments': '{"secret":true}'}},
    {'id': 'ready', 'function': {'name': 'report_ready', 'arguments': 'not-json'}},
])
async def test_probe_rejects_invalid_tool_result(monkeypatch, tool):
    response, calls = await request_probe(monkeypatch, lambda r, lib, n: chat(
        {'tool_calls': [{'index': 0, 'type': 'function', **tool}]}, 'tool_calls'))
    reject(response, 'LLM_MODEL_PROTOCOL_ERROR')
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_probe_tools_require_final_nonempty_text(monkeypatch):
    def handler(r, lib, n):
        if n == 1:
            return chat({'tool_calls': [{'index': 0, 'id': 'ready', 'type': 'function',
                'function': {'name': 'report_ready', 'arguments': '{}'}}]}, 'tool_calls')
        return chat({'content': '   '})
    response, calls = await request_probe(monkeypatch, handler)
    reject(response, 'LLM_MODEL_PROTOCOL_ERROR')
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_probe_missing_proxy_fails_closed_before_network(monkeypatch):
    monkeypatch.delenv('KNOWFLOW_CUSTOM_LLM_PROXY', raising=False)
    # Undo the injected factory used by request_probe: no transport, no proxy.
    def no_proxy_factory(config, **kwargs):
        kwargs.pop('transport', None)
        return ProductionModel(config, **kwargs)
    monkeypatch.setattr(app_module, 'LangChainAnswerModel', no_proxy_factory)
    app = create_app(Settings(SECRET), provider_runtime_factory=runtime_factory)
    payload = {**model_config().model_dump(mode='json'), 'api_key': 'fixture-key'}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://local') as client:
        response = await client.post('/internal/v1/llm-models/probe', json=payload,
            headers={**AUTH, 'X-Request-ID': 'safe-probe', 'X-KnowFlow-Owner-ID': str(OWNER)})
    reject(response, 'LLM_MODEL_UNREACHABLE')
    assert app.state.question_admission.active == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [200, 400, 500])
async def test_probe_response_is_bounded_and_closed(monkeypatch, status):
    closed = asyncio.Event()
    class TooLarge(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'x' * (1024 * 1024 + 1)
        async def aclose(self):
            closed.set()
    response, calls = await request_probe(monkeypatch, lambda r, lib, n: lib.Response(status,
        headers={'content-type': 'text/event-stream'}, stream=TooLarge()))
    reject(response, 'LLM_MODEL_PROTOCOL_ERROR' if status == 200 else 'LLM_MODEL_PROBE_FAILED')
    assert closed.is_set() and len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('protocol', PROTOCOLS)
async def test_probe_unknown_provider_failure_uses_generic_reason(monkeypatch, protocol):
    def handler(r, lib, n):
        raise RuntimeError('PRIVATE_PROVIDER_SECRET')
    response, calls = await request_probe(monkeypatch, handler, protocol=protocol)
    reject(response, 'LLM_MODEL_PROBE_FAILED')
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_probe_cleanup_failure_uses_generic_reason(monkeypatch):
    class Model:
        def __init__(self, *args, **kwargs):
            pass
        async def probe_capabilities(self):
            return False
        async def aclose(self):
            raise RuntimeError('PRIVATE_CLEANUP_SECRET')
    monkeypatch.setattr(app_module, 'LangChainAnswerModel', Model)
    app = create_app(Settings(SECRET), provider_runtime_factory=runtime_factory)
    payload = {**model_config().model_dump(mode='json'), 'api_key': 'fixture-key'}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://local') as client:
        response = await client.post('/internal/v1/llm-models/probe', json=payload,
            headers={**AUTH, 'X-Request-ID': 'safe-probe', 'X-KnowFlow-Owner-ID': str(OWNER)})
    reject(response, 'LLM_MODEL_PROBE_FAILED')
    assert app.state.question_admission.active == 0
