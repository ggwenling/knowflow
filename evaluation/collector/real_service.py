"""Real evaluation service: product app + single-use capture, no guarded double reservation.

The product adapters already reserve through ``knowflow_ai.provider_budget`` before each
outbound request. Wrapping them in ``GuardedEmbedding``/``GuardedLlm`` would reserve the same
attempt twice in the shared ledger, so this service injects the real adapters directly and
uses only ``CapturingRetriever``/``RecordingAnswerService`` for evaluation capture.
"""
import asyncio
import hmac
import importlib.util
import os
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn
from fastapi import HTTPException, Request
from knowflow_ai.answering import AnswerService, LlmSettings, ReadOnlyRetriever
from knowflow_ai.app import create_app
from knowflow_ai.budget import BudgetLedger
from knowflow_ai.config import Settings
from knowflow_ai.embedding import EmbeddingSettings
from knowflow_ai.worker import IndexWorker


def _local(name):
    spec = importlib.util.spec_from_file_location(
        "knowflow_eval_" + name, Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_capture = _local("capture")
_results = _local("results")
CaptureStore, CapturingRetriever = _capture.CaptureStore, _capture.CapturingRetriever
RecordingAnswerService = _results.RecordingAnswerService


class RealFactories:
    """Build the product worker and answer service while recording evaluation traces."""

    def __init__(self):
        self.traces = CaptureStore()
        self.results = {}

    def index_worker(self, gateway):
        return IndexWorker(gateway)

    def answer_service(self, database_url, contract, *, embedding_settings, model_profile=None):
        retriever = ReadOnlyRetriever(database_url, embedding_settings=embedding_settings)
        service = AnswerService(database_url, contract,
                                retriever=CapturingRetriever(retriever, self.traces),
                                model_profile=model_profile)
        return RecordingAnswerService(service, self)


def create_real_app(settings=None, *, factories=None, control_secret=None):
    """Create the product app plus the local single-use capture endpoint."""
    settings = settings or Settings.from_environment()
    control_secret = control_secret or os.environ.get("KNOWFLOW_EVALUATION_CONTROL_SECRET", "")
    if not isinstance(control_secret, str) or len(control_secret) < 32:
        raise RuntimeError("EVALUATION_SERVICE_NOT_READY: control_secret")
    factories = factories or RealFactories()
    app = create_app(settings, worker_factory=factories.index_worker,
                     answer_service_factory=factories.answer_service)
    app.state.evaluation_factories = factories

    @app.post("/internal/evaluation/results/{request_id}")
    async def take_result(request: Request, request_id: str):
        if (request.client is None or request.client.host not in ("127.0.0.1", "::1")
                or not hmac.compare_digest(request.headers.get("X-Evaluation-Secret", "").encode("utf-8"),
                                           control_secret.encode("utf-8"))):
            raise HTTPException(status_code=403, detail="EVALUATION_ACCESS_DENIED")
        result = factories.results.pop(request_id, None)
        if result is None:
            raise HTTPException(status_code=404, detail="EVALUATION_RESULT_NOT_AVAILABLE")
        return result

    return app


async def _probe_provider_budget(embedding_model, llm_model):
    from knowflow_ai.provider_budget import reserve_provider_call
    await reserve_provider_call(
        "siliconflow", embedding_model,
        {"model": embedding_model, "input": ["x"], "encoding_format": "float"})
    await reserve_provider_call(
        "deepseek", llm_model,
        {"model": llm_model, "messages": [{"role": "system", "content": "x"}],
         "max_tokens": 1024})


def preflight():
    """Validate keys, ledger, price and policy through production code without HTTP."""
    settings = Settings.from_environment()
    if not settings.ai_database_url:
        raise RuntimeError("REAL_EVALUATION_PREFLIGHT_FAILED")
    embedding = EmbeddingSettings.from_environment()
    llm = LlmSettings.from_environment()
    ledger_path = os.environ["KNOWFLOW_BUDGET_LEDGER_PATH"]
    BudgetLedger(ledger_path)
    original = ledger_path
    with TemporaryDirectory(prefix="knowflow-real-eval-preflight-") as temp:
        os.environ["KNOWFLOW_BUDGET_LEDGER_PATH"] = str(Path(temp) / "probe.sqlite3")
        try:
            asyncio.run(_probe_provider_budget(embedding.model, llm.model))
        finally:
            os.environ["KNOWFLOW_BUDGET_LEDGER_PATH"] = original


def main():
    try:
        preflight()
    except Exception:
        print("REAL_EVALUATION_PREFLIGHT_FAILED")
        return 1
    uvicorn.run(create_real_app(), host="127.0.0.1", port=8000,
                log_level="warning", access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
