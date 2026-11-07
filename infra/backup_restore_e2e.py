"""Isolated synthetic backup/restore drill. Never operates on an existing project."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import platform
import secrets
import socket
import subprocess
import tempfile
import time
import uuid

import httpx

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "infra/compose.yml"
BODY = b"Synthetic restore evidence. Only READY documents may be queried.\n"
_DOCKER_COMMANDS = []
_DOCKER_ERRORS = []
_DOCKER_SECRETS = set()
BUILD_INPUTS = ("infra/compose.yml", "services/api", "services/ai/Dockerfile",
                "services/ai/pyproject.toml", "services/ai/uv.lock", "services/ai/src",
                "services/ai/tools/local_backend_e2e.py", "services/ai/tools/browser_e2e_server.py",
                "contracts/schemas")


def source_revision():
    status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all", "--", *BUILD_INPUTS],
                            cwd=ROOT, capture_output=True, text=True, check=True).stdout
    if status.strip():
        raise RuntimeError("DIRTY_BUILD_INPUTS")
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                          text=True, check=True).stdout.strip()


def docker(args, *, data=None, check=True, timeout=600):
    command = ["docker", *map(str, args)]
    _DOCKER_COMMANDS.append(command)
    result = subprocess.run(command, cwd=ROOT, input=data, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, check=False, timeout=timeout)
    if result.returncode:
        error = result.stderr.decode("utf-8", errors="replace")
        for secret in _DOCKER_SECRETS:
            error = error.replace(secret, "[REDACTED]")
        _DOCKER_ERRORS.append({"command": command, "exit_code": result.returncode,
                               "stderr": error[-4000:]})
        if check:
            raise subprocess.CalledProcessError(result.returncode, command, result.stdout, result.stderr)
    return result


def project():
    return "knowflow-restore-" + uuid.uuid4().hex[:16]


def ensure_empty(name):
    if len(name) != 33 or not name.startswith("knowflow-restore-") or any(c not in "0123456789abcdef" for c in name[17:]):
        raise ValueError("INVALID_PROJECT")
    if any(project_resource_counts(name).values()):
        raise RuntimeError("PROJECT_NOT_EMPTY")


def project_resource_counts(name):
    counts = {}
    for resource in ("ps", "network", "volume"):
        args = {"ps": ["ps", "-aq"], "network": ["network", "ls", "-q"], "volume": ["volume", "ls", "-q"]}[resource]
        rows = docker([*args, "--filter", f"label=com.docker.compose.project={name}"]).stdout.decode().splitlines()
        counts[{"ps": "containers", "network": "networks", "volume": "volumes"}[resource]] = len([row for row in rows if row.strip()])
    return counts


def cleanup_project(name, env, override):
    result = docker(["compose", "--project-name", name, "-f", str(COMPOSE), "-f", str(override),
                     "--env-file", str(env), "down", "--volumes", "--remove-orphans"], check=False)
    try:
        remaining = project_resource_counts(name)
    except (OSError, subprocess.SubprocessError, UnicodeDecodeError):
        return {"down_exit_code": result.returncode, "remaining_resources": None, "verified_empty": False}
    return {"down_exit_code": result.returncode, "remaining_resources": remaining,
            "verified_empty": result.returncode == 0 and not any(remaining.values())}


def port():
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        return server.getsockname()[1]


def credentials(path):
    names = ("POSTGRES_PASSWORD", "MIGRATOR_PASSWORD", "APP_PASSWORD", "AI_PASSWORD", "MINIO_ROOT_PASSWORD")
    values = {"KNOWFLOW_DEV_" + n: secrets.token_hex(32) for n in names}
    values.update({"KNOWFLOW_DEV_MINIO_ROOT_USER": "restoretest", "KNOWFLOW_INTERNAL_SHARED_SECRET": secrets.token_hex(32),
                   "KNOWFLOW_E2E_DUMMY_EMBEDDING_KEY": secrets.token_hex(32), "KNOWFLOW_E2E_DUMMY_LLM_KEY": secrets.token_hex(32)})
    _DOCKER_SECRETS.update(values.values())
    path.write_text("\n".join(f"{k}={v}" for k, v in values.items()) + "\n", encoding="utf-8")


def compose(name, env, override, args, **kwargs):
    return docker(["compose", "--project-name", name, "-f", str(COMPOSE), "-f", str(override), "--env-file", str(env), *args], **kwargs)


def container(name, env, override, service):
    value = compose(name, env, override, ["ps", "--all", "-q", service]).stdout.decode().strip()
    if not value or "\n" in value:
        raise RuntimeError("CONTAINER_NOT_UNIQUE")
    return value


def restore_database(container_id, dump):
    result = docker(["exec", "-i", container_id, "pg_restore", "-U", "postgres",
                     "--exit-on-error", "--clean", "--if-exists", "-d", "knowflow"],
                    data=dump, check=False)
    if result.returncode:
        if b"already exists" in result.stderr:
            raise RuntimeError("RESTORE_DATABASE_OBJECT_ALREADY_EXISTS")
        raise RuntimeError("RESTORE_DATABASE_FAILED")


def verify_schema_owners(container_id):
    sql = ("SELECT nspname || '=' || pg_get_userbyid(nspowner) FROM pg_namespace "
           "WHERE nspname IN ('knowflow', 'knowflow_flyway') ORDER BY nspname")
    result = docker(["exec", container_id, "psql", "-U", "postgres", "-d", "knowflow",
                     "-At", "-c", sql]).stdout.decode("utf-8").splitlines()
    check(result == ["knowflow=knowflow_migrator", "knowflow_flyway=knowflow_migrator"],
          "RESTORED_SCHEMA_OWNER_MISMATCH")


def migration_version(container_id):
    sql = ("SELECT version FROM knowflow_flyway.flyway_schema_history "
           "WHERE success ORDER BY installed_rank DESC LIMIT 1")
    result = docker(["exec", container_id, "psql", "-U", "postgres", "-d", "knowflow",
                     "-At", "-c", sql]).stdout.decode("utf-8").strip()
    if not result:
        raise RuntimeError("MIGRATION_VERSION_MISSING")
    return result


def image_id(container_id):
    result = docker(["inspect", "--format", "{{.Image}}", container_id]).stdout.decode("utf-8").strip()
    if not result.startswith("sha256:"):
        raise RuntimeError("IMAGE_ID_MISSING")
    return result


def owner(client):
    response = client.post("/api/v1/auth/register", json={"contract_version": "0.2.0",
                           "email": f"restore-{uuid.uuid4().hex}@example.test", "password": "Restore-" + secrets.token_hex(16)})
    response.raise_for_status()
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def check(condition, code):
    if not condition:
        raise RuntimeError(code)


def question_history(client, headers, knowledge_base_id, question):
    response = client.get("/api/v1/questions", headers=headers, params={"limit": 100, "offset": 0})
    response.raise_for_status()
    matches = [item for item in response.json().get("items", [])
               if item.get("knowledge_base_id") == knowledge_base_id and item.get("question") == question]
    check(len(matches) == 1, "QUESTION_HISTORY_MISSING_OR_DUPLICATED")
    question_id = matches[0].get("question_id")
    detail = client.get(f"/api/v1/questions/{question_id}", headers=headers)
    detail.raise_for_status()
    return detail.json()


def history_source_signature(detail):
    return [{key: source.get(key) for key in
             ("source_id", "document_id", "content_version_id", "index_version_id", "chunk_id",
              "state", "locator", "quote")}
            for source in detail.get("sources", [])]


def run(output):
    _DOCKER_COMMANDS.clear()
    _DOCKER_ERRORS.clear()
    _DOCKER_SECRETS.clear()
    revision = source_revision()
    names = [project(), project()]
    check(names[0] != names[1], "PROJECT_COLLISION")
    for name in names:
        ensure_empty(name)
    ports = [port(), port()]
    check(ports[0] != ports[1], "PORT_COLLISION")
    report = {"status": "incomplete", "started_at": datetime.now(timezone.utc).isoformat(),
              "projects": names, "checks": {}, "provider_calls": 0,
              "source_revision": revision, "drill_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
              "command": f"uv run --project services/ai --frozen python infra/backup_restore_e2e.py --output {output.as_posix()}",
              "machine": {"os": platform.system(), "release": platform.release(),
                          "architecture": platform.machine(),
                          "docker_server": docker(["version", "--format", "{{.Server.Version}}"]).stdout.decode().strip(),
                          "compose": docker(["compose", "version", "--short"]).stdout.decode().strip()},
              "images": {}, "migration_versions": {}}
    started = []
    with tempfile.TemporaryDirectory(prefix="knowflow-restore-") as tmp:
        directory = Path(tmp)
        env = directory / ".env"
        credentials(env)
        overrides = []
        for i in range(2):
            override = directory / f"override-{i}.yml"
            override.write_text(f'services:\n  api:\n    ports:\n      - "127.0.0.1:{ports[i]}:8080"\n    networks: [knowflow, web-edge]\n', encoding="utf-8")
            overrides.append(override)
        try:
            started.append(0)
            report["stage"] = "start_source_stack"
            compose(names[0], env, overrides[0], ["up", "--build", "--quiet-build", "--wait", "--wait-timeout", "240", "api"])
            report["stage"] = "prepare_source_data"
            with httpx.Client(base_url=f"http://127.0.0.1:{ports[0]}", timeout=40, trust_env=False) as client:
                user = owner(client)
                other = owner(client)
                response = client.post("/api/v1/knowledge-bases", headers=user, json={"contract_version": "0.2.0", "name": "Restore evidence"})
                response.raise_for_status(); base = response.json()["id"]
                response = client.post(f"/api/v1/knowledge-bases/{base}/documents", headers=user,
                                       files={"file": ("restore.txt", BODY, "text/plain")})
                response.raise_for_status(); doc, task = response.json()["document_id"], response.json()["task_id"]
                deadline = time.monotonic() + 120
                while time.monotonic() < deadline:
                    state = client.get(f"/api/v1/tasks/{task}", headers=user); state.raise_for_status()
                    if state.json()["status"] == "SUCCEEDED": break
                    if state.json()["status"] in ("FAILED", "CANCELLED"): raise RuntimeError("INDEX_FAILED")
                    time.sleep(.4)
                else: raise RuntimeError("INDEX_TIMEOUT")
                question = client.post(f"/api/v1/knowledge-bases/{base}/questions", headers=user, json={"question": "When can documents be queried?"})
                question.raise_for_status(); answer = question.json(); check(bool(answer.get("sources")), "SOURCE_MISSING")
                source = answer["sources"][0]; content = source["content_version_id"]; sid = source["source_id"]
                history = question_history(client, user, base, "When can documents be queried?")
                check(history.get("status") == "SUCCEEDED" and history.get("has_answer") is True
                      and history.get("sources"), "QUESTION_HISTORY_INCOMPLETE")
                check(any(item.get("source_id") == sid and item.get("document_id") == doc
                          and item.get("content_version_id") == content for item in history["sources"]),
                      "QUESTION_HISTORY_SOURCE_MISMATCH")
                check(all(item.get("state") == "AVAILABLE" for item in history["sources"]),
                      "QUESTION_HISTORY_SOURCE_UNAVAILABLE")
                check(client.get(f"/api/v1/questions/{history['question_id']}", headers=other).status_code == 404,
                      "QUESTION_HISTORY_OWNER_ISOLATION_FAILED")
                file_path = f"/api/v1/documents/{doc}/contents/{content}/file"
                original = client.get(file_path, headers=user); original.raise_for_status()
                check(original.content == BODY, "ORIGINAL_MISMATCH")
                check(client.get(file_path, headers=other).status_code == 404,
                      "DOCUMENT_OWNER_ISOLATION_FAILED")
                check(client.get(f"/api/v1/sources/{sid}", headers=other).status_code == 404, "OWNER_ISOLATION_FAILED")
            # Stop all writers before taking database and object snapshots.
            report["stage"] = "backup_source"
            compose(names[0], env, overrides[0], ["stop", "api", "ai", "minio"])
            src_db = container(names[0], env, overrides[0], "postgres")
            src_store = container(names[0], env, overrides[0], "minio")
            report["images"]["source_api"] = image_id(container(names[0], env, overrides[0], "api"))
            report["images"]["source_ai"] = image_id(container(names[0], env, overrides[0], "ai"))
            report["migration_versions"]["source"] = migration_version(src_db)
            dump = docker(["exec", src_db, "pg_dump", "-U", "postgres", "--format=custom", "--no-owner", "knowflow"]).stdout
            archive = docker(["cp", "-a", f"{src_store}:/bitnami/minio/data/.", "-"]).stdout
            check(bool(dump) and bool(archive), "BACKUP_EMPTY")
            report["backup_sha256"] = {"database": sha256(dump).hexdigest(), "objects": sha256(archive).hexdigest()}
            report["stage"] = "start_restore_dependencies"
            started.append(1)
            compose(names[1], env, overrides[1], ["up", "--wait", "--wait-timeout", "120", "postgres", "minio"])
            compose(names[1], env, overrides[1], ["stop", "minio"])
            dst_db = container(names[1], env, overrides[1], "postgres")
            dst_store = container(names[1], env, overrides[1], "minio")
            report["stage"] = "restore_database"
            restore_database(dst_db, dump)
            verify_schema_owners(dst_db)
            report["migration_versions"]["restored"] = migration_version(dst_db)
            check(report["migration_versions"]["source"] == report["migration_versions"]["restored"],
                  "MIGRATION_VERSION_MISMATCH")
            report["stage"] = "restore_objects"
            docker(["cp", "-a", "-", f"{dst_store}:/bitnami/minio/data"], data=archive)
            report["stage"] = "start_restored_api"
            compose(names[1], env, overrides[1], ["up", "--build", "--quiet-build", "--wait", "--wait-timeout", "240", "api"])
            report["images"]["restored_api"] = image_id(container(names[1], env, overrides[1], "api"))
            report["images"]["restored_ai"] = image_id(container(names[1], env, overrides[1], "ai"))
            with httpx.Client(base_url=f"http://127.0.0.1:{ports[1]}", timeout=40, trust_env=False) as client:
                restored = client.get(file_path, headers=user); restored.raise_for_status()
                check(restored.content == BODY, "RESTORED_BYTES_MISMATCH")
                restored_source = client.get(f"/api/v1/sources/{sid}", headers=user); restored_source.raise_for_status()
                check(restored_source.json()["content_version_id"] == content, "SOURCE_VERSION_MISMATCH")
                check(client.get(f"/api/v1/sources/{sid}", headers=other).status_code == 404, "RESTORED_ISOLATION_FAILED")
                restored_history = client.get(f"/api/v1/questions/{history['question_id']}", headers=user)
                restored_history.raise_for_status()
                restored_detail = restored_history.json()
                check(restored_detail.get("status") == history["status"]
                      and restored_detail.get("question") == history["question"]
                      and restored_detail.get("answer") == history["answer"]
                      and restored_detail.get("has_answer") == history["has_answer"],
                      "RESTORED_QUESTION_HISTORY_MISMATCH")
                check(len(restored_detail.get("sources", [])) == len(history["sources"])
                      and all(item.get("state") == "AVAILABLE" for item in restored_detail["sources"])
                      and history_source_signature(restored_detail) == history_source_signature(history),
                      "RESTORED_QUESTION_HISTORY_SOURCES_MISMATCH")
                check(client.get(f"/api/v1/questions/{history['question_id']}", headers=other).status_code == 404,
                      "RESTORED_QUESTION_HISTORY_OWNER_ISOLATION_FAILED")
                check(client.get(file_path, headers=other).status_code == 404,
                      "RESTORED_DOCUMENT_OWNER_ISOLATION_FAILED")
                again = client.post(f"/api/v1/knowledge-bases/{base}/questions", headers=user, json={"question": "When can documents be queried?"})
                again.raise_for_status(); check(any(s["document_id"] == doc and s["content_version_id"] == content for s in again.json().get("sources", [])), "RESTORED_INDEX_UNQUERYABLE")
            report["checks"] = {"source_index_ready": True, "schema_owners_match": True, "bytes_match": True,
                                "history_answer_restored": True, "history_source_accessible": True,
                                "owner_isolation": True, "restored_index_queryable": True}
            check(source_revision() == revision, "BUILD_INPUTS_CHANGED")
            report["status"] = "passed"
        except Exception as exc:
            report["failure"] = type(exc).__name__ + (":" + str(exc) if isinstance(exc, RuntimeError) else "")
        finally:
            cleanup = {}
            for i in reversed(started):
                try:
                    cleanup[names[i]] = cleanup_project(names[i], env, overrides[i])
                except (OSError, subprocess.SubprocessError):
                    cleanup[names[i]] = {"down_exit_code": None, "remaining_resources": None,
                                         "verified_empty": False}
            report["cleanup"] = cleanup
            report["cleanup_verified"] = all(item["verified_empty"] for item in cleanup.values())
            report["commands"] = _DOCKER_COMMANDS
            report["docker_errors"] = _DOCKER_ERRORS
            report["finished_at"] = datetime.now(timezone.utc).isoformat()
            if not report["cleanup_verified"]: report["status"] = "incomplete"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    if report["status"] != "passed": raise RuntimeError("RESTORE_DRILL_FAILED")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists(): parser.error("output already exists")
    print(json.dumps(run(args.output), ensure_ascii=False))
