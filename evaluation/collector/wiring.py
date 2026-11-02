"""Evaluation factory wiring prototype; production startup stays disabled.

The current product create_app() constructs its own factories in module-level
closures and has no per-application injection interface. Monkeypatching those
globals is unsafe in a process that could host another app. This module does not
patch the product and does not start a service or make provider calls.
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
                              input_tokens_upper=1, output_tokens_upper=output_bound, quote=config["quote"])

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


def create_evaluation_app(*_args, **_kwargs):
    """Fail closed until per-app factory injection and safe budget wiring exist."""
    raise RuntimeError("EVALUATION_SERVICE_NOT_READY")


if __name__ == "__main__":
    create_evaluation_app()
