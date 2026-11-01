import asyncio
from contextlib import aclosing
import json

import httpx
import pytest

from knowflow_ai.adapters import ProcessingError
from knowflow_ai.answering import AnswerService, DeepSeekAdapter, LlmSettings
from knowflow_ai.streaming import IncrementalAnswerParser
from test_answering import FakeRetriever, KEY, _contract, _evidence, _request


class ProviderStream(httpx.AsyncByteStream):
    def __init__(self, chunks, *, block=False):
        self.chunks, self.block = chunks, block
        self.waiting = asyncio.Event()
        self.release = asyncio.Event()
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk
        if self.block:
            self.waiting.set()
            await self.release.wait()

    async def aclose(self):
        self.closed = True


def _sse(fragments, *, finish='stop', done=True, model='deepseek-flash'):
    events = []
    for content in fragments:
        events.append({'model': model, 'choices': [
            {'index': 0, 'delta': {'content': content}, 'finish_reason': None}]})
    if finish is not None:
        events.append({'model': model, 'choices': [
            {'index': 0, 'delta': {}, 'finish_reason': finish}]})
    body = b''.join(b'data: ' + json.dumps(row, ensure_ascii=False).encode() + b'\r\n\r\n'
                    for row in events)
    return body + (b'data: [DONE]\n\n' if done else b'')


def _service(stream, *, status=200, model_profile=None):
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(status, headers={'Content-Type': 'text/event-stream'}, stream=stream)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = DeepSeekAdapter(LlmSettings(api_key=KEY), client)
    service = AnswerService('unused', _contract(), retriever=FakeRetriever(_evidence()),
                            llm_factory=lambda: adapter, model_profile=model_profile)
    return service, client, calls


def test_incremental_parser_handles_every_character_escape_and_key_order():
    generated = {'answer': '中文😀\n[引用]\\"', 'source_ids': ['src-evidence-1'], 'has_answer': True}
    parser = IncrementalAnswerParser()
    deltas = [parser.feed(char) for char in json.dumps(generated, ensure_ascii=True)]
    assert ''.join(deltas) == generated['answer']
    assert parser.finish() == generated


@pytest.mark.parametrize('raw', [
    '{"has_answer":true,"answer":"x","source_ids":[],"answer":"forged"}',
    '{"has_answer":true,"answer":"\\ud800x","source_ids":[]}',
    '{"has_answer":true,"answer":"x","source_ids":[]',
    '{"has_answer":true,"answer":"' + 'x' * 16001,
])
def test_incremental_parser_rejects_duplicate_truncated_unicode_and_oversized_json(raw):
    parser = IncrementalAnswerParser()
    with pytest.raises(ProcessingError):
        parser.feed(raw)
        parser.finish()


@pytest.mark.asyncio
async def test_stream_emits_delta_before_provider_finish_and_closes_on_iterator_close():
    stream = ProviderStream([_sse(['{"has_answer":true,"answer":"首段'],
                                  finish=None, done=False)], block=True)
    service, client, calls = _service(stream)
    async with client, aclosing(service.stream(_request())) as events:
        assert (await anext(events))['event'] == 'started'
        delta = await anext(events)
        assert delta['delta'] == '首段'
        assert not stream.waiting.is_set()
        assert calls[0]['stream'] is True
    assert stream.closed


@pytest.mark.asyncio
async def test_provider_stream_accepts_fragmented_utf8_and_validates_final_sources():
    generated = '{"has_answer":true,"answer":"READY😀[src-evidence-1]","source_ids":["src-evidence-1"]}'
    body = _sse(list(generated))
    stream = ProviderStream([body[index:index+1] for index in range(len(body))])
    model_profile = {'embedding_model_profile_id': 'BAAI/bge-m3',
                     'llm_model_profile_id': 'deepseek-flash'}
    service, client, _calls = _service(stream, model_profile=model_profile)
    async with client:
        events = [event async for event in service.stream(_request())]
    assert events[0]['event'] == 'started'
    assert events[0]['model_profile'] == model_profile
    assert ''.join(event['delta'] for event in events if event['event'] == 'delta') == 'READY😀[src-evidence-1]'
    assert events[-2]['event'] == 'sources'
    assert events[-2]['sources'][0]['chunk_id'] == 'chunk-example-1'
    assert events[-1]['event'] == 'completed'
    assert [event['sequence'] for event in events] == list(range(1, len(events) + 1))
    assert stream.closed


