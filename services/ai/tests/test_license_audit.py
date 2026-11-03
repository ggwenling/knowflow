"""Regression checks for lock completeness and conservative license provenance."""
import email.message
import hashlib
import importlib.metadata as md
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "knowflow_license_audit", Path(__file__).resolve().parents[1] / "tools/audit_licenses.py"
)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class FakeDistribution:
    def __init__(self, root, version="1.0"):
        self.root = root
        self.version = version
        self.metadata = email.message.Message()
        self.metadata["Name"] = "example"
        self.metadata["Version"] = version
        self.metadata["License-Expression"] = "MIT"
        self.files = [md.PackagePath("example-1.0.dist-info/licenses/LICENSE"),
                      md.PackagePath("example-1.0.dist-info/METADATA")]
        for file in self.files:
            target = root / file
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("test-only license text" if file.name == "LICENSE" else "Name: example\n", encoding="utf-8")

    def locate_file(self, file):
        return self.root / file


def test_wrong_installed_version_is_not_license_evidence(tmp_path):
    dist = FakeDistribution(tmp_path, "2.0")
    row = audit.capture_package({"name": "example", "version": "1.0"}, distribution=dist)
    assert not row["installed"]
    assert row["observed_version"] == "2.0"
    assert row["license_files"] == []
    assert row["review_status"] == "未完成"


def test_matching_metadata_hashes_actual_license_bytes_without_approval(tmp_path):
    dist = FakeDistribution(tmp_path)
    row = audit.capture_package({"name": "example", "version": "1.0"}, distribution=dist)
    assert row["installed"]
    assert row["license_expression"] == "MIT"
    assert row["license_files"][0]["sha256"] == hashlib.sha256(b"test-only license text").hexdigest()
    assert "待独立审阅" in row["review_status"]


def test_missing_platform_package_stays_in_report(tmp_path, monkeypatch):
    lock_text = ('[[package]]\nname = "example"\nversion = "1.0"\n'
                 '[[package]]\nname = "platform-only"\nversion = "3.0"\n')
    (tmp_path / "uv.lock").write_bytes(lock_text.replace("\n", "\r\n").encode("utf-8"))
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["example==1.0"]\n'
        '[build-system]\nrequires = ["missing-builder==1.0"]\nbuild-backend = "missing_builder"\n',
        encoding="utf-8"
    )
    dist = FakeDistribution(tmp_path / "installed")

    def distribution(name):
        if name == "example":
            return dist
        raise md.PackageNotFoundError(name)

    monkeypatch.setattr(audit.md, "distribution", distribution)
    report = audit.collect_report(tmp_path)
    assert [(row["name"], row["version"]) for row in report["packages"]] == [
        ("example", "1.0"), ("platform-only", "3.0")
    ]
    assert report["summary"]["lock_entries"] == report["summary"]["evidence_rows"] == 2
    assert report["summary"]["incomplete"] == ["platform-only", "missing-builder"]
    assert report["lock_sha256"] == hashlib.sha256(lock_text.encode("utf-8")).hexdigest()
    assert report["lock_worktree_sha256"] == hashlib.sha256((tmp_path / "uv.lock").read_bytes()).hexdigest()
    assert report["lock_sha256"] != report["lock_worktree_sha256"]


@pytest.mark.parametrize("matching", [False, True])
def test_build_metadata_requires_exact_identity_and_is_not_runtime_installed(tmp_path, monkeypatch, matching):
    (tmp_path / "uv.lock").write_text("package = []\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = []\n[build-system]\n'
        'requires = ["expected-builder==1.0"]\nbuild-backend = "expected_builder"\n', encoding="utf-8"
    )
    wrong = FakeDistribution(tmp_path / "wrong")
    if matching:
        wrong.metadata.replace_header("Name", "expected-builder")
    monkeypatch.setattr(audit.md.Distribution, "at", lambda path: wrong)
    if matching:
        report = audit.collect_report(tmp_path, build_metadata=tmp_path / "wrong")
        build = report["build_dependencies"][0]
        assert build["matching_cached_metadata"]
        assert not build["installed"]
        assert build["scopes"] == ["isolated_build"]
        assert "待独立审阅" in build["review_status"]
    else:
        with pytest.raises(ValueError, match="name does not match"):
            audit.collect_report(tmp_path, build_metadata=tmp_path / "wrong")
