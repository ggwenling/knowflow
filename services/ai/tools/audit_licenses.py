"""Capture lock-bound local license evidence; never infer legal approval or fetch packages."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as md
import json
from pathlib import Path
import platform
import re
import tomllib

ROOT = Path(__file__).resolve().parents[1]
EXPORT_PACKAGES = {"psycopg", "psycopg-binary", "tzdata", "reportlab", "colorama", "uv-build"}


def normalized_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def capture_package(package: dict, *, distribution=None, export_dir: Path | None = None) -> dict:
    name, version = package["name"], package["version"]
    row = {"name": name, "version": version, "installed": False,
           "source": package.get("source", {}), "license_files": [],
           "review_status": "未完成"}
    try:
        dist = distribution if distribution is not None else md.distribution(name)
    except md.PackageNotFoundError:
        row["unknown_reason"] = "Not installed on this platform; license not inspected."
        return row
    row["observed_version"] = dist.version
    if dist.version != version:
        row["unknown_reason"] = "Installed version differs from lock; metadata is not evidence for this version."
        return row
    row.update(installed=True, license_expression=dist.metadata.get("License-Expression"),
               license_metadata=dist.metadata.get("License"),
               license_classifiers=[value for value in dist.metadata.get_all("Classifier", [])
                                    if value.startswith("License ::")])
    for file in dist.files or []:
        path = Path(dist.locate_file(file))
        if str(file).replace("\\", "/").endswith(".dist-info/METADATA") and path.is_file():
            row["metadata_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        if not any(part.lower() == "licenses"
                   or part.lower().startswith(("license", "copying", "notice")) for part in file.parts):
            continue
        if not path.is_file():
            continue
        content = path.read_bytes()
        evidence = {"path": str(file).replace("\\", "/"),
                    "sha256": hashlib.sha256(content).hexdigest()}
        if export_dir is not None and normalized_name(name) in EXPORT_PACKAGES:
            # Use a generated filename, never an untrusted package path, as the output location.
            destination = export_dir.resolve() / f"{normalized_name(name)}-{version}" / f"{len(row['license_files']) + 1:02d}-{path.name}"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            evidence["evidence_path"] = destination.relative_to(ROOT.parents[1]).as_posix()
        row["license_files"].append(evidence)
    if row["license_files"]:
        row["review_status"] = "证据已采集，待独立审阅"
    else:
        row["unknown_reason"] = "No license text found in this distribution; owner/upstream confirmation required."
    return row


def dependency_scopes(packages: list[dict], project: dict) -> dict[str, list[str]]:
    by_name = {normalized_name(package["name"]): package for package in packages}
    result: dict[str, list[str]] = {}
    for scope, requirements in (("runtime_candidate", project["project"]["dependencies"]),
                                ("development_candidate", project.get("dependency-groups", {}).get("dev", []))):
        pending = [normalized_name(re.split(r"[<>=!~;\[ ]", requirement, 1)[0])
                   for requirement in requirements if isinstance(requirement, str)]
        seen = set()
        while pending:
            name = pending.pop()
            if name in seen:
                continue
            seen.add(name)
            result.setdefault(name, []).append(scope)
            package = by_name.get(name, {})
            pending.extend(normalized_name(dep["name"]) for dep in package.get("dependencies", []))
            for deps in package.get("optional-dependencies", {}).values():
                pending.extend(normalized_name(dep["name"]) for dep in deps)
    return result


def collect_report(root: Path, *, build_metadata: Path | None = None,
                   export_dir: Path | None = None, base_sha: str | None = None) -> dict:
    lock = root / "uv.lock"
    lock_bytes = lock.read_bytes()
    packages = tomllib.loads(lock_bytes.decode("utf-8"))["package"]
    project_path = root / "pyproject.toml"
    project = tomllib.loads(project_path.read_text(encoding="utf-8"))
    scopes = dependency_scopes(packages, project)
    rows = []
    for package in packages:
        row = capture_package(package, export_dir=export_dir)
        row["scopes"] = scopes.get(normalized_name(package["name"]), ["first_party_or_unclassified"])
        rows.append(row)
    build_rows = []
    for requirement in project["build-system"]["requires"]:
        name, separator, version = requirement.partition("==")
        if not separator:
            build_rows.append({"requirement": requirement, "review_status": "未完成",
                               "unknown_reason": "Build requirement is not exactly pinned."})
            continue
        dist = md.Distribution.at(build_metadata) if build_metadata is not None else None
        if dist is not None and normalized_name(dist.metadata.get("Name", "")) != normalized_name(name):
            raise ValueError("Build metadata name does not match the declared build requirement")
        row = capture_package({"name": name, "version": version}, distribution=dist, export_dir=export_dir)
        row["scopes"] = ["isolated_build"]
        row["metadata_source"] = "explicit_local_dist_info" if build_metadata is not None else "current_environment"
        if build_metadata is not None:
            row["matching_cached_metadata"] = row["installed"]
            row["installed"] = False  # A cached build distribution is not an active runtime installation.
        build_rows.append(row)
    return {
        "schema_version": 2,
        "scope": "Local installed metadata for every lock entry plus isolated build requirements; not legal approval. Platform markers are not evaluated for scope classification. Installed metadata does not prove wheel/sdist byte identity or Linux image contents.",
        "base_sha": base_sha,
        "environment": {"system": platform.system(), "python": platform.python_version()},
        "hash_normalization": "lock_sha256 and pyproject_sha256 hash LF-normalized bytes (CRLF -> LF); worktree hashes retain original bytes. Compare canonical values with Git blobs and Linux checkouts.",
        "lock_sha256": hashlib.sha256(lock_bytes.replace(b"\r\n", b"\n")).hexdigest(),
        "lock_worktree_sha256": hashlib.sha256(lock_bytes).hexdigest(),
        "pyproject_sha256": hashlib.sha256(project_path.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
        "pyproject_worktree_sha256": hashlib.sha256(project_path.read_bytes()).hexdigest(),
        "build_backend": project["build-system"]["build-backend"],
        "packages": rows,
        "build_dependencies": build_rows,
        "summary": {"lock_entries": len(packages), "evidence_rows": len(rows),
                    "matching_installed_metadata": sum(row["installed"] for row in rows),
                    "packages_with_license_text": sum(bool(row["license_files"]) for row in rows),
                    "incomplete": [row["name"] for row in rows + build_rows if row["review_status"] == "未完成"]},
        "approval": "待独立审阅；项目自身授权、发行义务及非 Python 发行工件仍未完成。",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/evidence/dependency-licenses.json")
    parser.add_argument("--build-metadata", type=Path, help="Exact-version local build-backend .dist-info directory")
    parser.add_argument("--export-dir", type=Path, help="Preserve the missing-license audit targets' actual upstream license texts")
    parser.add_argument("--base-sha", help="Implementation baseline; the future commit containing this evidence is not self-referenced")
    args = parser.parse_args()
    report = collect_report(ROOT, build_metadata=args.build_metadata,
                            export_dir=args.export_dir, base_sha=args.base_sha)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=True))


if __name__ == "__main__":
    main()
