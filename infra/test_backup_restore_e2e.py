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


def test_cleanup_requires_down_success_and_empty_labeled_resources(monkeypatch, tmp_path):
    calls = []
    def fake_docker(args, **kwargs):
        calls.append((args, kwargs))
        if args[0] == "compose":
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
    monkeypatch.setattr(drill, "docker", fake_docker)
    result = drill.cleanup_project("knowflow-restore-" + "a" * 16, tmp_path / ".env", tmp_path / "override.yml")
    assert result == {"down_exit_code": 0, "remaining_resources": {"containers": 0, "networks": 0, "volumes": 0},
                      "verified_empty": True}
    assert len(calls) == 4


def test_cleanup_fails_when_compose_down_leaves_resources(monkeypatch, tmp_path):
    def fake_docker(args, **kwargs):
        if args[0] == "compose":
            return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
        return SimpleNamespace(returncode=0,
                               stdout=b"leftover\n" if args[0] == "volume" else b"", stderr=b"")
    monkeypatch.setattr(drill, "docker", fake_docker)
    result = drill.cleanup_project("knowflow-restore-" + "a" * 16, tmp_path / ".env", tmp_path / "override.yml")
    assert result["remaining_resources"]["volumes"] == 1
    assert result["verified_empty"] is False


def test_restore_evidence_records_migration_version_and_image_id(monkeypatch):
    commands = []
    def fake_docker(args, **_kwargs):
        commands.append(args)
        output = b"8\n" if "flyway_schema_history" in args[-1] else b"sha256:" + b"a" * 64 + b"\n"
        return SimpleNamespace(stdout=output)
    monkeypatch.setattr(drill, "docker", fake_docker)
    assert drill.migration_version("isolated-db") == "8"
    assert drill.image_id("isolated-api") == "sha256:" + "a" * 64
    assert "flyway_schema_history" in commands[0][-1]
    assert commands[1][:3] == ["inspect", "--format", "{{.Image}}"]


def test_history_source_signature_uses_public_snake_case_fields():
    source = {key: key for key in ("source_id", "document_id", "content_version_id",
                                   "index_version_id", "chunk_id", "state",
                                   "locator", "quote")}
    assert drill.history_source_signature({"sources": [source]}) == [source]
