"""App-owned, immediate provider admission, deadlines and generation-safe breakers."""
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import hashlib
import hmac
import json
import secrets
import time
from typing import Literal
from uuid import UUID

from .adapters import ProcessingError
from .provider_limits import ProviderLimits, TimeoutProfile
from .provider_observability import normalize_usage

BUSY_MESSAGE = '模型请求繁忙，请稍后重试。'
BREAKER_CAPACITY = 1024
BREAKER_IDLE_SECONDS = 600


def model_busy():
    return ProcessingError('RESOURCE_LIMIT', 429, retryable=True)


def is_model_busy(error):
    return isinstance(error, ProcessingError) and error.status == 429 and error.code == 'RESOURCE_LIMIT'


def timeout_error(kind):
    return ProcessingError('PROCESSING_TIMEOUT', 504, retryable=True, retry_reason=kind)


class DeadlineRunner:
    async def run(self, operation, *, deadline, timeout_kind):
        try:
            async with asyncio.timeout_at(deadline):
                return await operation()
        except TimeoutError:
            raise timeout_error(timeout_kind) from None


@dataclass(frozen=True)
class ModelCallContext:
    request_id: str
    owner_id: UUID
    custom_id: UUID | None = None
    purpose: Literal['answer', 'repair', 'probe'] = 'answer'

    def __post_init__(self):
        if (not isinstance(self.owner_id, UUID) or not self.request_id
                or self.purpose not in ('answer', 'repair', 'probe')
                or (self.custom_id is not None and not isinstance(self.custom_id, UUID))):
            raise ValueError('INVALID_MODEL_CALL_CONTEXT')


@dataclass
class CallState:
    turn: 'TurnState'
    started: float
    dispatched_at: float | None = None
    first_content_at: float | None = None
    provider_called: bool = False
    output_started: bool = False
    client_output_started: bool = False
    usage: dict | None = None
    failure_category: str | None = None
    first_token_observation: str | None = None
    dispatched: asyncio.Event = field(default_factory=asyncio.Event)
    first_content: asyncio.Event = field(default_factory=asyncio.Event)

    def dispatch(self):
        self.dispatched_at = self.turn.runtime.clock()
        self.dispatched.set()

    def observe_content(self):
        if not self.first_content.is_set():
            self.first_content_at = self.turn.runtime.clock()
            self.output_started = True
            self.first_content.set()

    def observe_usage(self, metadata):
        usage = normalize_usage(metadata)
        if usage is not None:
            self.usage = usage

    def mark_client_output_started(self):
        self.client_output_started = True


@dataclass
class Breaker:
    state: str = 'CLOSED'
    failures: int = 0
    generation: int = 0
    reopen_at: float = 0
    in_flight: int = 0
    last_used: float = 0


@dataclass
class BreakerToken:
    entry: Breaker
    generation: int
    half_open: bool
    settled: bool = False


@dataclass
class TurnState:
    runtime: 'ProviderRuntime'
    context: ModelCallContext
    profile: TimeoutProfile
    token: BreakerToken
    deadline: float

    def new_attempt(self):
        return CallState(self, self.runtime.clock())


