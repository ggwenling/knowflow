import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from knowflow_ai.budget import BudgetLedger
from knowflow_ai.config import Settings

ROOT = Path(__file__).resolve().parents[3]


def load():
    spec = importlib.util.spec_from_file_location(
        "real_service_test", ROOT / "evaluation/collector/real_service.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Worker:
    async def start(self): pass
    async def close(self): pass


class _Factories:
    def __init__(self):
        self.traces = object()
        self.results = {"req-1": {"request_id": "req-1", "trace": [], "response": None,
                                  "error_code": None}}

    def index_worker(self, gateway): return _Worker()
    def answer_service(self, *_args, **_kwargs): raise AssertionError("not called")


def test_capture_endpoint_requires_loopback_secret_and_single_use():
    service = load()
    secret = "test-only-" + "a" * 40
    control = "control-" + "c" * 40
    app = service.create_real_app(
        Settings(secret, ai_database_url="postgresql://unused.invalid/db"),
        factories=_Factories(), control_secret=control)
    headers = {"Authorization": f"Bearer {secret}"}
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        assert client.post("/internal/evaluation/results/req-1", headers=headers).status_code == 403
        captured = client.post("/internal/evaluation/results/req-1",
                               headers={**headers, "X-Evaluation-Secret": control})
        assert captured.status_code == 200
        assert captured.json()["request_id"] == "req-1"
        assert client.post("/internal/evaluation/results/req-1",
                           headers={**headers, "X-Evaluation-Secret": control}).status_code == 404


def test_real_factories_use_capture_and_recording_without_guards(monkeypatch):
    service = load()

    class Retriever:
        pass

    class Answer:
        def __init__(self, database_url, contract, retriever=None, **_kwargs):
            self.retriever = retriever

    monkeypatch.setattr(service, "ReadOnlyRetriever", lambda *_a, **_k: Retriever())
    monkeypatch.setattr(service, "AnswerService", Answer)
    factories = service.RealFactories()
    wrapped = factories.answer_service(
        "postgresql://unused.invalid/db", object(), embedding_settings=SimpleNamespace())
    assert isinstance(wrapped, service.RecordingAnswerService)
    assert isinstance(wrapped._service.retriever, service.CapturingRetriever)


def test_preflight_uses_production_validators_and_leaves_real_ledger_empty(tmp_path, monkeypatch):
    service = load()
    now = datetime.now(timezone.utc)
    quote = {"provider": "siliconflow", "model": "BAAI/bge-m3",
             "input_cny_per_million": "0", "output_cny_per_million": "0",
             "source_url": "https://siliconflow.cn/pricing", "verified_by": "test",
             "verified_at": (now - timedelta(minutes=1)).isoformat(),
             "valid_until": (now + timedelta(hours=1)).isoformat()}
    llm_quote = {**quote, "provider": "deepseek", "model": "deepseek-flash",
                 "input_cny_per_million": "1", "output_cny_per_million": "2",
                 "source_url": "https://api-docs.deepseek.com/zh-cn/quick_start/pricing"}
    policy = {"provider": "siliconflow", "bound_kind": "provider_context_limit",
              "source_url": "https://docs.siliconflow.cn/docs/api/embeddings-post",
              "verified_by": "test", "verified_at": quote["verified_at"],
              "valid_until": quote["valid_until"], "input_tokens_upper": 32768,
              "output_tokens_upper": 0, "max_payload_bytes": 131072}
    llm_policy = {**policy, "provider": "deepseek",
                  "source_url": "https://api-docs.deepseek.com/zh-cn/quick_start/pricing",
                  "input_tokens_upper": 8192, "output_tokens_upper": 1024,
                  "max_payload_bytes": 65536}
    (tmp_path / "PRICE_FILE.json").write_text(
        json.dumps({"BAAI/bge-m3": quote, "deepseek-flash": llm_quote}), encoding="utf-8")
    (tmp_path / "POLICY_FILE.json").write_text(
        json.dumps({"BAAI/bge-m3": policy, "deepseek-flash": llm_policy}), encoding="utf-8")
    ledger = tmp_path / "budget.sqlite3"
    monkeypatch.setenv("KNOWFLOW_INTERNAL_SHARED_SECRET", "a" * 64)
    monkeypatch.setenv("KNOWFLOW_AI_DATABASE_URL", "postgresql://unused.invalid/db")
    monkeypatch.setenv("EMBEDING_KEY", "e" * 48)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "d" * 48)
    monkeypatch.setenv("KNOWFLOW_BUDGET_LEDGER_PATH", str(ledger))
    monkeypatch.setenv("KNOWFLOW_BUDGET_PRICE_FILE", str(tmp_path / "PRICE_FILE.json"))
    monkeypatch.setenv("KNOWFLOW_BUDGET_POLICY_FILE", str(tmp_path / "POLICY_FILE.json"))
    service.preflight()
    assert BudgetLedger(ledger).summary()["reserved_microyuan"] == 0
