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
