import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import httpx
import pytest

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


@pytest.mark.parametrize("status", ["incomplete", "completed_with_errors"])
def test_cli_fails_for_nonpassing_measurements(monkeypatch, tmp_path, status):
    monkeypatch.setattr(sys, "argv", ["run.py", "--output", str(tmp_path / "report.json")])
    monkeypatch.setattr(perf, "run", lambda _args: {"status": status, "cases": [], "cleanup_exit_code": 0})
    with pytest.raises(SystemExit) as error:
        perf.main()
    assert error.value.code == 1


def test_question_records_terminal_status_without_answer_or_credentials(monkeypatch):
    def handler(request):
        assert request.headers["authorization"] == "Bearer private-token"
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
                              text='event: started\ndata: {"event":"started","sequence":1,"request_id":"server-1"}\n\n'
                                   'event: delta\ndata: {"event":"delta","sequence":2,"request_id":"server-1","delta":"private answer"}\n\n'
                                   'event: sources\ndata: {"event":"sources","sequence":3,"request_id":"server-1","has_answer":true,"sources":[]}\n\n'
                                   'event: completed\ndata: {"event":"completed","sequence":4,"request_id":"server-1"}\n\n')
    real_client = httpx.Client
    monkeypatch.setattr(perf.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    result = perf.question("http://localhost", {"Authorization": "Bearer private-token"}, "kb")
    assert result["outcome"] == "success" and result["first_delta_ms"] is not None
    assert result["retrieval_request_id"] == "server-1"
    assert "private" not in str(result)


def test_malformed_stream_is_not_counted_as_success(monkeypatch):
    def handler(request):
        return httpx.Response(200, text='event: delta\ndata: {"text":"not a delta"}\n\nevent: completed\ndata: {}\n\n')
    real_client = httpx.Client
    monkeypatch.setattr(perf.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    assert perf.question("http://localhost", {}, "kb")["outcome"] == "protocol_error"


def test_retryable_admission_error_is_recorded_without_message(monkeypatch):
    def handler(request):
        return httpx.Response(200, text='event: error\ndata: {"event":"error","sequence":1,"request_id":"s1","code":"AI_PROCESSING_FAILED","retryable":true,"message":"private"}\n\n')
    real_client = httpx.Client
    monkeypatch.setattr(perf.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    result = perf.question("http://localhost", {}, "kb")
    assert result["outcome"] == "stream_error"
    assert result["error_code"] == "AI_PROCESSING_FAILED" and result["retryable"] is True
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


def test_resource_coverage_requires_all_services():
    resources = {name: {"samples": 1} for name in ("api", "ai", "postgres", "minio")}
    assert perf.has_resource_coverage(resources)
    resources["ai"]["samples"] = 0
    assert not perf.has_resource_coverage(resources)


def test_compose_admission_limit_covers_requested_concurrency(tmp_path):
    _env, override = perf.compose_files(tmp_path, 8080, admission_limit=8)
    config = override.read_text(encoding="utf-8")
    assert config.count('KNOWFLOW_QUESTION_MAX_CONCURRENT: "8"') == 2
    assert config.index("  api:") < config.index("  ai:")


def test_cleanup_removes_only_the_projects_images_and_verifies_resources(monkeypatch):
    calls = []
    def fake_docker(args, **kwargs):
        calls.append((args, kwargs))
        if args[0:2] == ["image", "ls"]:
            return SimpleNamespace(returncode=0, stdout="other-project-api:latest\n")
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    monkeypatch.setattr(perf, "docker", fake_docker)

    result = perf.cleanup_project(["compose", "--project-name", "knowflow-perf-a"],
                                  "knowflow-perf-a")

    assert result == {"down_exit_code": 0, "image_remove_exit_code": 0,
                      "remaining_resources": {"containers": 0, "networks": 0,
                                               "volumes": 0, "temporary_image_tags": 0},
                      "verified_empty": True}
    image_remove = next(args for args, _kwargs in calls if args[0:2] == ["image", "rm"])
    assert image_remove[-3:] == ["knowflow-perf-a-api:latest", "knowflow-perf-a-ai:latest",
                                 "knowflow-perf-a-migrate:latest"]


def test_cleanup_rejects_a_leftover_temporary_image_tag(monkeypatch):
    def fake_docker(args, **kwargs):
        output = "knowflow-perf-a-api:latest\n" if args[0:2] == ["image", "ls"] else ""
        return SimpleNamespace(returncode=0, stdout=output, stderr="")
    monkeypatch.setattr(perf, "docker", fake_docker)

    result = perf.cleanup_project(["compose", "--project-name", "knowflow-perf-a"],
                                  "knowflow-perf-a")

    assert result["remaining_resources"]["temporary_image_tags"] == 1
    assert result["verified_empty"] is False
