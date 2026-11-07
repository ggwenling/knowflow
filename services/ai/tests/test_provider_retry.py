import json
import os
from pathlib import Path

import httpx
import pytest

from knowflow_ai.adapters import ProcessingError
from knowflow_ai.answering import DeepSeekAdapter, LlmSettings
from knowflow_ai.budget import BudgetLedger
from knowflow_ai.embedding import EmbeddingSettings, SiliconFlowEmbeddingAdapter
from knowflow_ai.provider_retry import ProviderRetryPolicy

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
