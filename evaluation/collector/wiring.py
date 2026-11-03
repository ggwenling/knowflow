"""Explicitly configured evaluation service with shared guarded factories."""
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory


def _local(name):
    spec = importlib.util.spec_from_file_location("knowflow_eval_" + name, Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_capture = _local("capture")
CaptureStore, CapturingRetriever = _capture.CaptureStore, _capture.CapturingRetriever
_guards = _local("guarded_adapters")
GuardedEmbedding, GuardedLlm = _guards.GuardedEmbedding, _guards.GuardedLlm
_prediction = _local("prediction")
BudgetLedger = _local("budget").BudgetLedger
from knowflow_ai.answering import AnswerService, ReadOnlyRetriever
from knowflow_ai.config import Settings
from knowflow_ai.worker import IndexWorker


class EvaluationFactories:
    """Construct worker and answer factories using one ledger and trace store."""
    def __init__(self, *, ledger, embedding, llm):
        if not isinstance(ledger, BudgetLedger) or not isinstance(embedding, dict) or not isinstance(llm, dict):
            raise ValueError("EVALUATION_CONFIGURATION_REQUIRED")
        self._ledger = ledger
        self._embedding = dict(embedding)
        self._llm = dict(llm)
        self.traces = CaptureStore()
        self.results = {}
        self.record_results = False

    def preflight(self):
        """Validate prices and bound declarations without creating a provider."""
        with TemporaryDirectory(prefix="knowflow-eval-preflight-") as temp:
            probe = BudgetLedger(Path(temp) / "probe.sqlite3")
            for name, cls, config, output_bound in (
                    ("embedding", GuardedEmbedding, self._embedding, 0),
                    ("llm", GuardedLlm, self._llm, 1024)):
                guard = cls(ledger=probe, **config)
                guard._verify_bound_evidence()
                probe.reserve("preflight:" + name, provider=config["provider"], model=config["model"],
                              input_tokens_upper=1, output_tokens_upper=output_bound, quote=config["quote"],
                              allow_zero_price_embedding=(
                                  name == "embedding" and isinstance(config["quote"], dict)
                                  and config["quote"].get("input_cny_per_million") == "0"))

    def embedding_factory(self):
        return GuardedEmbedding(ledger=self._ledger, **self._embedding)

    def llm_factory(self):
        return GuardedLlm(ledger=self._ledger, **self._llm)

    def index_worker(self, gateway):
        return IndexWorker(gateway, embedding_factory=self.embedding_factory)

    def answer_service(self, database_url, contract, *, embedding_settings, model_profile=None):
        retriever = ReadOnlyRetriever(database_url, embedding_factory=self.embedding_factory,
                                      embedding_settings=embedding_settings)
        service = AnswerService(database_url, contract, retriever=CapturingRetriever(retriever, self.traces),
                                llm_factory=self.llm_factory, model_profile=model_profile)
        if self.record_results:
            return _local("results").RecordingAnswerService(service, self)
        return service

    async def prediction_from_response(self, *, request_id, question_id,
                                       runtime_question_id, mappings, response, latency_ms):
        return await _prediction.bind_response(
            trace_store=self.traces, request_id=request_id, question_id=question_id,
            runtime_question_id=runtime_question_id, mappings=mappings,
            response=response, latency_ms=latency_ms)

    async def prediction_from_error(self, *, request_id, question_id,
                                    runtime_question_id, mappings, error_code, latency_ms):
        return await _prediction.bind_error(
            trace_store=self.traces, request_id=request_id, question_id=question_id,
            runtime_question_id=runtime_question_id, mappings=mappings,
            error_code=error_code, latency_ms=latency_ms)


def create_evaluation_app(settings=None, *, ledger=None, embedding=None, llm=None,
                          control_secret=None, **unknown):
    """Create an evaluation app only when every guarded dependency is supplied."""
    missing = []
    if not isinstance(settings, Settings):
        missing.append("settings")
    elif not settings.ai_database_url:
        missing.append("ai_database_url")
    if not isinstance(ledger, BudgetLedger):
        missing.append("ledger")
    if not isinstance(embedding, dict):
        missing.append("embedding")
    if not isinstance(llm, dict):
        missing.append("llm")
    if not isinstance(control_secret, str) or len(control_secret) < 32:
        missing.append("control_secret")
    if unknown:
        missing.append("unsupported configuration")
    if missing:
        raise RuntimeError("EVALUATION_SERVICE_NOT_READY: " + ", ".join(missing))
    factories = EvaluationFactories(ledger=ledger, embedding=embedding, llm=llm)
    factories.record_results = True
    try:
        factories.preflight()
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError("EVALUATION_SERVICE_NOT_READY: invalid guard configuration") from error
    from knowflow_ai.app import create_app
    app = create_app(settings, worker_factory=factories.index_worker,
                     answer_service_factory=factories.answer_service)
    app.state.evaluation_factories = factories
    import hmac
    from fastapi import HTTPException, Request

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


if __name__ == "__main__":
    create_evaluation_app()