class ProviderRuntime:
    def __init__(self, limits=None, *, clock=time.monotonic, deadline_runner=None):
        self.limits = limits or ProviderLimits.from_environment()
        self.clock = clock
        self.deadline_runner = deadline_runner or DeadlineRunner()
        self.users = {}
        self.models = {}
        self.breakers = {}
        self._salt = secrets.token_bytes(32)

    def model_key(self, context, *, protocol, endpoint, model, key):
        if context.custom_id is None:
            return ('deepseek', model)
        fingerprint = hmac.new(self._salt, json.dumps([protocol, endpoint, model, key]).encode(),
                               hashlib.sha256).digest()
        return (context.owner_id, context.custom_id, fingerprint)

    def _breaker_token(self, key):
        now = self.clock()
        # Sweep idle entries, without ever evicting live or unexpired open state.
        for old_key, old in list(self.breakers.items()):
            if (not old.in_flight and old.state != 'HALF_OPEN' and now >= old.reopen_at
                    and now - old.last_used >= BREAKER_IDLE_SECONDS):
                del self.breakers[old_key]
        if key not in self.breakers:
            if len(self.breakers) >= BREAKER_CAPACITY:
                candidates = [(entry.last_used, old_key) for old_key, entry in self.breakers.items()
                              if not entry.in_flight and entry.state != 'HALF_OPEN' and now >= entry.reopen_at]
                if not candidates:
                    raise model_busy()
                del self.breakers[min(candidates, key=lambda item: item[0])[1]]
            self.breakers[key] = Breaker(last_used=now)
        entry = self.breakers[key]
        if entry.state == 'HALF_OPEN' or (entry.state == 'OPEN' and now < entry.reopen_at):
            raise ProcessingError('AI_PROCESSING_FAILED', 503, retryable=True, retry_reason='circuit_open')
        if entry.state == 'OPEN':
            entry.state = 'HALF_OPEN'
            entry.generation += 1
        entry.in_flight += 1
        entry.last_used = now
        return BreakerToken(entry, entry.generation, entry.state == 'HALF_OPEN')

    def settle(self, token, outcome, category=None):
        if token.settled:
            return
        token.settled = True
        entry = token.entry
        entry.in_flight -= 1
        entry.last_used = self.clock()
        if token.generation != entry.generation:
            return
        if outcome == 'success':
            entry.state, entry.failures = 'CLOSED', 0
            if token.half_open:
                entry.generation += 1
        elif outcome == 'failure':
            entry.failures += 1
            if token.half_open or entry.failures >= self.limits.failure_threshold:
                self._open(entry)
        elif token.half_open:
            # Cancellation/neutral releases the probe without counting a failure.
            self._open(entry)

    def _open(self, entry):
        entry.state = 'OPEN'
        entry.generation += 1
        entry.reopen_at = self.clock() + self.limits.cooldown

    @asynccontextmanager
    async def turn(self, context, model_key, profile):
        user_key = (context.owner_id, context.custom_id is not None)
        model = (context.owner_id, context.custom_id) if context.custom_id is not None else None
        if (self.users.get(user_key, 0) >= self.limits.per_user
                or (model is not None and self.models.get(model, 0) >= self.limits.per_model)):
            raise model_busy()
        token = self._breaker_token(model_key)
        self.users[user_key] = self.users.get(user_key, 0) + 1
        if model is not None:
            self.models[model] = self.models.get(model, 0) + 1
        try:
            yield TurnState(self, context, profile, token, self.clock() + profile.total)
        except BaseException as error:
            neutral = (isinstance(error, asyncio.CancelledError) or not isinstance(error, ProcessingError)
                       or error.status in (400, 429) and error.provider_status is None
                       or error.retry_reason in ('circuit_open', 'local_budget', 'local_input')
                       or (error.provider_status is None and error.status != 504 and not error.retryable
                           and error.code != 'AI_PROCESSING_FAILED')
                       or (context.purpose == 'probe' and error.provider_status in (400, 422, 501)))
            self.settle(token, 'neutral' if neutral else 'failure', getattr(error, 'retry_reason', None))
            raise
        else:
            self.settle(token, 'success')
        finally:
            for counts, key in ((self.users, user_key), (self.models, model)):
                if key is not None:
                    counts[key] -= 1
                    if not counts[key]:
                        del counts[key]


async def run_attempt(operation, state):
    """Race first-content against dispatch, keeping cancellation fully joined."""
    runner = state.turn.runtime.deadline_runner

    async def first_deadline():
        await state.dispatched.wait()
        if state.first_content.is_set():
            return
        await runner.run(state.first_content.wait,
                         deadline=state.dispatched_at + state.turn.profile.first,
                         timeout_kind='first_token_timeout')

    task = asyncio.create_task(operation())
    first = asyncio.create_task(first_deadline())
    try:
        done, _ = await asyncio.wait((task, first), return_when=asyncio.FIRST_COMPLETED)
        if first in done:
            first.result()
        return await task
    finally:
        for pending in (task, first):
            if not pending.done():
                pending.cancel()
        await asyncio.gather(task, first, return_exceptions=True)
