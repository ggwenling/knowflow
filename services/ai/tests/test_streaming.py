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


def _service(stream, *, status=200, model_profile=None, evidence=None):
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(status, headers={'Content-Type': 'text/event-stream'}, stream=stream)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = DeepSeekAdapter(LlmSettings(api_key=KEY), client)
    service = AnswerService('unused', _contract(),
                            retriever=FakeRetriever(_evidence() if evidence is None else evidence),
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
async def test_stream_buffers_answer_until_provider_finish_and_citation_validation():
    generated = ('{"has_answer":true,"answer":"索引 READY 后才可检索'
                 '[src-evidence-1]。","source_ids":["src-evidence-1"]}')
    stream = ProviderStream([_sse([generated])], block=True)
    service, client, calls = _service(stream)
    async with client, aclosing(service.stream(_request())) as events:
        assert (await anext(events))['event'] == 'started'
        pending_delta = asyncio.create_task(anext(events))
        await asyncio.wait_for(stream.waiting.wait(), 1)
        assert not pending_delta.done()
        assert calls[0]['stream'] is True
        stream.release.set()
        delta = await asyncio.wait_for(pending_delta, 1)
        assert delta['event'] == 'delta' and delta['sequence'] == 2
        assert delta['delta'] == '索引 READY 后才可检索[src-evidence-1]。'
        assert (await anext(events))['event'] == 'sources'
        assert (await anext(events))['event'] == 'completed'
    assert stream.closed


@pytest.mark.asyncio
@pytest.mark.parametrize('url', [
    'https://docs.example.test/search?q=cache',
    'https://docs.example.test/items;view=all',
])
async def test_stream_final_answer_preserves_url_boundary_characters(url):
    answer = f'请访问 {url}[src-evidence-1]。'
    evidence = _evidence()
    evidence[0]['text_content'] = f'请访问 {url}。'
    generated = json.dumps({'answer': answer, 'has_answer': True,
                            'source_ids': ['src-evidence-1']}, ensure_ascii=False)
    service, client, _calls = _service(
        ProviderStream([_sse([generated])]), evidence=evidence)

    async with client:
        events = [event async for event in service.stream(_request())]

    assert ''.join(event['delta'] for event in events if event['event'] == 'delta') == answer
    assert events[-2]['event'] == 'sources' and events[-2]['has_answer'] is True
    assert [source['source_id'] for source in events[-2]['sources']] == ['src-evidence-1']
    assert events[-1]['event'] == 'completed'


@pytest.mark.asyncio
@pytest.mark.parametrize('quote', ['"', '`'])
@pytest.mark.parametrize('separator', [';', '!', '?'])
async def test_stream_prunes_claim_after_a_quoted_url(quote, separator):
    answer = (f'参考 {quote}https://docs.example.test/start{quote}{separator}'
              '缓存默认关闭[src-evidence-1][src-evidence-2]。')
    evidence = _evidence()
    evidence[0]['text_content'] = '缓存默认关闭。'
    evidence.append({**evidence[0], 'source_id': 'src-evidence-2',
                     'chunk_id': 'chunk-example-2',
                     'text_content': '缓存默认开启。'})
    generated = json.dumps({'answer': answer, 'has_answer': True,
                            'source_ids': ['src-evidence-1', 'src-evidence-2']},
                           ensure_ascii=False)
    service, client, _calls = _service(
        ProviderStream([_sse([generated])]), evidence=evidence)

    async with client:
        events = [event async for event in service.stream(_request())]

    assert ''.join(event['delta'] for event in events if event['event'] == 'delta') == (
        '缓存默认关闭[src-evidence-1]。')
    assert events[-2]['event'] == 'sources' and events[-2]['has_answer'] is True
    assert [source['source_id'] for source in events[-2]['sources']] == ['src-evidence-1']
    assert events[-1]['event'] == 'completed'


@pytest.mark.asyncio
@pytest.mark.parametrize(('quote', 'second_url'), [
    ('"', 'https://docs.example.test/search?q=cache'),
    ('"', 'https://docs.example.test/items;view=all'),
    ('`', 'https://docs.example.test/search?q=cache'),
    ('`', 'https://docs.example.test/items;view=all'),
])
async def test_stream_rescans_each_quoted_url(quote, second_url):
    claim = (f'入口{quote}https://docs.example.test/start{quote}和'
             f'{quote}{second_url}{quote}')
    answer = claim + '[src-evidence-1]。'
    evidence = _evidence()
    evidence[0]['text_content'] = claim + '。'
    generated = json.dumps({'answer': answer, 'has_answer': True,
                            'source_ids': ['src-evidence-1']}, ensure_ascii=False)
    service, client, _calls = _service(
        ProviderStream([_sse([generated])]), evidence=evidence)

    async with client:
        events = [event async for event in service.stream(_request())]

    assert ''.join(event['delta'] for event in events if event['event'] == 'delta') == answer
    assert events[-2]['event'] == 'sources' and events[-2]['has_answer'] is True
    assert [source['source_id'] for source in events[-2]['sources']] == ['src-evidence-1']
    assert events[-1]['event'] == 'completed'


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
async def test_provider_stream_accepts_final_usage_only_chunk():
    generated = '{"has_answer":true,"answer":"ok[src-evidence-1]","source_ids":["src-evidence-1"]}'
    usage = {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20}
    body = (_sse([generated], done=False)
            + b'data: ' + json.dumps({"model": "deepseek-flash", "choices": [],
                                     "usage": usage}).encode() + b'\n\n'
            + b'data: [DONE]\n\n')
    service, client, _calls = _service(ProviderStream([body]))
    async with client:
        events = [event async for event in service.stream(_request())]
    assert events[-1]['event'] == 'completed'
    assert service._llm_factory().last_usage == usage


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
async def test_stream_single_marker_passes_without_soft_refuse():
    generated = ('{"answer":"数据库采用 PostgreSQL 存储[src-evidence-1]。",'
                 '"has_answer":true,"source_ids":["src-evidence-1"]}')
    service, client, _calls = _service(ProviderStream([_sse([generated])]))
    async with client:
        events = [event async for event in service.stream(_request())]

    assert [event['event'] for event in events] == [
        'started', 'delta', 'sources', 'completed']
    assert events[-2]['has_answer'] is True
    assert events[-2]['sources']


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
    # Include durable budget reservation before the deliberately blocked stream.
    monkeypatch.setattr(answering, 'ANSWER_DEADLINE_SECONDS', .5)
    stream = ProviderStream([], block=True)
    service, client, _calls = _service(stream)
    async with client:
        events = [event async for event in service.stream(_request())]
    assert events[-1]['event'] == 'error'
    assert events[-1]['code'] == 'PROCESSING_TIMEOUT'
    assert stream.waiting.is_set()
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
    assert app.state.question_admission.active == 0
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
    assert app.state.question_admission.active == 0


@pytest.mark.asyncio
async def test_http_answer_rejects_when_shared_capacity_is_full(monkeypatch):
    import knowflow_ai.app as ai_app
    from knowflow_ai.config import Settings
    from test_service import SECRET

    entered, release = asyncio.Event(), asyncio.Event()

    class WaitingAnswerService:
        async def stream(self, payload):
            entered.set()
            await release.wait()
            yield {'event': 'error', 'request_id': payload['request_id'], 'sequence': 1,
                   'code': 'AI_PROCESSING_FAILED'}

    monkeypatch.setenv('EMBEDING_KEY', 'e' * 40)
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'd' * 40)
    monkeypatch.setattr(ai_app, 'AnswerService', lambda *args, **kwargs: WaitingAnswerService())
    app = ai_app.create_app(Settings(SECRET,
        ai_database_url='postgresql://unused.invalid/db', max_concurrent_questions=1))
    payload = _request()
    headers = {'Authorization': 'Bearer ' + SECRET, 'X-Request-ID': payload['request_id']}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
        first = asyncio.create_task(client.post('/internal/v1/answers/stream', json=payload,
                                                 headers=headers))
        await asyncio.wait_for(entered.wait(), 1)
        second_payload = dict(payload)
        second_payload['request_id'] = 'request-busy-check'
        rejected = await client.post('/internal/v1/answers', json=second_payload, headers={
            'Authorization': 'Bearer ' + SECRET, 'X-Request-ID': second_payload['request_id']})
        assert rejected.status_code == 503
        assert rejected.json()['code'] == 'AI_PROCESSING_FAILED'
        assert rejected.json()['retryable'] is True
        release.set()
        response = await first
        assert response.status_code == 200
        assert 'event: error' in response.text
    assert app.state.question_admission.active == 0
