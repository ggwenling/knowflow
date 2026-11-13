import asyncio
from dataclasses import asdict
import json
import os
from pathlib import Path

import httpx
import pytest

from knowflow_ai.adapters import ProcessingError
from knowflow_ai.answering import DeepSeekAdapter, LlmSettings
from knowflow_ai.budget import BudgetLedger
from knowflow_ai.embedding import EmbeddingSettings, SiliconFlowEmbeddingAdapter
from knowflow_ai.provider_retry import ProviderRetryPolicy, classify_provider_failure, run_provider_with_retry
from provider_test_helpers import FakeClock

FAKE_KEY = "fake-key-" * 8
ANSWER = {"has_answer": False, "answer": "", "source_ids": []}
POLICY = ProviderRetryPolicy(max_attempts=3, base_seconds=0, total_seconds=5)


def _llm_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _llm_response():
    return httpx.Response(200, json={
        "model": "deepseek-flash",
        "choices": [{"finish_reason": "stop",
                     "message": {"content": json.dumps(ANSWER)}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    })


@pytest.mark.asyncio
async def test_5xx_retries_then_succeeds_and_reserves_each_attempt():
    calls = []

    async def handler(request):
        calls.append(request)
        return _llm_response() if len(calls) == 3 else httpx.Response(503)

    async with _llm_client(handler) as client:
        adapter = DeepSeekAdapter(LlmSettings(api_key=FAKE_KEY), client,
                                  retry_policy=POLICY)
        result = await adapter.generate("synthetic", [], request_id="retry-success")
    assert result == ANSWER
    assert len(calls) == 3
    summary = BudgetLedger(os.environ["KNOWFLOW_BUDGET_LEDGER_PATH"]).summary()
    assert summary["paid_reservations"] == 3


@pytest.mark.asyncio
async def test_consecutive_5xx_fails_and_records_reason(caplog):
    calls = []

    async def handler(request):
        calls.append(request)
        return httpx.Response(503)

    async with _llm_client(handler) as client:
        adapter = DeepSeekAdapter(LlmSettings(api_key=FAKE_KEY), client,
                                  retry_policy=POLICY)
        with pytest.raises(ProcessingError) as error:
            await adapter.generate("synthetic", [], request_id="retry-exhausted")
    assert error.value.retryable is True
    assert error.value.provider_status == 503
    assert len(calls) == 3
    assert "provider_retry_exhausted" in caplog.text
    assert "HTTP_503" in caplog.text
    summary = BudgetLedger(os.environ["KNOWFLOW_BUDGET_LEDGER_PATH"]).summary()
    assert summary["paid_reservations"] == 3


@pytest.mark.asyncio
async def test_non_retryable_4xx_is_not_retried():
    calls = []

    async def handler(request):
        calls.append(request)
        return httpx.Response(400)

    async with _llm_client(handler) as client:
        adapter = DeepSeekAdapter(LlmSettings(api_key=FAKE_KEY), client,
                                  retry_policy=POLICY)
        with pytest.raises(ProcessingError) as error:
            await adapter.generate("synthetic", [], request_id="retry-4xx")
    assert error.value.retryable is False
    assert error.value.provider_status == 400
    assert len(calls) == 1
    summary = BudgetLedger(os.environ["KNOWFLOW_BUDGET_LEDGER_PATH"]).summary()
    assert summary["paid_reservations"] == 1


@pytest.mark.asyncio
async def test_429_honours_retry_after():
    calls = []

    async def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return _llm_response()

    async with _llm_client(handler) as client:
        adapter = DeepSeekAdapter(LlmSettings(api_key=FAKE_KEY), client,
                                  retry_policy=POLICY)
        result = await adapter.generate("synthetic", [], request_id="retry-429")
    assert result == ANSWER
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_retry_total_duration_cap_stops_retrying(caplog):
    calls = []

    async def handler(request):
        calls.append(request)
        return httpx.Response(503)

    policy = ProviderRetryPolicy(max_attempts=3, base_seconds=0, total_seconds=0)
    async with _llm_client(handler) as client:
        adapter = DeepSeekAdapter(LlmSettings(api_key=FAKE_KEY), client,
                                  retry_policy=policy)
        with pytest.raises(ProcessingError):
            await adapter.generate("synthetic", [], request_id="retry-cap")
    assert len(calls) == 1
    assert "provider_retry_abandoned" in caplog.text


@pytest.mark.asyncio
async def test_timeout_is_retried():
    calls = []

    async def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ReadTimeout("synthetic timeout", request=request)
        return _llm_response()

    async with _llm_client(handler) as client:
        adapter = DeepSeekAdapter(LlmSettings(api_key=FAKE_KEY), client,
                                  retry_policy=POLICY)
        result = await adapter.generate("synthetic", [], request_id="retry-timeout")
    assert result == ANSWER
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_budget_soft_stop_is_not_retried():
    model = "deepseek-flash"
    policy_path = Path(os.environ["KNOWFLOW_BUDGET_POLICY_FILE"])
    policies = json.loads(policy_path.read_text(encoding="utf-8"))
    policies[model]["input_tokens_upper"] = 10_000
    policy_path.write_text(json.dumps(policies), encoding="utf-8")
    quote = json.loads(Path(os.environ["KNOWFLOW_BUDGET_PRICE_FILE"]).read_text(encoding="utf-8"))[model]
    ledger_path = os.environ["KNOWFLOW_BUDGET_LEDGER_PATH"]
    ledger = BudgetLedger(ledger_path)
    ledger.reserve("initial", provider="deepseek", model=model,
                   input_tokens_upper=8_000_000, output_tokens_upper=0, quote=quote)
    calls = []

    async def handler(request):
        calls.append(request)
        return _llm_response()

    async with _llm_client(handler) as client:
        adapter = DeepSeekAdapter(LlmSettings(api_key=FAKE_KEY), client,
                                  retry_policy=POLICY)
        with pytest.raises(ProcessingError) as error:
            await adapter.generate("synthetic", [], request_id="retry-budget-stop")
    assert error.value.retryable is False
    assert calls == []
    assert BudgetLedger(ledger_path).summary()["paid_reservations"] == 1
    assert BudgetLedger(ledger_path).stop_reason() == "BUDGET_SOFT_STOP"


@pytest.mark.asyncio
async def test_embedding_retries_5xx():
    calls = []

    async def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={
            "model": "BAAI/bge-m3",
            "data": [{"index": 0, "embedding": [0.0] * 1023 + [1.0]}],
            "usage": {"prompt_tokens": 1, "total_tokens": 1},
        })

    async with _llm_client(handler) as client:
        adapter = SiliconFlowEmbeddingAdapter(
            EmbeddingSettings(api_key=FAKE_KEY), client, retry_policy=POLICY)
        result = await adapter.embed(["synthetic"], request_id="retry-embed")
    assert result["dimensions"] == 1024
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_streaming_retries_5xx_before_first_fragment():
    calls = []

    async def handler(request):
        calls.append(request)
        return httpx.Response(503)

    async with _llm_client(handler) as client:
        adapter = DeepSeekAdapter(LlmSettings(api_key=FAKE_KEY), client,
                                  retry_policy=POLICY)
        with pytest.raises(ProcessingError):
            async for _fragment in adapter.stream_content(
                    "synthetic", [], request_id="retry-stream"):
                pass
    # streaming retries only before any fragment is emitted
    assert len(calls) == 3


# Step 3: exercise policy with fake time; existing adapter/ledger assertions above
# continue to check their original public contracts.
@pytest.mark.parametrize('status', [None, 0, 200, 299, *range(300, 600), 600, 999])
def test_retry_classification_table(status):
    decision = classify_provider_failure(status=status)
    assert decision.retryable is (status == 429 or status is not None and 500 <= status <= 599)
    assert set(asdict(decision)) == {'retryable', 'reason'}
    assert decision.reason in {'unknown', 'redirect', 'auth', 'http_4xx', 'rate_limited', 'http_5xx'}
    for flag in ('output_started', 'client_output_started'):
        blocked = classify_provider_failure(status=status, **{flag: True})
        assert not blocked.retryable and blocked.reason == flag


@pytest.mark.parametrize('kind', [
    'connect_failure', 'connection_reset', 'connect_timeout', 'first_token_timeout', 'read_timeout',
    'total_timeout', 'outer_deadline', 'completion_validation', 'model_mismatch', 'parse', 'garbage',
    'response_too_large', 'encoding', 'content_filter', 'refusal', 'length_truncation', 'invalid_url',
    'unsupported_protocol', 'local_budget', 'admission', 'circuit_open', 'local_input', 'configuration',
    'cancelled', 'untrusted arbitrary error text', None,
])
def test_retry_classification_failure_kinds(kind):
    transient = kind in ('connect_failure', 'connection_reset', 'connect_timeout', 'first_token_timeout', 'read_timeout')
    decision = classify_provider_failure(failure_kind=kind)
    assert decision.retryable is transient
    assert decision.reason != 'untrusted arbitrary error text'
    assert not classify_provider_failure(failure_kind=kind, output_started=True).retryable
    assert not classify_provider_failure(failure_kind=kind, client_output_started=True).retryable


@pytest.mark.asyncio
@pytest.mark.parametrize('client', [False, True])
async def test_output_flag_is_rechecked_after_retry_delay(client):
    clock, calls, delays = FakeClock(), [], []
    output = False
    failure = ProcessingError('MODEL_FAILURE', 502, retryable=True, provider_status=503)

    async def operation():
        calls.append(clock.monotonic())
        raise failure

    async def sleep(delay):
        nonlocal output
        delays.append(delay)
        clock.advance(delay)
        output = True

    with pytest.raises(ProcessingError) as caught:
        await run_provider_with_retry(operation, policy=ProviderRetryPolicy(), request_id='output-delay',
                                      provider='synthetic', clock=clock.monotonic, sleep=sleep,
                                      **{('client_output_started' if client else 'output_started'): lambda: output})
    assert caught.value is failure
    assert calls == [0] and delays == [0.5]


@pytest.mark.asyncio
@pytest.mark.parametrize('hint,outer,attempts,delays', [
    (2, 5, 3, [2, 2]), (5, 5, 1, []), (600, 5, 1, []), (2, 1, 1, []), (0, 0, 1, []),
])
async def test_retry_after_uses_fake_clock_and_stops_when_budget_is_insufficient(hint, outer, attempts, delays):
    clock, calls, slept = FakeClock(), [], []
    failure = ProcessingError('MODEL_FAILURE', 502, retryable=True, provider_status=429, retry_after=hint)

    async def operation():
        calls.append(clock.monotonic())
        raise failure

    async def sleep(delay):
        slept.append(delay)
        clock.advance(delay)

    with pytest.raises(ProcessingError) as caught:
        await run_provider_with_retry(operation, policy=ProviderRetryPolicy(total_seconds=outer),
                                      request_id='retry-after', provider='synthetic', clock=clock.monotonic, sleep=sleep)
    assert caught.value is failure and len(calls) == attempts and slept == delays


@pytest.mark.asyncio
async def test_retry_checks_cancellation_before_backoff():
    calls, slept = [], []

    async def operation():
        calls.append(True)
        asyncio.current_task().cancel()
        raise ProcessingError('MODEL_FAILURE', 502, retryable=True)

    async def sleep(delay):
        slept.append(delay)

    task = asyncio.create_task(run_provider_with_retry(operation, policy=POLICY,
                              request_id='cancel', provider='synthetic', sleep=sleep))
    with pytest.raises(asyncio.CancelledError):
        await task
    assert calls == [True] and not slept


@pytest.mark.asyncio
@pytest.mark.parametrize('expired_during', ['attempt', 'sleep'])
async def test_retry_rechecks_cutoff_before_next_attempt(expired_during):
    clock, calls, delays = FakeClock(), [], []
    failure = ProcessingError('MODEL_TIMEOUT', 504, retryable=True, retry_reason='TIMEOUT')

    async def operation():
        calls.append(clock.monotonic())
        if expired_during == 'attempt':
            clock.advance(2)
        raise failure

    async def sleep(delay):
        delays.append(delay)
        # Scheduling/oversleep may use up more than the requested backoff.
        clock.advance(2)

    with pytest.raises(ProcessingError) as caught:
        await run_provider_with_retry(operation, policy=ProviderRetryPolicy(), request_id='cutoff',
                                      provider='synthetic', clock=clock.monotonic, sleep=sleep, outer_deadline=2)
    assert caught.value is failure
    assert calls == [0] and delays == ([] if expired_during == 'attempt' else [0.5])


@pytest.mark.asyncio
async def test_expired_outer_deadline_prevents_first_attempt():
    clock, calls = FakeClock(), []

    async def operation():
        calls.append(True)

    with pytest.raises(ProcessingError) as caught:
        await run_provider_with_retry(operation, policy=POLICY, request_id='expired', provider='synthetic',
                                      clock=clock.monotonic, outer_deadline=0)
    assert (caught.value.code, caught.value.status, caught.value.retryable) == ('PROCESSING_TIMEOUT', 504, False)
    assert not calls


@pytest.mark.asyncio
@pytest.mark.parametrize('path', ['answer', 'embedding', 'stream'])
@pytest.mark.parametrize('status', [302, 400, 401, 403, 404, 408, 422, 429, 501, 505, 599, 600])
async def test_legacy_paths_preserve_http_mapping_and_budget(path, status, monkeypatch):
    from test_provider_completion import forbid_wire_network
    forbid_wire_network(monkeypatch)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, headers={'Retry-After': '0'})

    async with _llm_client(handler) as client:
        with pytest.raises(ProcessingError) as caught:
            if path == 'embedding':
                adapter = SiliconFlowEmbeddingAdapter(EmbeddingSettings(api_key=FAKE_KEY), client, retry_policy=POLICY)
                await adapter.embed(['synthetic'], request_id='legacy-matrix')
            else:
                adapter = DeepSeekAdapter(LlmSettings(api_key=FAKE_KEY), client, retry_policy=POLICY)
                if path == 'stream':
                    async for _ in adapter.stream_content('synthetic', [], request_id='legacy-matrix'):
                        pytest.fail('HTTP error must not emit content')
                else:
                    await adapter.generate('synthetic', [], request_id='legacy-matrix')
    transient = status == 429 or 500 <= status <= 599
    assert (caught.value.code, caught.value.status, caught.value.retry_reason) == ('MODEL_FAILURE', 502, f'HTTP_{status}')
    assert caught.value.retryable is transient and caught.value.provider_status == status
    assert len(calls) == (3 if transient else 1)
    assert BudgetLedger(os.environ['KNOWFLOW_BUDGET_LEDGER_PATH']).summary()['paid_reservations'] == len(calls)


