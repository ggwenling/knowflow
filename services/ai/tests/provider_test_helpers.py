"""Event-driven provider tests: no real provider network or production-time waits."""
import asyncio
from uuid import UUID

import httpx
import httpx2

from knowflow_ai.provider_runtime import ProviderRuntime, ModelCallContext, timeout_error
from knowflow_ai.provider_limits import ProviderLimits
from knowflow_ai.langchain_answer import LangChainAnswerModel as ProductionModel, CustomModel

OWNER = UUID('11111111-1111-4111-8111-111111111111')


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class FakeDeadlineRunner:
    def __init__(self, clock):
        self.clock = clock
        self.pending = {}

    async def run(self, operation, *, deadline, timeout_kind):
        task = asyncio.create_task(operation())
        expired = asyncio.get_running_loop().create_future()
        self.pending[expired] = (deadline, task)
        try:
            if self.clock.monotonic() >= deadline:
                raise timeout_error(timeout_kind)
            done, _ = await asyncio.wait((task, expired), return_when=asyncio.FIRST_COMPLETED)
            if expired in done:
                raise timeout_error(timeout_kind)
            return task.result()
        finally:
            self.pending.pop(expired, None)
            expired.cancel()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def advance(self, seconds):
        self.clock.advance(seconds)
        tasks = []
        for expired, (deadline, task) in list(self.pending.items()):
            if deadline <= self.clock.monotonic():
                expired.set_result(None)
                tasks.append(task)
        # Wait until run() has cancelled and joined all expired operations.
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.sleep(0)


class ControlledByteStream(httpx.AsyncByteStream, httpx2.AsyncByteStream):
    def __init__(self, prefix=b'', tail=b''):
        self.prefix, self.tail = prefix, tail
        self.entered, self.release, self.closed = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def __aiter__(self):
        try:
            if self.prefix:
                yield self.prefix
            self.entered.set()
            await self.release.wait()
            if self.tail:
                yield self.tail
        finally:
            self.closed.set()

    async def aclose(self):
        self.closed.set()


def runtime_factory(limits=None, **overrides):
    clock = FakeClock()
    runner = FakeDeadlineRunner(clock)
    return ProviderRuntime(limits or ProviderLimits(**overrides), clock=clock.monotonic, deadline_runner=runner)


def call_context(settings, *, owner=OWNER, request_id='provider-test', probe=False):
    return ModelCallContext(request_id, owner, settings.id if isinstance(settings, CustomModel) else None,
                            'probe' if probe else 'answer')


def LangChainAnswerModel(settings, *, runtime=None, call_context=None, **kwargs):
    """Explicit synthetic owner and isolated app runtime for direct SDK tests."""
    if kwargs.get('transport') is None:
        raise AssertionError('Provider test requires an injected transport')
    return ProductionModel(settings, runtime=runtime or runtime_factory(),
                           call_context=call_context or globals()['call_context'](settings, probe=kwargs.get('probe', False)),
                           **kwargs)
