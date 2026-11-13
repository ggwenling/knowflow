import asyncio
from uuid import uuid4

import httpx
import httpx2
import pytest

from knowflow_ai.adapters import ProcessingError
from knowflow_ai.app import QuestionAdmission, create_app
from knowflow_ai.answering import AnswerService, LlmSettings
from knowflow_ai.config import Settings
from knowflow_ai.langchain_answer import LangChainAnswerModel as ProductionModel
from knowflow_ai.provider_runtime import ModelCallContext, BUSY_MESSAGE
from provider_test_helpers import LangChainAnswerModel, runtime_factory, ControlledByteStream, OWNER
from test_answering import FakeRetriever, _contract, _evidence, _request
from test_langchain_models import model_config
from test_provider_completion import fixture_case, wire_bytes, PROTOCOLS, forbid_wire_network
from test_service import SECRET, AUTH


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    forbid_wire_network(monkeypatch)
    async def reserve(*args, **kwargs):
        pass
    monkeypatch.setattr('knowflow_ai.langchain_answer.reserve_provider_call', reserve)


async def wait_entered(event, task):
    waiter = asyncio.create_task(event.wait())
    try:
        done, _ = await asyncio.wait((waiter, task), timeout=2, return_when=asyncio.FIRST_COMPLETED)
        if task in done:
            result = task.result()
            pytest.fail(f"Request completed before blocking: {result.status_code} {result.text}")
        assert waiter in done, 'Provider never entered'
    finally:
        waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('protocol', PROTOCOLS)
async def test_admission_rejects_without_waiting_or_starting_provider(protocol):
    runtime = runtime_factory(per_user=1)
    custom = protocol != 'deepseek'
    config = model_config(protocol) if custom else LlmSettings(api_key='x' * 40)
    lib = httpx2 if protocol == 'anthropic_messages' else httpx
    calls = []
    def handle(request):
        calls.append(request)
        pytest.fail('admission must precede network')
    ctx = ModelCallContext('admission', OWNER, config.id if custom else None)
    model = LangChainAnswerModel(config, runtime=runtime, call_context=ctx, transport=lib.MockTransport(handle))
    try:
        async with runtime.turn(ctx, model.model_key, model.profile):
            with pytest.raises(ProcessingError) as caught:
                await model._invoke(lambda: model.model.ainvoke('synthetic'))
        assert (caught.value.status, caught.value.code) == (429, 'RESOURCE_LIMIT')
        assert not calls and not runtime.users and not runtime.models
    finally:
        await model.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize('protocol', ['chat_completions', 'anthropic_messages', 'responses'])