@pytest.mark.asyncio
async def test_legacy_stream_does_not_retry_after_emitting_content(monkeypatch):
    from test_provider_completion import forbid_wire_network
    forbid_wire_network(monkeypatch)
    calls, fragments = [], []

    class ResetAfterContent(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'data: {"model":"deepseek-flash","choices":[{"index":0,"delta":{"content":"partial"},"finish_reason":null}]}\n\n'
            raise httpx.ReadError('SECRET')

    def handler(request):
        calls.append(request)
        return httpx.Response(200, headers={'content-type': 'text/event-stream'}, stream=ResetAfterContent())

    async with _llm_client(handler) as client:
        adapter = DeepSeekAdapter(LlmSettings(api_key=FAKE_KEY), client, retry_policy=POLICY)
        with pytest.raises(ProcessingError) as caught:
            async for fragment in adapter.stream_content('synthetic', [], request_id='legacy-emitted'):
                fragments.append(fragment)
    assert fragments == ['partial'] and len(calls) == 1
    assert (caught.value.code, caught.value.status, caught.value.retry_reason) == ('MODEL_FAILURE', 502, 'TRANSPORT')
    assert BudgetLedger(os.environ['KNOWFLOW_BUDGET_LEDGER_PATH']).summary()['paid_reservations'] == 1
