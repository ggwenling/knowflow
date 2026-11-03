"""Evaluation factory wiring prototype; production startup stays disabled.

The product create_app() supports per-application worker and answer factories.
This module does not start a service or make provider calls. Real evaluation
startup remains disabled until a trustworthy token-bound policy and process-wide
budget enforcement have been independently verified.
"""
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
from knowflow_ai.worker import IndexWorker


class EvaluationFactories:
    """Construct the worker and answer factories for synthetic verification.

    Both guarded factories use the very same ledger. Supplying arbitrary
    factories or estimates is not evidence of a trustworthy token upper bound;
    real service startup remains disabled until the whole path is audited.
    """
    def __init__(self, *, ledger, embedding, llm):
        if not isinstance(ledger, BudgetLedger) or not isinstance(embedding, dict) or not isinstance(llm, dict):
            raise ValueError("EVALUATION_CONFIGURATION_REQUIRED")
        self._ledger = ledger
        self._embedding = dict(embedding)
        self._llm = dict(llm)
        self.traces = CaptureStore()

    def preflight(self):
        """Check both configurations without constructing a provider or spending.

        Policy evidence does not prove that a token-bound implementation is
        correct; the actual startup path remains unconditionally disabled.
        """
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
        return AnswerService(database_url, contract, retriever=CapturingRetriever(retriever, self.traces),
                             llm_factory=self.llm_factory, model_profile=model_profile)

    async def prediction_from_response(self, *, request_id, question_id, mappings,
                                       response, latency_ms):
        return await _prediction.bind_response(
            trace_store=self.traces, request_id=request_id, question_id=question_id,
            mappings=mappings, response=response, latency_ms=latency_ms)

    async def prediction_from_error(self, *, request_id, question_id, mappings,
                                    error_code, latency_ms):
        return await _prediction.bind_error(
            trace_store=self.traces, request_id=request_id, question_id=question_id,
            mappings=mappings, error_code=error_code, latency_ms=latency_ms)


def create_evaluation_app(*_args, **_kwargs):
    """Fail closed until trusted token bounds and full budget enforcement are verified."""
    raise RuntimeError("EVALUATION_SERVICE_NOT_READY")


if __name__ == "__main__":
    create_evaluation_app()