@pytest.mark.parametrize('http_entry', [False, True], ids=['runtime', 'http-app'])
async def test_slow_custom_and_probe_do_not_block_builtin(protocol, http_entry, monkeypatch):
    custom, probe_config = model_config(protocol), model_config(protocol)
    blocked = [ControlledByteStream(), ControlledByteStream()]
    models, builtin_calls = [], []
    custom_index = 0
    runtime = runtime_factory()

    def factory(config, *, runtime, call_context, **kwargs):
        nonlocal custom_index
        lib = httpx2 if getattr(config, 'protocol', None) == 'anthropic_messages' else httpx
        if isinstance(config, LlmSettings):
            def handle(request):
                builtin_calls.append(request)
                return lib.Response(200, headers={'content-type': 'text/event-stream'},
                                    content=wire_bytes(fixture_case('deepseek', 'normal_stream', True)))
        else:
            stream = blocked[custom_index]
            custom_index += 1
            def handle(request):
                return lib.Response(200, headers={'content-type': 'text/event-stream'}, stream=stream)
        model = ProductionModel(config, runtime=runtime, call_context=call_context,
                                transport=lib.MockTransport(handle), **kwargs)
        models.append(model)
        return model

    tasks = []
    try:
        if not http_entry:
            admission = QuestionAdmission(3, 2)
            async def held(config, probe=False):
                lease = admission.try_acquire(custom=True)
                model = factory(config, runtime=runtime,
                                call_context=ModelCallContext('hold', OWNER, config.id, 'probe' if probe else 'answer'),
                                probe=probe)
                try:
                    return await model.probe_capabilities() if probe else await model.generate('synthetic', [], request_id='hold')
                finally:
                    lease.release()
            tasks.append(asyncio.create_task(held(custom)))
            await wait_entered(blocked[0].entered, tasks[0])
            tasks.append(asyncio.create_task(held(probe_config, True)))
            await wait_entered(blocked[1].entered, tasks[1])
            with pytest.raises(ProcessingError, match='RESOURCE_LIMIT'):
                admission.try_acquire(custom=True)
            lease = admission.try_acquire(custom=False)
            builtin = factory(LlmSettings(api_key='x' * 40), runtime=runtime,
                              call_context=ModelCallContext('builtin', OWNER))
            try:
                result = await asyncio.wait_for(builtin.generate('synthetic', [], request_id='builtin'), 10)
                assert result == fixture_case('deepseek', 'normal_stream', True)['expected_result']
            finally:
                lease.release()
        else:
            import knowflow_ai.app as ai_app
            monkeypatch.setenv('KNOWFLOW_CUSTOM_LLM_ENABLED', 'true')
            monkeypatch.setenv('EMBEDING_KEY', 'e' * 40)
            monkeypatch.setenv('DEEPSEEK_API_KEY', 'd' * 40)
            monkeypatch.setattr(ai_app, 'LangChainAnswerModel', factory)
            def service(database, contract, **kwargs):
                return AnswerService(database, contract, retriever=FakeRetriever(_evidence()), **kwargs)
            monkeypatch.setattr(ai_app, 'AnswerService', service)
            app = create_app(Settings(SECRET, ai_database_url='unused', max_concurrent_questions=3))
            runtime = app.state.provider_runtime
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
                payload = _request()
                payload["scope"]["owner_id"] = str(OWNER)
                headers = {**AUTH, 'X-Request-ID': payload['request_id']}
                def connection(config):
                    return {**config.model_dump(mode='json'), 'api_key': config.api_key.get_secret_value()}
                tasks.append(asyncio.create_task(client.post('/internal/v1/custom-answers',
                    json={'request': payload, 'model': connection(custom)}, headers=headers)))
                await wait_entered(blocked[0].entered, tasks[0])
                tasks.append(asyncio.create_task(client.post('/internal/v1/llm-models/probe', json=connection(probe_config),
                    headers={**headers, 'X-KnowFlow-Owner-ID': payload['scope']['owner_id']})))
                await wait_entered(blocked[1].entered, tasks[1])
                rejected = await client.post('/internal/v1/custom-answers',
                    json={'request': payload, 'model': connection(model_config(protocol))}, headers=headers)
                assert rejected.status_code == 429
                assert rejected.json()['code'] == 'RESOURCE_LIMIT' and rejected.json()['message'] == BUSY_MESSAGE
                result = await asyncio.wait_for(client.post('/internal/v1/answers', json=payload, headers=headers), 10)
                assert result.status_code == 200 and result.json()['has_answer']
            admission = app.state.question_admission
        assert len(builtin_calls) == 1
        assert all(not task.done() for task in tasks)
        assert all(not stream.closed.is_set() for stream in blocked)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for model in models:
            await model.aclose()
    assert admission.active == admission.custom_active == 0
    assert not runtime.users and not runtime.models
    assert all(stream.closed.is_set() for stream in blocked)


