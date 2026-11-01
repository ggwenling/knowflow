"""Proxy-environment resilience for adapter-owned HTTP clients.

A malformed ``NO_PROXY`` entry used to raise ``httpx.InvalidURL`` while the
adapter client was being constructed, which escapes as an unhandled error
instead of the intended fail-closed response. These cases pin the degradation.
"""
from pathlib import Path

import importlib.util

import httpx
import pytest

from knowflow_ai.embedding import EmbeddingSettings, SiliconFlowEmbeddingAdapter
from knowflow_ai.http_client import _validated_environment_proxy, build_async_client
from knowflow_ai.java_client import JavaGateway
from knowflow_ai.protocol import ContractConsumer


KEY = "synthetic-test-key-" + "x" * 40
SECRET = "test-only-java-gateway-secret-" + "x" * 32
ROOT = Path(__file__).resolve().parents[3]
MALFORMED_NO_PROXY = "localhost,127.0.0.1,::1,[::1]"


@pytest.fixture
def malformed_proxy_environment(monkeypatch):
    monkeypatch.setenv("NO_PROXY", MALFORMED_NO_PROXY)
    monkeypatch.setenv("no_proxy", MALFORMED_NO_PROXY)
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7890")
    monkeypatch.setenv("https_proxy", "http://127.0.0.1:7890")


def test_client_construction_survives_unparseable_no_proxy(malformed_proxy_environment):
    client = build_async_client(20.0)
    assert client.trust_env is False
    client._transport.__class__  # transport is built, not deferred


@pytest.mark.asyncio
async def test_provider_fallback_keeps_outbound_proxy(malformed_proxy_environment):
    client = build_async_client(20.0, environment_proxy_fallback=True)
    assert client.trust_env is False
    assert _validated_environment_proxy() == httpx.URL("http://127.0.0.1:7890")
    await client.aclose()


@pytest.mark.asyncio
async def test_gateway_never_adopts_environment_proxy(malformed_proxy_environment):
    contract = ContractConsumer(ROOT / "contracts/schemas/protocol.schema.json")
    gateway = JavaGateway("http://java.test", SECRET, contract)
    assert gateway._client.trust_env is False
    await gateway.aclose()


def test_valid_environment_still_trusted(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "localhost,127.0.0.1")
    monkeypatch.setenv("no_proxy", "localhost,127.0.0.1")
    client = build_async_client(20.0)
    assert client.trust_env is True


@pytest.mark.asyncio
async def test_embedding_adapter_constructs_under_malformed_no_proxy(
        malformed_proxy_environment):
    adapter = SiliconFlowEmbeddingAdapter(EmbeddingSettings(api_key=KEY))
    assert adapter._owns_client is True
    await adapter.aclose()


@pytest.mark.asyncio
async def test_socks_proxy_without_extra_degrades_instead_of_failing(monkeypatch):
    if importlib.util.find_spec("socksio") is not None:
        pytest.skip("socks extra installed; the unsupported-transport path cannot be hit")
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("https_proxy", raising=False)
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.delenv("http_proxy", raising=False)
    monkeypatch.setenv("ALL_PROXY", "socks5://127.0.0.1:1080")
    monkeypatch.setenv("all_proxy", "socks5://127.0.0.1:1080")
    client = build_async_client(20.0, environment_proxy_fallback=True)
    assert client.trust_env is False
    await client.aclose()
