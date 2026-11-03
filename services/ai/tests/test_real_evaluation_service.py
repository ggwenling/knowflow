import asyncio
import importlib.util
import json
import socket
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "real_evaluation_service", ROOT / "evaluation/collector/real_service.py")
real_service = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(real_service)


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch):
    """Reject real outbound network; loopback MockTransport paths stay local."""

    def refuse(*_args, **_kwargs):
        raise RuntimeError("EXTERNAL_NETWORK_DISABLED_IN_TEST")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket.socket, "sendto", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


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


def test_corrupt_shared_ledger_fails_closed(monkeypatch, tmp_path):
    configure_real_service(monkeypatch, tmp_path)
    ledger_path = tmp_path / "ledger.sqlite3"
    with sqlite3.connect(ledger_path) as db:
        db.execute("CREATE TABLE reservations (unexpected INTEGER)")
        db.commit()

    with pytest.raises(RuntimeError) as error:
        real_service.create_real_app()

    assert str(error.value) == "EVALUATION_SERVICE_NOT_READY: KNOWFLOW_BUDGET_LEDGER_PATH"


def test_ledger_missing_request_id_column_fails_closed(monkeypatch, tmp_path):
    configure_real_service(monkeypatch, tmp_path)
    ledger_path = tmp_path / "ledger.sqlite3"
    with sqlite3.connect(ledger_path) as db:
        db.execute("CREATE TABLE reservations (microyuan INTEGER NOT NULL)")
        db.commit()

    with pytest.raises(RuntimeError) as error:
        real_service.create_real_app()

    assert str(error.value) == "EVALUATION_SERVICE_NOT_READY: KNOWFLOW_BUDGET_LEDGER_PATH"


def test_ledger_insert_trigger_failure_fails_closed(monkeypatch, tmp_path):
    configure_real_service(monkeypatch, tmp_path)
    # Build a normal ledger first, then attach a rejecting trigger.
    from knowflow_ai.budget import BudgetLedger
    BudgetLedger(tmp_path / "ledger.sqlite3")
    with sqlite3.connect(tmp_path / "ledger.sqlite3") as db:
        db.execute(
            "CREATE TRIGGER reject_reservations BEFORE INSERT ON reservations "
            "BEGIN SELECT RAISE(ABORT, 'blocked'); END")
        db.commit()

    with pytest.raises(RuntimeError) as error:
        real_service.create_real_app()

    assert str(error.value) == "EVALUATION_SERVICE_NOT_READY: KNOWFLOW_BUDGET_LEDGER_PATH"


def test_soft_stopped_shared_ledger_fails_closed(monkeypatch, tmp_path):
    prices, _policies, _price_file, _policy_file = configure_real_service(monkeypatch, tmp_path)
    from knowflow_ai.budget import BudgetLedger, SOFT_STOP_MICROYUAN

    ledger = BudgetLedger(tmp_path / "ledger.sqlite3")
    quote = prices["deepseek-flash"]
    # One large paid reservation to reach soft stop exactly.
    ledger.reserve(
        "soft-stop-seed",
        provider="deepseek",
        model="deepseek-flash",
        input_tokens_upper=SOFT_STOP_MICROYUAN,
        output_tokens_upper=0,
        quote=quote,
    )
    assert ledger.summary()["reserved_microyuan"] >= SOFT_STOP_MICROYUAN

    with pytest.raises(RuntimeError) as error:
        real_service.create_real_app()

    assert str(error.value) == "EVALUATION_SERVICE_NOT_READY: KNOWFLOW_BUDGET_LEDGER_PATH"


def test_real_app_uses_product_adapters_with_mock_transport(monkeypatch, tmp_path):
    configure_real_service(monkeypatch, tmp_path)
    from knowflow_ai import answering, embedding

    requests_seen = []

    def mock_client(timeout, **_kwargs):
        def handler(request):
            requests_seen.append(str(request.url))
            return httpx.Response(500)

        return httpx.AsyncClient(timeout=timeout, trust_env=False,
                                 transport=httpx.MockTransport(handler))

    monkeypatch.setattr(embedding, "build_async_client", mock_client)
    monkeypatch.setattr(answering, "build_async_client", mock_client)

    app = real_service.create_real_app()
    assert app.state.evaluation_ai_port == 8000
    factories = app.state.evaluation_factories
    embedding_adapter = factories._embedding["adapter_factory"]()
    llm_adapter = factories._llm["adapter_factory"]()
    embedding_guard = factories.embedding_factory()
    llm_guard = factories.llm_factory()
    try:
        assert isinstance(embedding_adapter, embedding.SiliconFlowEmbeddingAdapter)
        assert isinstance(llm_adapter, answering.DeepSeekAdapter)
        assert embedding_adapter.settings.model == "BAAI/bge-m3"
        assert embedding_adapter.settings.dimensions == 1024
        assert llm_adapter.settings.model == "deepseek-flash"

        from knowflow_ai.adapters import ProcessingError

        async def exercise_guards():
            with pytest.raises(ProcessingError) as emb_error:
                await embedding_guard.embed(["hello"], request_id="emb-test-1")
            assert emb_error.value.code == "MODEL_FAILURE"
            mid = factories._ledger.summary()
            assert mid["paid_reservations"] == 1
            assert any("/embeddings" in url for url in requests_seen)
            with pytest.raises(ProcessingError) as llm_error:
                await llm_guard.generate(
                    "q", [{"source_id": "s1", "text_content": "t"}],
                    request_id="llm-test-1")
            assert llm_error.value.code == "MODEL_FAILURE"
            assert factories._ledger.summary()["paid_reservations"] == 2
            assert any("/chat/completions" in url for url in requests_seen)

        assert factories._ledger.summary()["paid_reservations"] == 0
        asyncio.run(exercise_guards())
        assert len(requests_seen) == 2
    finally:
        async def close_adapters():
            await embedding_adapter.aclose()
            await llm_adapter.aclose()
            await embedding_guard.aclose()
            await llm_guard.aclose()
        asyncio.run(close_adapters())


def test_main_binds_loopback_only(monkeypatch, tmp_path):
    configure_real_service(monkeypatch, tmp_path)
    from knowflow_ai import answering, embedding

    def mock_client(timeout, **_kwargs):
        return httpx.AsyncClient(timeout=timeout, trust_env=False,
                                 transport=httpx.MockTransport(
                                     lambda _request: httpx.Response(500)))

    monkeypatch.setattr(embedding, "build_async_client", mock_client)
    monkeypatch.setattr(answering, "build_async_client", mock_client)
    captured = {}

    def fake_run(app, host, port, **_kwargs):
        captured["host"] = host
        captured["port"] = port
        captured["app"] = app

    import uvicorn
    monkeypatch.setattr(uvicorn, "run", fake_run)
    real_service.main()
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8000