@pytest.mark.asyncio
@pytest.mark.parametrize('fragments,finish,done,model', [
    (['{"has_answer":true,"answer":"x[src-forged]","source_ids":["src-forged"]}'], 'stop', True, 'deepseek-flash'),
    (['{"has_answer":true,"answer":"x'], 'stop', True, 'deepseek-flash'),
    (['{}'], 'length', True, 'deepseek-flash'),
    (['{}'], 'stop', False, 'deepseek-flash'),
    (['{}'], 'stop', True, 'wrong-model'),
])
async def test_stream_rejects_forged_citations_truncation_finish_and_model(fragments, finish, done, model):
    stream = ProviderStream([_sse(fragments, finish=finish, done=done, model=model)])
    service, client, _calls = _service(stream)
    async with client:
        events = [event async for event in service.stream(_request())]
    assert [event['event'] for event in events][-1] == 'error'
    assert not any(event['event'] in ('sources', 'completed') for event in events)
    assert sum(event['event'] in ('error', 'cancelled', 'completed') for event in events) == 1
    assert stream.closed


@pytest.mark.asyncio
async def test_stream_refusal_is_canonical_and_has_no_model_sources():
    generated = '{"answer":"untrusted claim","has_answer":false,"source_ids":[]}'
    stream = ProviderStream([_sse([generated])])
    service, client, _calls = _service(stream)
    async with client:
        events = [event async for event in service.stream(_request())]
    assert [event['event'] for event in events] == ['started', 'delta', 'sources', 'completed']
    assert events[1]['delta'] == '没有足够的资料证据回答这个问题。'
    assert events[2]['has_answer'] is False and events[2]['sources'] == []


@pytest.mark.asyncio
async def test_stream_cancellation_closes_provider_and_yields_one_terminal():
    stream = ProviderStream([], block=True)
    service, client, _calls = _service(stream)
    async with client, aclosing(service.stream(_request())) as events:
        assert (await anext(events))['event'] == 'started'
        operation = asyncio.create_task(anext(events))
        await asyncio.wait_for(stream.waiting.wait(), 1)
        operation.cancel()
        terminal = await asyncio.wait_for(operation, 1)
        assert terminal['event'] == 'cancelled'
        assert stream.closed
        with pytest.raises(StopAsyncIteration):
            await anext(events)


@pytest.mark.asyncio
async def test_stream_deadline_closes_provider_and_returns_timeout(monkeypatch):
    import knowflow_ai.answering as answering
    monkeypatch.setattr(answering, 'ANSWER_DEADLINE_SECONDS', .02)
    stream = ProviderStream([], block=True)
    service, client, _calls = _service(stream)
    async with client:
        events = [event async for event in service.stream(_request())]
    assert events[-1]['event'] == 'error'
    assert events[-1]['code'] == 'PROCESSING_TIMEOUT'
    assert stream.closed


@pytest.mark.asyncio
async def test_stream_without_evidence_uses_no_provider():
    service = AnswerService('unused', _contract(), retriever=FakeRetriever([]),
                            llm_factory=lambda: pytest.fail('must not create provider'))
    events = [event async for event in service.stream(_request())]
    assert [event['event'] for event in events] == ['started', 'delta', 'sources', 'completed']

@pytest.mark.asyncio
@pytest.mark.parametrize('body', [b'data: {malformed}\n\n', b'data: {}\n\n', b': ' + b'x' * 2048 + b'\n\n'])
async def test_provider_malformed_sse_and_total_body_limit_close_stream(body):
    stream = ProviderStream([body])
    client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, headers={'content-type': 'text/event-stream'}, stream=stream)))
    adapter = DeepSeekAdapter(LlmSettings(api_key=KEY, max_response_bytes=1024), client)
    async with client:
        with pytest.raises(ProcessingError):
            _ = [content async for content in adapter.stream_content('q', _evidence(), request_id='r1')]
    assert stream.closed


@pytest.mark.asyncio
async def test_provider_rejects_completed_json_instead_of_sse():
    client = httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={'choices': []})))
    adapter = DeepSeekAdapter(LlmSettings(api_key=KEY), client)
    async with client:
        with pytest.raises(ProcessingError):
            _ = [content async for content in adapter.stream_content('q', _evidence(), request_id='r1')]


@pytest.mark.asyncio
async def test_stream_owned_http_client_closes_after_timeout():
    def timeout(request):
        raise httpx.ReadTimeout('redacted')

    adapter = DeepSeekAdapter(LlmSettings(api_key=KEY))
    await adapter._client.aclose()
    adapter._client = httpx.AsyncClient(transport=httpx.MockTransport(timeout))
    service = AnswerService('unused', _contract(), retriever=FakeRetriever(_evidence()),
                            llm_factory=lambda: adapter)
    events = [event async for event in service.stream(_request())]
    assert events[-1]['code'] == 'PROCESSING_TIMEOUT'
    assert adapter._client.is_closed


