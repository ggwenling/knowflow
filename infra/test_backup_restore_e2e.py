import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location("backup_restore_e2e", Path(__file__).with_name("backup_restore_e2e.py"))
drill = importlib.util.module_from_spec(spec)
spec.loader.exec_module(drill)


def test_rejects_shared_or_invalid_project_before_docker(monkeypatch):
    calls = []
    monkeypatch.setattr(drill, "docker", lambda args: calls.append(args))
    for name in ("knowflow-local", "knowflow-restore-../../existing", "knowflow-restore-not-hex"):
        with pytest.raises(ValueError, match="INVALID_PROJECT"):
            drill.ensure_empty(name)
    assert calls == []


def test_rejects_existing_project_resources(monkeypatch):
    calls = []
    def fake_docker(args):
        calls.append(args)
        return SimpleNamespace(stdout=b"existing-container\n")
    monkeypatch.setattr(drill, "docker", fake_docker)
    with pytest.raises(RuntimeError, match="PROJECT_NOT_EMPTY"):
        drill.ensure_empty("knowflow-restore-" + "a" * 16)
    assert calls[0][:2] == ["ps", "-aq"]


def test_database_restore_replaces_preexisting_bootstrap_objects(monkeypatch):
    calls = []
    def fake_docker(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stderr=b'')
    monkeypatch.setattr(drill, "docker", fake_docker)
    drill.restore_database("isolated-db", b"archive")
    command, options = calls[0]
    assert command[:3] == ["exec", "-i", "isolated-db"]
    assert "--clean" in command and "--if-exists" in command
    assert "--no-owner" not in command
    assert options["data"] == b"archive"


def test_schema_owner_check_rejects_restored_schemas_owned_by_postgres(monkeypatch):
    monkeypatch.setattr(drill, "docker", lambda _args: SimpleNamespace(
        stdout=b"knowflow=postgres\nknowflow_flyway=knowflow_migrator\n"))
    with pytest.raises(RuntimeError, match="RESTORED_SCHEMA_OWNER_MISMATCH"):
        drill.verify_schema_owners("isolated-db")


def test_dirty_build_inputs_prevent_snapshot_run(monkeypatch):
    calls = []
    def fake_run(args, **_kwargs):
        calls.append(args)
        return SimpleNamespace(stdout=" M services/ai/src/knowflow_ai/app.py\n")
    monkeypatch.setattr(drill.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="DIRTY_BUILD_INPUTS"):
        drill.run(Path("unused.json"))
    assert calls[0][:3] == ["git", "status", "--porcelain"]
