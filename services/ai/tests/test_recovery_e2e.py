import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest
from knowflow_ai.adapters import ProcessingError
from knowflow_ai.parsing import parse_document
from knowflow_ai.protocol import ContractConsumer
from knowflow_ai.worker import IndexWorker


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


@pytest.mark.asyncio
async def test_second_embedding_failure_after_persisted_first_batch(monkeypatch, tmp_path):
    from test_worker import FakeGateway, _dispatch
    import knowflow_ai.worker as worker_module

    source = recovery.LONG_DOCUMENT_TEXT.encode("utf-8")
    dispatch = _dispatch(source)
    dispatch["runtime_profile"].update(embedding_max_batch_items=16, index_max_batch_chunks=8)
    lease = dispatch["lease"]
    parsed = parse_document(source, format="txt", document_id=lease["document_id"],
                            content_version_id=lease["content_version_id"],
                            file_id=dispatch["source"]["file_id"])

    async def parsed_source(*_args, **_kwargs):
        return parsed

    monkeypatch.setattr(worker_module, "parse_document_isolated", parsed_source)
    gateway = FakeGateway(ContractConsumer(recovery.REPO / "contracts/schemas/protocol.schema.json"), source)
    marker = tmp_path / "fault.json"
    embedding = recovery.SecondBatchFailureEmbedding(marker=marker)
    worker = IndexWorker(gateway)

    with pytest.raises(ProcessingError, match="MODEL_FAILURE") as exc:
        await worker._index(dispatch, embedding)

    assert not exc.value.retryable
    assert json.loads(marker.read_text(encoding="utf-8")) == {
        "successful_batches": 1, "failed_batch": 2}
    assert len(gateway.batches) >= 1
    assert gateway.completions == []


def test_failed_candidate_wait_requires_physical_cleanup(monkeypatch):
    pending = {"status": "FAILED", "cleaned": False, "document_status": "ACTIVE",
               "active_index_version_id": "original", "chunk_rows": 8, "embedding_rows": 8}
    cleaned = {**pending, "cleaned": True, "chunk_rows": 0, "embedding_rows": 0}
    states = iter([pending, {**cleaned, "embedding_rows": 1}, cleaned])
    calls = []
    monkeypatch.setattr(recovery, "_failed_candidate_state",
                        lambda db, candidate: calls.append((db, candidate)) or next(states))
    monkeypatch.setattr(recovery.time, "sleep", lambda _seconds: None)

    assert recovery._wait_failed_candidate_cleanup("isolated-db", "failed", "original") == cleaned
    assert calls == [("isolated-db", "failed")] * 3


def test_failed_candidate_wait_fails_if_active_index_changes(monkeypatch):
    state = {"status": "FAILED", "cleaned": True, "document_status": "ACTIVE",
             "active_index_version_id": "wrong", "chunk_rows": 0, "embedding_rows": 0}
    monkeypatch.setattr(recovery, "_failed_candidate_state", lambda *_args: state)
    with pytest.raises(RuntimeError, match="FAILED_EMBEDDING_REPLACED_ACTIVE_INDEX"):
        recovery._wait_failed_candidate_cleanup("isolated-db", "failed", "original")


