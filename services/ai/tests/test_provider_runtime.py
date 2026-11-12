import asyncio
from contextlib import AsyncExitStack
from uuid import uuid4
import pytest

from knowflow_ai.adapters import ProcessingError
from knowflow_ai.provider_runtime import ModelCallContext, BREAKER_CAPACITY, DeadlineRunner
from provider_test_helpers import OWNER, runtime_factory


def context(custom=True):
    return ModelCallContext('runtime-test', OWNER, uuid4() if custom else None)


def turn(runtime, ctx, key=None):
    return runtime.turn(ctx, key or ('test', ctx.custom_id), runtime.limits.timeout_profile())


async def fail(runtime, ctx, key=None):
    with pytest.raises(ProcessingError):
        async with turn(runtime, ctx, key):
            raise ProcessingError('AI_PROCESSING_FAILED', 502, retryable=False)


@pytest.mark.asyncio
async def test_user_limit_applies_across_custom_models():
    runtime = runtime_factory(per_user=1)
    async with turn(runtime, context()):
        with pytest.raises(ProcessingError) as caught:
            async with turn(runtime, context()):
                pytest.fail('admitted')
        assert (caught.value.status, caught.value.code) == (429, 'RESOURCE_LIMIT')
    assert runtime.users == runtime.models == {}


@pytest.mark.asyncio
async def test_model_limit_is_independent_of_user_limit():
    runtime, ctx = runtime_factory(per_user=4), context()
    async with turn(runtime, ctx):
        with pytest.raises(ProcessingError, match='RESOURCE_LIMIT'):
            async with turn(runtime, ctx):
                pytest.fail('admitted')
        async with turn(runtime, context()):
            pass


@pytest.mark.asyncio
async def test_builtin_user_lane_is_independent_of_custom_lane():
    runtime = runtime_factory(per_user=1)
    async with turn(runtime, context()):
        async with turn(runtime, context(False)):
            assert len(runtime.users) == 2
    assert not runtime.users


@pytest.mark.asyncio
async def test_breaker_opens_after_consecutive_final_failures():
    runtime, ctx = runtime_factory(), context()
    for _ in range(3):
        await fail(runtime, ctx)
    with pytest.raises(ProcessingError) as caught:
        async with turn(runtime, ctx):
            pytest.fail('open')
    assert caught.value.retry_reason == 'circuit_open'
    assert next(iter(runtime.breakers.values())).failures == 3
    assert not runtime.users and not runtime.models


@pytest.mark.asyncio
async def test_success_resets_consecutive_failures():
    runtime, ctx = runtime_factory(), context()
    await fail(runtime, ctx)
    async with turn(runtime, ctx):
        pass
    assert next(iter(runtime.breakers.values())).failures == 0


@pytest.mark.asyncio
async def test_breaker_allows_one_half_open_probe():
    runtime, ctx = runtime_factory(failure_threshold=1, per_model=2), context()
    await fail(runtime, ctx)
    runtime.clock.__self__.advance(30)
    async with turn(runtime, ctx) as state:
        assert state.token.half_open
        with pytest.raises(ProcessingError) as caught:
            async with turn(runtime, ctx):
                pytest.fail('second probe')
        assert caught.value.retry_reason == 'circuit_open'
    assert state.token.entry.state == 'CLOSED'


@pytest.mark.asyncio
async def test_stale_success_cannot_close_new_open_generation():
    runtime, ctx = runtime_factory(failure_threshold=1, per_model=2), context()
    async with turn(runtime, ctx):
        await fail(runtime, ctx)
    entry = next(iter(runtime.breakers.values()))
    assert entry.state == 'OPEN' and entry.failures == 1


@pytest.mark.asyncio
async def test_half_open_failure_and_cancellation_release_probe_token():
    runtime, ctx = runtime_factory(failure_threshold=1), context()
    await fail(runtime, ctx)
    for outcome in ('failure', 'cancel'):
        runtime.clock.__self__.advance(30)
        with pytest.raises((ProcessingError, asyncio.CancelledError)):
            async with turn(runtime, ctx) as state:
                assert state.token.half_open
                raise ProcessingError('AI_PROCESSING_FAILED') if outcome == 'failure' else asyncio.CancelledError()
        assert state.token.entry.state == 'OPEN'
        assert state.token.entry.in_flight == 0
        assert not runtime.users and not runtime.models
    assert state.token.entry.failures == 2


@pytest.mark.asyncio
async def test_changed_custom_credentials_use_new_breaker_generation():
    runtime, ctx = runtime_factory(failure_threshold=1), context()
    def key(secret='old', endpoint='https://example.test'):
        return runtime.model_key(ctx, protocol='responses', endpoint=endpoint, model='test', key=secret)
    await fail(runtime, ctx, key())
    for changed in (key('new'), key(endpoint='https://new.example.test')):
        assert changed != key()
        async with turn(runtime, ctx, changed):
            with pytest.raises(ProcessingError, match='RESOURCE_LIMIT'):
                async with turn(runtime, ctx, key('another')):
                    pytest.fail('stable concurrency key bypassed')
    assert 'old' not in repr(runtime.breakers)


@pytest.mark.asyncio
async def test_registry_remains_bounded_and_does_not_evict_live_breakers():
    runtime = runtime_factory(failure_threshold=1)
    for _ in range(BREAKER_CAPACITY):
        await fail(runtime, context())
    with pytest.raises(ProcessingError, match='RESOURCE_LIMIT'):
        async with turn(runtime, context()):
            pytest.fail('registry overflow')
    assert len(runtime.breakers) == BREAKER_CAPACITY
    runtime.clock.__self__.advance(30)
    async with turn(runtime, context()):
        pass
    assert len(runtime.breakers) == BREAKER_CAPACITY
    runtime.clock.__self__.advance(600)
    async with turn(runtime, context()):
        pass
    assert len(runtime.breakers) == 1

    live = runtime_factory()
    async with AsyncExitStack() as stack:
        for _ in range(BREAKER_CAPACITY):
            ctx = ModelCallContext('live', uuid4(), uuid4())
            await stack.enter_async_context(turn(live, ctx))
        with pytest.raises(ProcessingError, match='RESOURCE_LIMIT'):
            async with turn(live, context()):
                pytest.fail('evicted an in-flight breaker')
        assert len(live.breakers) == BREAKER_CAPACITY
        assert all(entry.in_flight == 1 for entry in live.breakers.values())
    assert not live.users and not live.models


@pytest.mark.asyncio
async def test_production_deadline_runner_propagates_cancellation_and_joins_operation():
    entered, closed = asyncio.Event(), asyncio.Event()
    async def blocked():
        try:
            entered.set()
            await asyncio.Event().wait()
        finally:
            closed.set()
    task = asyncio.create_task(DeadlineRunner().run(blocked, deadline=asyncio.get_running_loop().time()+25,
                                                   timeout_kind='total_timeout'))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed.is_set()
    with pytest.raises(ProcessingError) as caught:
        await DeadlineRunner().run(blocked, deadline=asyncio.get_running_loop().time(), timeout_kind='total_timeout')
    assert caught.value.retry_reason == 'total_timeout'
