"""Local evaluation service with deterministic providers and blocked external HTTP."""
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

import httpx
from knowflow_ai.config import Settings


def load(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeEmbedding:
    settings = SimpleNamespace(model="BAAI/bge-m3")
    async def embed(self, texts, *, request_id):
        return {"request_id": request_id, "model": self.settings.model, "dimensions": 1024,
                "data": [{"index": index, "embedding": [.125] * 1024} for index in range(len(texts))]}
    async def aclose(self):
        pass


class FakeLlm:
    settings = SimpleNamespace(model="deepseek-flash")
    last_usage = None
    async def generate(self, question, evidence, *, request_id):
        source = evidence[0]["source_id"]
        return {"answer": "Synthetic answer [" + source + "]", "has_answer": True, "source_ids": [source]}
    async def aclose(self):
        pass


def create_fake_app():
    wiring = load(Path(__file__).with_name("wiring.py"))
    now = datetime.now(timezone.utc)
    times = {"verified_at": (now - timedelta(hours=1)).isoformat(),
             "valid_until": (now + timedelta(hours=1)).isoformat()}
    def bounds(operation, *inputs):
        return (10000, 0 if operation == "embed" else 1024)
    bounds.policy_id = "fake-provider-v1"
    def config(factory):
        model = factory.settings.model
        return {"adapter_factory": factory, "provider": "synthetic", "model": model,
                "token_bounds": bounds,
                "quote": {"provider": "synthetic", "model": model,
                          "input_cny_per_million": "1", "output_cny_per_million": "2",
                          "source_url": "https://example.invalid/prices", "verified_by": "fake-test", **times},
                "bound_evidence": {"provider": "synthetic", "model": model, "policy_id": bounds.policy_id,
                                   "source_url": "https://example.invalid/bounds", "verified_by": "fake-test", **times}}
    return wiring.create_evaluation_app(
        Settings.from_environment(), ledger=wiring.BudgetLedger(os.environ["KNOWFLOW_BUDGET_LEDGER_PATH"]),
        embedding=config(FakeEmbedding), llm=config(FakeLlm),
        control_secret=os.environ["KNOWFLOW_EVALUATION_CONTROL_SECRET"])


def main():
    import uvicorn
    original = httpx.AsyncHTTPTransport.handle_async_request
    async def loopback_only(self, request):
        if request.url.host not in ("127.0.0.1", "localhost", "::1"):
            raise RuntimeError("EXTERNAL_NETWORK_DISABLED_IN_FAKE_SERVICE")
        return await original(self, request)
    httpx.AsyncHTTPTransport.handle_async_request = loopback_only
    uvicorn.run(create_fake_app(), host="127.0.0.1",
                port=int(os.environ.get("KNOWFLOW_EVALUATION_AI_PORT", "8000")),
                log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