@pytest.mark.asyncio
@pytest.mark.parametrize('owner', [None, 'not-a-uuid'])
async def test_probe_owner_header_is_required_and_validated(owner, monkeypatch):
    monkeypatch.setenv('KNOWFLOW_CUSTOM_LLM_ENABLED', 'true')
    app = create_app(Settings(SECRET))
    config = model_config()
    payload = {**config.model_dump(mode='json'), 'api_key': 'fixture-key'}
    headers = {**AUTH, **({'X-KnowFlow-Owner-ID': owner} if owner else {})}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
        assert (await client.post('/internal/v1/llm-models/probe', json=payload, headers=headers)).status_code == 400
        # Internal authentication precedes all owner processing.
        assert (await client.post('/internal/v1/llm-models/probe', json=payload,
                                  headers={'X-KnowFlow-Owner-ID': str(OWNER)})).status_code == 401
    assert not app.state.question_admission.active


@pytest.mark.asyncio
@pytest.mark.parametrize('protocol', PROTOCOLS)
async def test_stream_busy_has_one_safe_error_and_releases_leases(protocol):
    runtime = runtime_factory(per_user=1)
    config = LlmSettings(api_key='x' * 40) if protocol == 'deepseek' else model_config(protocol)
    lib = httpx2 if protocol == 'anthropic_messages' else httpx
    def forbidden(request):
        pytest.fail('Busy turn started provider')
    model = LangChainAnswerModel(config, runtime=runtime, transport=lib.MockTransport(forbidden))
    service = AnswerService('unused', _contract(), retriever=FakeRetriever(_evidence()), llm_factory=lambda: model)
    try:
        async with runtime.turn(model.call_context, model.model_key, model.profile):
            events = [event async for event in service.stream(_request())]
        assert [event['event'] for event in events] == ['started', 'error']
        assert events[-1]['code'] == 'RESOURCE_LIMIT' and events[-1]['message'] == BUSY_MESSAGE
        assert events[-1]['retryable'] is True
        for event in events:
            _contract().validate('AnswerStreamEvent', event)
        assert not runtime.users and not runtime.models and model.http.is_closed
    finally:
        await model.aclose()


@pytest.mark.asyncio
async def test_probe_turns_share_route_deadline(monkeypatch):
    import knowflow_ai.app as ai_app
    entered = [asyncio.Event(), asyncio.Event(), asyncio.Event()]
    released = [asyncio.Event(), asyncio.Event(), asyncio.Event()]
    finished = asyncio.Event()
    monkeypatch.setenv('KNOWFLOW_CUSTOM_LLM_ENABLED', 'true')
    class Model:
        def __init__(self, config, *, runtime, call_context, **kwargs):
            self.runtime, self.context = runtime, call_context
        async def probe_capabilities(self):
            # Model turns alone allow 5 seconds each; the route still owns one 10s deadline.
            for index in range(3):
                async with self.runtime.turn(self.context, ('probe',), self.runtime.limits.timeout_profile(True, True)) as turn:
                    async def wait():
                        entered[index].set()
                        await released[index].wait()
                    await self.runtime.deadline_runner.run(wait, deadline=turn.deadline, timeout_kind='total_timeout')
            return False
        async def aclose(self):
            finished.set()
    monkeypatch.setattr(ai_app, 'LangChainAnswerModel', Model)
    app = create_app(Settings(SECRET), provider_runtime_factory=runtime_factory)
    runtime = app.state.provider_runtime
    payload = {**model_config().model_dump(mode='json'), 'api_key': 'fixture-key'}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
        task = asyncio.create_task(client.post('/internal/v1/llm-models/probe', json=payload,
                                  headers={**AUTH, 'X-KnowFlow-Owner-ID': str(OWNER)}))
        try:
            for index in range(2):
                await asyncio.wait_for(entered[index].wait(), 2)
                await runtime.deadline_runner.advance(4)
                released[index].set()
            await asyncio.wait_for(entered[2].wait(), 2)
            await runtime.deadline_runner.advance(2)
            result = await asyncio.wait_for(task, 2)
            assert result.status_code == 422 and result.json()['code'] == 'LLM_MODEL_TIMEOUT'
            assert finished.is_set() and app.state.question_admission.active == 0
            assert not runtime.users and not runtime.models and not runtime.deadline_runner.pending
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
