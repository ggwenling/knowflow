import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from knowflow_ai.adapters import ProcessingError
from knowflow_ai.answering import DeepSeekAdapter, LlmSettings
from knowflow_ai.embedding import SiliconFlowEmbeddingAdapter, EmbeddingSettings
from knowflow_ai.budget import BudgetLedger
from pathlib import Path
import os
import importlib.util


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["embed", "generate", "stream"])
async def test_direct_provider_calls_require_budget_before_http(monkeypatch, operation):
    for key in ("KNOWFLOW_BUDGET_LEDGER_PATH", "KNOWFLOW_BUDGET_PRICE_FILE", "KNOWFLOW_BUDGET_POLICY_FILE"):
        monkeypatch.delenv(key, raising=False)
    calls = []
    async def transport(request):
        calls.append(request)
        return httpx.Response(500)
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        embedding = SiliconFlowEmbeddingAdapter(EmbeddingSettings(api_key="fake-key-" * 8), client)
        llm = DeepSeekAdapter(LlmSettings(api_key="fake-key-" * 8), client)
        with pytest.raises(ProcessingError, match="AI_PROCESSING_FAILED") as error:
            if operation == "embed":
                await embedding.embed(["synthetic"], request_id="probe")
            elif operation == "generate":
                await llm.generate("synthetic", [], request_id="probe")
            else:
                async for _ in llm.stream_content("synthetic", [], request_id="probe"):
                    pass
        assert error.value.retryable is False
    assert calls == []


