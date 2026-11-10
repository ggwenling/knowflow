from datetime import datetime, timedelta, timezone
import os

import httpx
import pytest

from knowflow_ai.answering import LlmSettings
from knowflow_ai.budget import BudgetLedger
from knowflow_ai.embedding import EmbeddingSettings
from knowflow_ai.provider_probe import ProviderReadiness, probe_provider


def _settings():
    return LlmSettings(api_key="fake-key-" * 8), EmbeddingSettings(api_key="fake-key-" * 8)


@pytest.mark.asyncio
async def test_probe_uses_models_endpoint_without_chat_or_embedding_tokens():
    paths = []

    async def handler(request):
        paths.append(request.url.path)
        return httpx.Response(200, json={"data": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await probe_provider("llm", base_url="https://api.deepseek.com",
                                      api_key="fake-key-" * 8, timeout_seconds=5,
                                      client=client)
    assert result == {"status": "UP"}
    assert paths == ["/models"]


@pytest.mark.asyncio
async def test_probe_maps_5xx_and_429_to_down():
    async def handler(request):
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await probe_provider("llm", base_url="https://api.deepseek.com",
                                      api_key="fake-key-" * 8, timeout_seconds=5,
                                      client=client)
    assert result == {"status": "DOWN", "reason": "PROVIDER_ERROR", "provider_status": 503}

    async def limited(request):
        return httpx.Response(429)

    async with httpx.AsyncClient(transport=httpx.MockTransport(limited)) as client:
        result = await probe_provider("llm", base_url="https://api.deepseek.com",
                                      api_key="fake-key-" * 8, timeout_seconds=5,
                                      client=client)
    assert result == {"status": "DOWN", "reason": "RATE_LIMITED", "provider_status": 429}


@pytest.mark.asyncio
async def test_probe_maps_timeout_and_auth_rejection():
    async def timeout(request):
        raise httpx.ReadTimeout("synthetic", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as client:
        result = await probe_provider("llm", base_url="https://api.deepseek.com",
                                      api_key="fake-key-" * 8, timeout_seconds=5,
                                      client=client)
    assert result == {"status": "DOWN", "reason": "TIMEOUT"}

    async def rejected(request):
        return httpx.Response(401)

    async with httpx.AsyncClient(transport=httpx.MockTransport(rejected)) as client:
        result = await probe_provider("llm", base_url="https://api.deepseek.com",
                                      api_key="fake-key-" * 8, timeout_seconds=5,
                                      client=client)
    assert result == {"status": "DOWN", "reason": "AUTH_REJECTED", "provider_status": 401}


@pytest.mark.asyncio
async def test_readiness_combines_checks_and_caches(monkeypatch):
    llm, embedding = _settings()
    probe_calls = []

    async def probe(name, settings):
        probe_calls.append(name)
        if name == "llm":
            return {"status": "DOWN", "reason": "PROVIDER_ERROR", "provider_status": 503}
        return {"status": "UP"}

    readiness = ProviderReadiness(timeout_seconds=5, ttl_seconds=60,
                                  settings_loader=lambda env: (llm, embedding),
                                  probe=probe)
    first = await readiness.check()
    second = await readiness.check()
    assert first["status"] == "UNAVAILABLE"
    assert first["checks"]["llm"]["status"] == "DOWN"
    assert first["checks"]["embedding"]["status"] == "UP"
    assert first["checks"]["budget"]["status"] == "UP"
    assert second == first
    # One probe per provider; second check served from the TTL cache.
    assert sorted(probe_calls) == ["embedding", "llm"]


@pytest.mark.asyncio
async def test_readiness_checks_only_active_run_and_project_stops():
    environment = dict(os.environ)
    path = environment["KNOWFLOW_BUDGET_LEDGER_PATH"]
    now = datetime.now(timezone.utc)
    quote = {"provider": "synthetic", "model": "fake", "input_cny_per_million": "1",
             "output_cny_per_million": "1", "source_url": "https://example.test/prices",
             "verified_by": "test", "verified_at": (now - timedelta(hours=1)).isoformat(),
             "valid_until": (now + timedelta(hours=1)).isoformat()}

    def reject(ledger, reason, amount):
        with pytest.raises(ValueError, match=reason):
            ledger.reserve(ledger.run_id or "legacy", provider="synthetic", model="fake",
                           input_tokens_upper=amount, output_tokens_upper=0, quote=quote)

    reject(BudgetLedger(path, run_id="previous", run_limit_microyuan=1), "BUDGET_RUN_EXCEEDED", 2)

    async def probe(_name, _settings):
        return {"status": "UP"}

    readiness = ProviderReadiness(environ=environment, ttl_seconds=0,
                                  settings_loader=lambda _env: _settings(), probe=probe)

    async def budget_status():
        return (await readiness.check())["checks"]["budget"]

    environment["KNOWFLOW_BUDGET_RUN_ID"] = ""
    environment["KNOWFLOW_BUDGET_RUN_LIMIT_MICROYUAN"] = ""
    assert await budget_status() == {"status": "UP"}
    environment["KNOWFLOW_BUDGET_RUN_ID"] = "current"
    assert await budget_status() == {"status": "DOWN", "reason": "BUDGET_CONFIGURATION_REQUIRED"}
    environment["KNOWFLOW_BUDGET_RUN_LIMIT_MICROYUAN"] = "1"
    assert await budget_status() == {"status": "UP"}
    reject(BudgetLedger(path, run_id="current", run_limit_microyuan=1), "BUDGET_RUN_EXCEEDED", 2)
    assert await budget_status() == {"status": "DOWN", "reason": "BUDGET_RUN_EXCEEDED"}
    environment["KNOWFLOW_BUDGET_RUN_LIMIT_MICROYUAN"] = "2"
    assert await budget_status() == {"status": "DOWN", "reason": "BUDGET_CONFIGURATION_REQUIRED"}
    environment["KNOWFLOW_BUDGET_RUN_ID"] = "next"
    assert await budget_status() == {"status": "UP"}
    reject(BudgetLedger(path), "BUDGET_EXCEEDED", 10_000_001)
    assert await budget_status() == {"status": "DOWN", "reason": "BUDGET_EXCEEDED"}
