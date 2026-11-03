import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from evaluation.collector import real_service


def configure_real_service(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    evidence_time = {
        "verified_at": (now - timedelta(minutes=1)).isoformat(),
        "valid_until": (now + timedelta(hours=1)).isoformat(),
    }
    prices = {
        "BAAI/bge-m3": {
            "provider": "siliconflow", "model": "BAAI/bge-m3",
            "input_cny_per_million": "1", "output_cny_per_million": "2",
            "source_url": "https://siliconflow.cn/pricing", "verified_by": "test-reviewer",
            **evidence_time,
        },
        "deepseek-flash": {
            "provider": "deepseek", "model": "deepseek-flash",
            "input_cny_per_million": "1", "output_cny_per_million": "2",
            "source_url": "https://deepseek.com/pricing", "verified_by": "test-reviewer",
            **evidence_time,
        },
    }
    policies = {
        "BAAI/bge-m3": {
            "provider": "siliconflow", "bound_kind": "provider_context_limit",
            "source_url": "https://siliconflow.cn/pricing", "verified_by": "test-reviewer",
            **evidence_time, "input_tokens_upper": 100_000,
            "output_tokens_upper": 1024, "max_payload_bytes": 1_000_000,
        },
        "deepseek-flash": {
            "provider": "deepseek", "bound_kind": "provider_context_limit",
            "source_url": "https://deepseek.com/pricing", "verified_by": "test-reviewer",
            **evidence_time, "input_tokens_upper": 100_000,
            "output_tokens_upper": 1024, "max_payload_bytes": 1_000_000,
        },
    }
    price_file = tmp_path / "prices.json"
    policy_file = tmp_path / "policies.json"
    price_file.write_text(json.dumps(prices), encoding="utf-8")
    policy_file.write_text(json.dumps(policies), encoding="utf-8")

    for name in (*real_service._REQUIRED_ENVIRONMENT, "KNOWFLOW_EVALUATION_AI_PORT",
                 "FAKE_EMBEDDING_KEY", "FAKE_LLM_KEY"):
        monkeypatch.delenv(name, raising=False)
    values = {
        "KNOWFLOW_BUDGET_LEDGER_PATH": str(tmp_path / "ledger.sqlite3"),
        "KNOWFLOW_BUDGET_PRICE_FILE": str(price_file),
        "KNOWFLOW_BUDGET_POLICY_FILE": str(policy_file),
        "KNOWFLOW_INTERNAL_SHARED_SECRET": "test-internal-secret-" + "i" * 40,
        "KNOWFLOW_EVALUATION_CONTROL_SECRET": "test-control-secret-" + "c" * 40,
        "KNOWFLOW_AI_DATABASE_URL": "postgresql://localhost/knowflow_test",
        "KNOWFLOW_EMBEDDING_KEY_ENV": "FAKE_EMBEDDING_KEY",
        "FAKE_EMBEDDING_KEY": "test-embedding-key-" + "e" * 40,
        "KNOWFLOW_EMBEDDING_BASE_URL": "https://api.siliconflow.cn/v1",
        "KNOWFLOW_EMBEDDING_MODEL": "BAAI/bge-m3",
        "KNOWFLOW_EMBEDDING_DIMENSIONS": "1024",
        "KNOWFLOW_LLM_KEY_ENV": "FAKE_LLM_KEY",
        "FAKE_LLM_KEY": "test-llm-key-" + "l" * 40,
        "KNOWFLOW_LLM_BASE_URL": "https://api.deepseek.com",
        "KNOWFLOW_LLM_MODEL": "deepseek-flash",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return prices, policies, price_file, policy_file


@pytest.mark.parametrize("name", real_service._REQUIRED_ENVIRONMENT)
def test_missing_required_environment_fails_closed(monkeypatch, tmp_path, name):
    configure_real_service(monkeypatch, tmp_path)
    monkeypatch.delenv(name)

    with pytest.raises(RuntimeError) as error:
        real_service.create_real_app()

    message = str(error.value)
    assert message.startswith("EVALUATION_SERVICE_NOT_READY:")
    assert name in message
    assert "test-internal-secret-" not in message
    assert "test-control-secret-" not in message


@pytest.mark.parametrize("name", ("FAKE_EMBEDDING_KEY", "FAKE_LLM_KEY"))
def test_missing_selected_provider_key_fails_closed(monkeypatch, tmp_path, name):
    configure_real_service(monkeypatch, tmp_path)
    monkeypatch.delenv(name)

    with pytest.raises(RuntimeError) as error:
        real_service.create_real_app()

    assert name in str(error.value)
    assert "test-embedding-key-" not in str(error.value)
    assert "test-llm-key-" not in str(error.value)


def test_short_control_secret_is_reported_by_variable_name(monkeypatch, tmp_path):
    configure_real_service(monkeypatch, tmp_path)
    monkeypatch.setenv("KNOWFLOW_EVALUATION_CONTROL_SECRET", "too-short")

    with pytest.raises(RuntimeError) as error:
        real_service.create_real_app()

    assert str(error.value) == (
        "EVALUATION_SERVICE_NOT_READY: KNOWFLOW_EVALUATION_CONTROL_SECRET")
    assert "too-short" not in str(error.value)


def test_current_models_must_exist_in_price_and_policy_files(monkeypatch, tmp_path):
    _prices, _policies, price_file, _policy_file = configure_real_service(monkeypatch, tmp_path)
    prices = json.loads(price_file.read_text(encoding="utf-8"))
    del prices["deepseek-flash"]
    price_file.write_text(json.dumps(prices), encoding="utf-8")

    with pytest.raises(RuntimeError) as error:
        real_service.create_real_app()

    assert "KNOWFLOW_BUDGET_PRICE_FILE" in str(error.value)
    assert "llm.model" in str(error.value)


def test_expired_policy_fails_closed(monkeypatch, tmp_path):
    _prices, policies, _price_file, policy_file = configure_real_service(monkeypatch, tmp_path)
    policies["deepseek-flash"]["valid_until"] = "2000-01-01T00:00:00Z"
    policy_file.write_text(json.dumps(policies), encoding="utf-8")

    with pytest.raises(RuntimeError) as error:
        real_service.create_real_app()

    assert str(error.value) == "EVALUATION_SERVICE_NOT_READY: KNOWFLOW_BUDGET_POLICY_FILE"


def test_expired_price_fails_closed(monkeypatch, tmp_path):
    prices, _policies, price_file, _policy_file = configure_real_service(monkeypatch, tmp_path)
    prices["deepseek-flash"]["valid_until"] = "2000-01-01T00:00:00Z"
    price_file.write_text(json.dumps(prices), encoding="utf-8")

    with pytest.raises(RuntimeError) as error:
        real_service.create_real_app()

    message = str(error.value)
    assert message.startswith("EVALUATION_SERVICE_NOT_READY:")
    assert "KNOWFLOW_BUDGET_PRICE_FILE" in message
    assert "test-reviewer" not in message


def test_real_app_uses_product_adapters_with_mock_transport(monkeypatch, tmp_path):
    configure_real_service(monkeypatch, tmp_path)
    from knowflow_ai import answering, embedding

    def mock_client(timeout, **_kwargs):
        return httpx.AsyncClient(timeout=timeout, trust_env=False,
                                 transport=httpx.MockTransport(
                                     lambda _request: httpx.Response(500)))

    monkeypatch.setattr(embedding, "build_async_client", mock_client)
    monkeypatch.setattr(answering, "build_async_client", mock_client)

    app = real_service.create_real_app()
    assert app.state.evaluation_ai_port == 8000
    factories = app.state.evaluation_factories
    embedding_adapter = factories._embedding["adapter_factory"]()
    llm_adapter = factories._llm["adapter_factory"]()
    try:
        assert isinstance(embedding_adapter, embedding.SiliconFlowEmbeddingAdapter)
        assert isinstance(llm_adapter, answering.DeepSeekAdapter)
        assert embedding_adapter.settings.model == "BAAI/bge-m3"
        assert embedding_adapter.settings.dimensions == 1024
        assert llm_adapter.settings.model == "deepseek-flash"
    finally:
        async def close_adapters():
            await embedding_adapter.aclose()
            await llm_adapter.aclose()
        asyncio.run(close_adapters())
