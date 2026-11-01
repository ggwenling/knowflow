import importlib.util
import json
from pathlib import Path
import subprocess
import sys


SCRIPT = Path(__file__).resolve().parents[1] / "tools/recovery_e2e.py"
sys.path.insert(0, str(SCRIPT.parent))
spec = importlib.util.spec_from_file_location("recovery_e2e", SCRIPT)
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


def _compose_result(args, services):
    return subprocess.CompletedProcess(
        args, 0, "\n".join(json.dumps(service) for service in services), "")


def test_ensure_compose_starts_only_the_stopped_service(monkeypatch, tmp_path):
    calls = []
    initial = [
        {"Service": "postgres", "State": "running", "Health": "healthy"},
        {"Service": "minio", "State": "exited", "Health": ""},
    ]
    healthy = [
        {"Service": "postgres", "State": "running", "Health": "healthy"},
        {"Service": "minio", "State": "running", "Health": "healthy"},
    ]

    def run_compose(_env_path, args):
        calls.append(args)
        if args[0] == "up":
            return subprocess.CompletedProcess(args, 0, "", "")
        return _compose_result(args, initial if len(calls) == 1 else healthy)

    monkeypatch.setattr(recovery, "_run_compose", run_compose)

    started = recovery._ensure_compose(tmp_path / ".env")

    assert started == {"minio"}
    assert calls == [
        ["ps", "--all", "--format", "json"],
        ["up", "-d", "minio"],
        ["ps", "--format", "json"],
    ]


def test_ensure_compose_does_not_claim_already_running_services(monkeypatch, tmp_path):
    calls = []
    healthy = [
        {"Service": "postgres", "State": "running", "Health": "healthy"},
        {"Service": "minio", "State": "running", "Health": "healthy"},
    ]

    def run_compose(_env_path, args):
        calls.append(args)
        return _compose_result(args, healthy)

    monkeypatch.setattr(recovery, "_run_compose", run_compose)

    started = recovery._ensure_compose(tmp_path / ".env")

    assert started == set()
    assert calls == [["ps", "--all", "--format", "json"],
                     ["ps", "--format", "json"]]


def test_cleanup_stops_only_services_started_by_this_run(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        recovery, "_run_compose",
        lambda _env_path, args: calls.append(args)
        or subprocess.CompletedProcess(args, 0, "", ""))

    recovery._stop_compose_services(tmp_path / ".env", {"minio"})
    recovery._stop_compose_services(tmp_path / ".env", set())

    assert calls == [["stop", "minio"]]
