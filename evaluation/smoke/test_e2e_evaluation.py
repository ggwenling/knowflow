import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/e2e-evaluation.py"
spec = importlib.util.spec_from_file_location("evaluation_e2e", SCRIPT)
e2e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e2e)


def test_fake_smoke_rejects_execution_error_rows():
    payload = {"predictions": [{"outcome": "error", "answer": "", "citations": [],
                                "retrieved_evidence": []}]}
    scorer = {"sample_count": 1, "metrics": {"execution_error_count": 1}}
    with pytest.raises(RuntimeError, match="EVALUATION_EXECUTION_ERRORS"):
        e2e.assert_fake_evaluation_success(payload, scorer, 1)


def test_fake_smoke_checks_expected_answer_and_citation():
    row = {"outcome": "answered", "answer": "Synthetic answer [source-1]",
           "citations": [{"source_id": "source-1"}],
           "retrieved_evidence": [{"source_id": "source-1"}]}
    e2e.assert_fake_evaluation_success(
        {"predictions": [row]}, {"sample_count": 1, "metrics": {"execution_error_count": 0}}, 1)
    row["citations"] = []
    with pytest.raises(RuntimeError, match="DETERMINISTIC_FAKE_ANSWER_MISMATCH"):
        e2e.assert_fake_evaluation_success(
            {"predictions": [row]}, {"sample_count": 1, "metrics": {"execution_error_count": 0}}, 1)
