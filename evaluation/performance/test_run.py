import importlib.util
from pathlib import Path

import httpx

spec = importlib.util.spec_from_file_location("perf_runner", Path(__file__).with_name("run.py"))
perf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(perf)


def test_percentiles_preserve_small_sample_counts():
    assert perf.summarize([]) == {"sample_count": 0, "p50_ms": None, "p95_ms": None}
    assert perf.summarize([4, 2, 3, 1]) == {"sample_count": 4, "p50_ms": 2, "p95_ms": 4}


def test_retrieval_logs_use_only_requested_ids_and_retrieval_stage():
    logs = ("ai_stage request_id=a stage=retrieval duration_ms=12 result_count=5 outcome=success\n"
            "ai_stage request_id=b stage=retrieval duration_ms=99 result_count=5 outcome=success\n"
            "ai_stage request_id=a stage=embedding duration_ms=31 outcome=success")
    assert perf.retrieval_timings(logs, {"a"}) == {"a": 12}


def test_missing_latency_evidence_cannot_report_complete():
    load = {"failed": 0, "succeeded": 1, "first_delta": {"sample_count": 1},
            "retrieval": {"sample_count": 0}}
    cases = [{"loads": [load]}]
    assert perf.measurement_status(cases) == "incomplete"
    load["retrieval"]["sample_count"] = 1
    assert perf.measurement_status(cases) == "completed"
    load["failed"] = 1
    assert perf.measurement_status(cases) == "completed_with_errors"


def test_question_records_terminal_status_without_answer_or_credentials(monkeypatch):
    def handler(request):
        assert request.headers["authorization"] == "Bearer private-token"
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
                              text='event: delta\ndata: {"request_id":"server-1","text":"private answer"}\n\nevent: completed\ndata: {"request_id":"server-1"}\n\n')
    real_client = httpx.Client
    monkeypatch.setattr(perf.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    result = perf.question("http://localhost", {"Authorization": "Bearer private-token"}, "kb")
    assert result["outcome"] == "success" and result["first_delta_ms"] is not None
    assert result["retrieval_request_id"] == "server-1"
    assert "private" not in str(result)


def test_question_keeps_transport_failures_out_of_success_metrics(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("private-error")
    real_client = httpx.Client
    monkeypatch.setattr(perf.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    result = perf.question("http://localhost", {}, "kb")
    assert result["outcome"] == "transport_error"
    assert "private" not in str(result)


def test_resource_summary_reports_sampled_maxima():
    rows = [("api", 10.0, 100), ("api", 5.0, 200), ("ai", 1.0, 50)]
    assert perf.summarize_resources(rows) == {
        "ai": {"samples": 1, "peak_cpu_percent": 1.0, "peak_memory_bytes": 50},
        "api": {"samples": 2, "peak_cpu_percent": 10.0, "peak_memory_bytes": 200},
    }