@pytest.mark.asyncio
async def test_raw_adapter_failed_attempts_are_reserved_individually(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    model = "deepseek-flash"
    quote = {"provider": "deepseek", "model": model, "input_cny_per_million": "1",
             "output_cny_per_million": "2", "source_url": "https://example.test/prices",
             "verified_by": "synthetic-test", "verified_at": (now - timedelta(hours=1)).isoformat(),
             "valid_until": (now + timedelta(hours=1)).isoformat()}
    policy = {"provider": "deepseek", "bound_kind": "provider_context_limit",
              "verified_by": "synthetic-test", "source_url": "https://example.test/policy",
              "verified_at": quote["verified_at"], "valid_until": quote["valid_until"],
              "input_tokens_upper": 10000, "output_tokens_upper": 1024, "max_payload_bytes": 10000}
    for name, value in (("PRICE_FILE", {model: quote}), ("POLICY_FILE", {model: policy})):
        path = tmp_path / (name + ".json")
        path.write_text(json.dumps(value), encoding="utf-8")
        monkeypatch.setenv("KNOWFLOW_BUDGET_" + name, str(path))
    ledger_path = tmp_path / "budget.sqlite3"
    monkeypatch.setenv("KNOWFLOW_BUDGET_LEDGER_PATH", str(ledger_path))
    calls = []
    async def transport(request):
        calls.append(request)
        return httpx.Response(503)
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        adapter = DeepSeekAdapter(LlmSettings(api_key="fake-key-" * 8), client)
        for _ in range(2):
            with pytest.raises(ProcessingError):
                await adapter.generate("synthetic", [], request_id="same-product-request")
    assert len(calls) == 2
    assert BudgetLedger(ledger_path).summary()["paid_reservations"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("spent,input_upper,reason", [
    (8_000_000, 10_000, "BUDGET_SOFT_STOP"),
    (7_000_000, 2_000_000, "BUDGET_SOFT_STOP"),
    (7_000_000, 4_000_000, "BUDGET_EXCEEDED"),
])
async def test_provider_thresholds_stop_before_http(monkeypatch, caplog, spent, input_upper, reason):
    model = "deepseek-flash"
    policy_path = Path(os.environ["KNOWFLOW_BUDGET_POLICY_FILE"])
    policies = json.loads(policy_path.read_text())
    policies[model]["input_tokens_upper"] = input_upper
    policy_path.write_text(json.dumps(policies))
    quote = json.loads(Path(os.environ["KNOWFLOW_BUDGET_PRICE_FILE"]).read_text())[model]
    ledger = BudgetLedger(os.environ["KNOWFLOW_BUDGET_LEDGER_PATH"])
    ledger.reserve("initial", provider="deepseek", model=model, input_tokens_upper=spent,
                   output_tokens_upper=0, quote=quote)
    calls = []
    async def transport(request):
        calls.append(request)
        return httpx.Response(500)
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        adapter = DeepSeekAdapter(LlmSettings(api_key="fake-key-" * 8), client)
        with pytest.raises(ProcessingError) as error:
            await adapter.generate("synthetic", [], request_id="threshold")
    assert error.value.retryable is False
    assert reason in caplog.text
    assert calls == []
    assert ledger.summary()["paid_reservations"] == 1


def test_provider_budget_accepts_positive_siliconflow_price_source(tmp_path):
    from knowflow_ai.provider_budget import reserve_provider_call_sync

    now = datetime.now(timezone.utc)
    quote = {"provider": "siliconflow", "model": "BAAI/bge-m3",
             "input_cny_per_million": "1", "output_cny_per_million": "0",
             "source_url": "https://api.siliconflow.cn/pricing", "verified_by": "test-reviewer",
             "verified_at": (now - timedelta(minutes=1)).isoformat(),
             "valid_until": (now + timedelta(hours=1)).isoformat()}
    policy = {"provider": "siliconflow", "bound_kind": "provider_context_limit",
              "source_url": quote["source_url"], "verified_by": "test-reviewer",
              "verified_at": quote["verified_at"], "valid_until": quote["valid_until"],
              "input_tokens_upper": 1000, "output_tokens_upper": 0, "max_payload_bytes": 10000}
    price_path, policy_path = tmp_path / "prices.json", tmp_path / "policies.json"
    price_path.write_text(json.dumps({"BAAI/bge-m3": quote}), encoding="utf-8")
    policy_path.write_text(json.dumps({"BAAI/bge-m3": policy}), encoding="utf-8")
    env = {"KNOWFLOW_BUDGET_LEDGER_PATH": str(tmp_path / "ledger.sqlite3"),
           "KNOWFLOW_BUDGET_PRICE_FILE": str(price_path),
           "KNOWFLOW_BUDGET_POLICY_FILE": str(policy_path)}

    reserve_provider_call_sync("siliconflow", "BAAI/bge-m3",
                               {"model": "BAAI/bge-m3", "input": ["synthetic"]}, environ=env)

    assert BudgetLedger(env["KNOWFLOW_BUDGET_LEDGER_PATH"]).summary()["paid_reservations"] == 1


@pytest.mark.parametrize("table,quote,allow_zero", [
    ("reservations", {"provider": "synthetic", "model": "model-a",
                      "input_cny_per_million": "1", "output_cny_per_million": "1",
                      "source_url": "https://example.test/prices"}, False),
    ("zero_price_reservations", {"provider": "siliconflow", "model": "BAAI/bge-m3",
                                  "input_cny_per_million": "0", "output_cny_per_million": "0",
                                  "source_url": "https://siliconflow.cn/pricing"}, True),
])
@pytest.mark.parametrize("trigger", ["ignore_before", "delete_after", "mutate_after"])
def test_ledger_rejects_missing_reservation_after_trigger(tmp_path, table, quote, allow_zero, trigger):
    import sqlite3
    from knowflow_ai.budget import BudgetLedger

    now = datetime.now(timezone.utc)
    quote.update({"verified_by": "test-reviewer",
                  "verified_at": (now - timedelta(minutes=1)).isoformat(),
                  "valid_until": (now + timedelta(hours=1)).isoformat()})
    ledger = BudgetLedger(tmp_path / "budget.sqlite3")
    with sqlite3.connect(ledger.path) as db:
        if trigger == "ignore_before":
            sql = f"CREATE TRIGGER ignore_insert BEFORE INSERT ON {table} BEGIN SELECT RAISE(IGNORE); END"
        elif trigger == "mutate_after" and table == "reservations":
            sql = ("CREATE TRIGGER mutate_after_insert AFTER INSERT ON reservations "
                   "BEGIN UPDATE reservations SET microyuan = microyuan + 1 "
                   "WHERE request_id = NEW.request_id; END")
        elif trigger == "mutate_after":
            sql = ("CREATE TRIGGER mutate_after_insert AFTER INSERT ON zero_price_reservations "
                   "BEGIN UPDATE zero_price_reservations SET input_tokens_upper = input_tokens_upper + 1 "
                   "WHERE request_id = NEW.request_id; END")
        else:
            sql = (f"CREATE TRIGGER delete_after_insert AFTER INSERT ON {table} "
                   "BEGIN DELETE FROM " + table + " WHERE request_id = NEW.request_id; END")
        db.execute(sql)

    with pytest.raises(ValueError, match="BUDGET_RESERVATION_FAILED"):
        ledger.reserve("provider:ignored", provider=quote["provider"], model=quote["model"],
                       input_tokens_upper=1000, output_tokens_upper=0, quote=quote,
                       allow_zero_price_embedding=allow_zero)

    assert ledger.summary()["reserved_microyuan"] == 0


def test_ledger_rejects_explicitly_unsigned_price(tmp_path):
    from knowflow_ai.budget import BudgetLedger

    now = datetime.now(timezone.utc)
    quote = {"provider": "synthetic", "model": "model-a", "input_cny_per_million": "1",
             "output_cny_per_million": "1", "source_url": "https://example.test/prices",
             "verified_by": "draft-not-owner-signed",
             "verified_at": (now - timedelta(minutes=1)).isoformat(),
             "valid_until": (now + timedelta(hours=1)).isoformat()}
    ledger = BudgetLedger(tmp_path / "budget.sqlite3")

    with pytest.raises(ValueError, match="UNVERIFIED_PRICE"):
        ledger.reserve("draft-price", provider="synthetic", model="model-a",
                       input_tokens_upper=1000, output_tokens_upper=0, quote=quote)

    assert ledger.summary()["reserved_microyuan"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["embed", "generate", "stream"])
async def test_guarded_real_adapters_reserve_once_per_failed_http_attempt(monkeypatch, operation):
    root = Path(__file__).resolve().parents[3]
    wiring_spec = importlib.util.spec_from_file_location(
        "provider_budget_wiring", root / "evaluation/collector/wiring.py")
    wiring = importlib.util.module_from_spec(wiring_spec)
    wiring_spec.loader.exec_module(wiring)
    ledger_path = Path(os.environ["KNOWFLOW_BUDGET_LEDGER_PATH"])
    ledger_path.unlink(missing_ok=True)
    calls = []
    async def transport(request):
        calls.append(request)
        return httpx.Response(503)

    now = datetime.now(timezone.utc)
    model = "BAAI/bge-m3" if operation == "embed" else "deepseek-flash"
    provider = "siliconflow" if operation == "embed" else "deepseek"
    quote = json.loads(Path(os.environ["KNOWFLOW_BUDGET_PRICE_FILE"]).read_text())[model]
    def bounds(requested_operation, *_):
        return (10_000, 0 if requested_operation == "embed" else 1024)
    bounds.policy_id = "synthetic-test-policy"
    evidence = {"provider": provider, "model": model, "policy_id": bounds.policy_id,
                "source_url": "https://example.test/policy", "verified_by": "synthetic-test",
                "verified_at": (now - timedelta(hours=1)).isoformat(),
                "valid_until": (now + timedelta(hours=1)).isoformat()}
    ledger = wiring.BudgetLedger(ledger_path)
    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        if operation == "embed":
            adapter = SiliconFlowEmbeddingAdapter(EmbeddingSettings(api_key="fake-key-" * 8), client)
            arguments = {"texts": ["synthetic"], "request_id": "same-request"}
            invoke = lambda guard: guard.embed(**arguments)
        else:
            adapter = DeepSeekAdapter(LlmSettings(api_key="fake-key-" * 8), client)
            arguments = {"question": "synthetic", "evidence": [], "request_id": "same-request"}
            invoke = (lambda guard: guard.generate(**arguments)) if operation == "generate" else (
                lambda guard: guard.stream_content(**arguments))
        config = {"adapter_factory": lambda: adapter, "provider": provider,
                  "model": model, "quote": quote, "token_bounds": bounds, "bound_evidence": evidence}
        factories = wiring.EvaluationFactories(ledger=ledger, embedding=config, llm=config)
        # Both are valid configurations; preflight does not construct either provider.
        factories.preflight()
        guard = factories.embedding_factory() if operation == "embed" else factories.llm_factory()
        for _ in range(2):
            if operation == "stream":
                with pytest.raises(ProcessingError):
                    async for _fragment in invoke(guard):
                        pass
            else:
                with pytest.raises(ProcessingError):
                    await invoke(guard)
    summary = ledger.summary()
    assert len(calls) == 2
    assert summary["paid_reservations"] == 2