@pytest.mark.asyncio
async def test_stream_cancels_retrieval_before_emitting_cancelled():
    started, closed = asyncio.Event(), asyncio.Event()

    class BlockingRetriever:
        async def retrieve(self, *args, **kwargs):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                closed.set()

    service = AnswerService('unused', _contract(), retriever=BlockingRetriever(),
                            llm_factory=lambda: pytest.fail('no model before retrieval'))
    async with aclosing(service.stream(_request())) as events:
        await anext(events)
        task = asyncio.create_task(anext(events))
        await started.wait()
        task.cancel()
        assert (await task)['event'] == 'cancelled'
        assert closed.is_set()
        with pytest.raises(StopAsyncIteration):
            await anext(events)


@pytest.mark.asyncio
async def test_terminal_cannot_be_followed_by_cancelled():
    service = AnswerService('unused', _contract(), retriever=FakeRetriever([]))
    events = service.stream(_request())
    while (await anext(events))['event'] != 'completed':
        pass
    with pytest.raises(asyncio.CancelledError):
        await events.athrow(asyncio.CancelledError())


@pytest.mark.asyncio
@pytest.mark.parametrize('spec,disconnect_after_delta', [('2.0', False), ('2.4', False), ('2.4', True)])
async def test_http_disconnect_closes_real_provider_stream(monkeypatch, spec, disconnect_after_delta):
    import knowflow_ai.app as ai_app
    from knowflow_ai.config import Settings
    from test_service import SECRET

    chunks = [_sse(['{"has_answer":true,"answer":"first'], finish=None, done=False)] if disconnect_after_delta else []
    stream = ProviderStream(chunks, block=True)
    service, client, _calls = _service(stream)
    monkeypatch.setenv('EMBEDING_KEY', 'e' * 40)
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'd' * 40)
    monkeypatch.setattr(ai_app, 'AnswerService', lambda *args, **kwargs: service)
    app = ai_app.create_app(Settings(SECRET, ai_database_url='postgresql://unused.invalid/db'))
    payload = _request()
    received_body = False
    sent = []

    async def receive():
        nonlocal received_body
        if not received_body:
            received_body = True
            return {'type': 'http.request', 'body': json.dumps(payload).encode(), 'more_body': False}
        await stream.waiting.wait()
        return {'type': 'http.disconnect'}

    async def send(message):
        sent.append(message)
        if disconnect_after_delta and message['type'] == 'http.response.body' and b'event: delta' in message.get('body', b''):
            raise OSError('connection closed')

    scope = {'type': 'http', 'asgi': {'spec_version': spec}, 'http_version': '1.1',
             'method': 'POST', 'scheme': 'http', 'path': '/internal/v1/answers/stream',
             'raw_path': b'/internal/v1/answers/stream', 'query_string': b'',
             'headers': [(b'authorization', ('Bearer ' + SECRET).encode()),
                         (b'x-request-id', payload['request_id'].encode()),
                         (b'content-type', b'application/json')],
             'client': ('127.0.0.1', 1), 'server': ('127.0.0.1', 8000)}
    async with client:
        await asyncio.wait_for(app(scope, receive, send), 2)
    assert stream.closed
    assert not any(b'event: completed' in row.get('body', b'') for row in sent)


@pytest.mark.asyncio
async def test_http_sse_route_serializes_valid_events(monkeypatch):
    import knowflow_ai.app as ai_app
    from knowflow_ai.config import Settings
    from test_service import SECRET

    stream = ProviderStream([_sse(['{"has_answer":true,"answer":"ok[src-evidence-1]","source_ids":["src-evidence-1"]}'])])
    service, provider_client, _calls = _service(stream)
    monkeypatch.setenv('EMBEDING_KEY', 'e' * 40)
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'd' * 40)
    monkeypatch.setattr(ai_app, 'AnswerService', lambda *args, **kwargs: service)
    app = ai_app.create_app(Settings(SECRET, ai_database_url='postgresql://unused.invalid/db'))
    async with provider_client, httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
        response = await client.post('/internal/v1/answers/stream', json=_request(), headers={
            'Authorization': 'Bearer ' + SECRET, 'X-Request-ID': _request()['request_id']})
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/event-stream')
    events = [json.loads(line.removeprefix('data: ')) for line in response.text.splitlines() if line.startswith('data: ')]
    assert [event['event'] for event in events] == ['started', 'delta', 'sources', 'completed']
    for event in events:
        _contract().validate('AnswerStreamEvent', event)