def test_failed_candidate_wait_fails_if_physical_rows_remain(monkeypatch):
    state = {"status": "FAILED", "cleaned": True, "document_status": "ACTIVE",
             "active_index_version_id": "original", "chunk_rows": 1, "embedding_rows": 0}
    monkeypatch.setattr(recovery, "_failed_candidate_state", lambda *_args: state)
    ticks = iter([0, 0, 2])
    monkeypatch.setattr(recovery.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(recovery.time, "sleep", lambda _seconds: None)
    with pytest.raises(RuntimeError, match="FAILED_CANDIDATE_NOT_PHYSICALLY_CLEANED"):
        recovery._wait_failed_candidate_cleanup("isolated-db", "failed", "original", timeout=1)


def test_service_outage_rejects_shared_compose_before_touching_services(monkeypatch):
    monkeypatch.setattr(recovery, "_ISOLATED_COMPOSE", None)
    calls = []
    monkeypatch.setattr(recovery, "_run_compose", lambda *args: calls.append(args))
    with pytest.raises(RuntimeError, match="OUTAGE_REQUIRES_OWN_ISOLATED_COMPOSE"):
        recovery._scenario_service_outage(object(), "postgres")
    assert calls == []


def test_run_outage_mode_cannot_start_shared_compose(monkeypatch):
    monkeypatch.setattr(recovery, "_ISOLATED_COMPOSE", None)
    with pytest.raises(RuntimeError, match="OUTAGE_REQUIRES_OWN_ISOLATED_COMPOSE"):
        recovery.run(type("Args", (), {"isolated_outages": True})())


def test_stopped_isolated_service_is_restored_even_if_fault_setup_fails(monkeypatch, tmp_path):
    from types import SimpleNamespace

    class Client:
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def get(self, *_args, **_kwargs): return SimpleNamespace(status_code=200)

    harness = SimpleNamespace(args=SimpleNamespace(env_file=tmp_path / ".env"),
                              start_python=lambda **_kwargs: None,
                              create_knowledge_base=lambda _label: "kb",
                              upload_document=lambda *_args: ("doc", "task"),
                              database_url="db", token="token", client=lambda **_kwargs: Client())
    monkeypatch.setattr(recovery, "_ISOLATED_COMPOSE", ("knowflow-outage-0123456789abcd", tmp_path / "override.yml"))
    monkeypatch.setattr(recovery, "_wait_task", lambda *_args: {})
    monkeypatch.setattr(recovery, "_document_row", lambda *_args: {
        "active_index_version_id": "original", "content_version_id": "version"})
    commands = []
    monkeypatch.setattr(recovery, "_run_compose", lambda _path, args: commands.append(args)
                        or subprocess.CompletedProcess(args, 1 if args[0] == "ps" else 0, "", ""))
    restored = []
    monkeypatch.setattr(recovery, "_restore_isolated_service", lambda path, service: restored.append((path, service)))
    with pytest.raises(RuntimeError, match="ISOLATED_SERVICE_NOT_STOPPED"):
        recovery._scenario_service_outage(harness, "postgres")
    assert commands == [["stop", "postgres"], ["ps", "--all", "--format", "json"]]
    assert restored == [(harness.args.env_file, "postgres")]


def test_isolated_compose_targets_owned_project_and_override(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(recovery, "_ISOLATED_COMPOSE", ("knowflow-outage-0123456789abcd", tmp_path / "override.yml"))
    monkeypatch.setattr(recovery.subprocess, "run", lambda command, **kwargs: calls.append(command)
                        or subprocess.CompletedProcess(command, 0, "", ""))
    recovery._run_compose(tmp_path / ".env", ["stop", "minio"])
    assert calls[0][:4] == ["docker", "compose", "--project-name", "knowflow-outage-0123456789abcd"]
    assert str(tmp_path / "override.yml") in calls[0]
    assert calls[0][-2:] == ["stop", "minio"]


def test_isolated_project_collision_is_rejected(monkeypatch):
    monkeypatch.setattr(recovery.subprocess, "run", lambda command, **kwargs:
                        subprocess.CompletedProcess(command, 0, "existing-container\n", ""))
    with pytest.raises(RuntimeError, match="ISOLATED_PROJECT_NOT_EMPTY"):
        recovery._assert_isolation_available("knowflow-outage-0123456789abcd")


def test_isolated_outage_failure_cleans_only_owned_compose(monkeypatch, tmp_path):
    from types import SimpleNamespace

    monkeypatch.setattr(recovery, "_ISOLATED_COMPOSE", None)
    monkeypatch.setattr(recovery.local, "can_bind", lambda _port: True)
    monkeypatch.setattr(recovery, "_assert_isolation_available", lambda _project: None)
    calls = []

    def fail_run(args):
        project, override = recovery._ISOLATED_COMPOSE
        assert project.startswith("knowflow-outage-")
        contents = override.read_text(encoding="utf-8")
        assert f"name: {project}-postgres" in contents
        assert f"name: {project}-minio" in contents
        assert args.env_file.is_file()
        raise RuntimeError("SIMULATED_FAILURE")

    def cleanup(env_path, args):
        calls.append((recovery._ISOLATED_COMPOSE[0], args, env_path.is_file()))
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(recovery, "run", fail_run)
    monkeypatch.setattr(recovery, "_run_compose", cleanup)
    args = SimpleNamespace(isolated_outages=True, output=tmp_path / "report.json")
    with pytest.raises(RuntimeError, match="SIMULATED_FAILURE"):
        recovery.run_isolated_outages(args)
    assert len(calls) == 1 and calls[0][0].startswith("knowflow-outage-")
    assert calls[0][1:] == (["down", "--volumes", "--remove-orphans"], True)
    assert recovery._ISOLATED_COMPOSE is None
