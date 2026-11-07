"""Exercise worker and question recovery with real local services and synthetic models."""
import argparse
import asyncio
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid

import httpx
import psycopg
from psycopg import sql

import local_backend_e2e as local
from knowflow_ai.batch_digest import manifest_sha256
from knowflow_ai.protocol import CONTRACT_VERSION


AI_ROOT = Path(__file__).resolve().parents[1]
REPO = AI_ROOT.parents[1]
BLOCK_ANSWER_MARKER = "KNOWFLOW_RECOVERY_BLOCK_ANSWER"
DOCUMENT_TEXT = ("Recovery evidence confirms that Java owns publication. "
                 "Synthetic worker restart must preserve the active index.\n") * 36
LONG_DOCUMENT_TEXT = DOCUMENT_TEXT * 8
_ISOLATED_COMPOSE = None


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8", newline="\n")


class SecondBatchFailureEmbedding(local.SyntheticEmbedding):
    """Synthetic adapter that fails the second indexing embedding batch."""

    def __init__(self, *args, marker: Path, **kwargs):
        super().__init__(*args, **kwargs)
        self.marker = marker
        self.calls = 0

    async def embed(self, texts, *, request_id):
        from knowflow_ai.adapters import ProcessingError

        self.calls += 1
        if self.calls == 2:
            _write_json(self.marker, {"successful_batches": 1, "failed_batch": 2})
            raise ProcessingError("MODEL_FAILURE", 502, retryable=False)
        return await super().embed(texts, request_id=request_id)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_compose(env_path: Path, args: list[str]) -> subprocess.CompletedProcess:
    command = ["docker", "compose"]
    if _ISOLATED_COMPOSE is not None:
        project, override = _ISOLATED_COMPOSE
        command.extend(["--project-name", project])
    command.extend(["-f", str(REPO / "services/api/compose.dev.yml")])
    if _ISOLATED_COMPOSE is not None:
        command.extend(["-f", str(override)])
    return subprocess.run(
        [*command, "--env-file", str(env_path), *args],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=30)


def _stop_compose_services(env_path: Path, services: set[str]) -> None:
    if services:
        _run_compose(env_path, ["stop", *sorted(services)])


def _ensure_compose(env_path: Path) -> set[str]:
    try:
        result = _run_compose(env_path, ["ps", "--all", "--format", "json"])
    except (OSError, subprocess.SubprocessError):
        raise RuntimeError("LOCAL_POSTGRES_MINIO_NOT_HEALTHY") from None
    if result.returncode:
        raise RuntimeError("LOCAL_POSTGRES_MINIO_NOT_HEALTHY")
    containers = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    by_service = {item.get("Service"): item for item in containers}
    started_services = {
        name for name in ("postgres", "minio")
        if by_service.get(name, {}).get("State") != "running"
    }
    try:
        if started_services:
            started = _run_compose(
                env_path, ["up", "-d", *sorted(started_services)])
            if started.returncode:
                raise RuntimeError("LOCAL_POSTGRES_MINIO_NOT_HEALTHY")
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            result = _run_compose(env_path, ["ps", "--format", "json"])
            if result.returncode == 0:
                containers = [json.loads(line) for line in result.stdout.splitlines()
                              if line.strip()]
                health = {item.get("Service"): item.get("Health") for item in containers}
                if all(health.get(name) == "healthy" for name in ("postgres", "minio")):
                    return started_services
            time.sleep(1)
        raise RuntimeError("LOCAL_POSTGRES_MINIO_NOT_HEALTHY")
    except (OSError, subprocess.SubprocessError, RuntimeError):
        _stop_compose_services(env_path, started_services)
        raise


def _create_database(dotenv: dict[str, str], database_name: str) -> None:
    admin_password = dotenv.get("KNOWFLOW_DEV_POSTGRES_PASSWORD")
    migrator_password = dotenv.get("KNOWFLOW_DEV_MIGRATOR_PASSWORD")
    if not admin_password or not migrator_password:
        raise RuntimeError("LOCAL_DATABASE_ADMIN_CREDENTIALS_MISSING")
    with psycopg.connect(host="127.0.0.1", port=55432, dbname="postgres",
                         user="postgres", password=admin_password, autocommit=True) as admin:
        exists = admin.execute("SELECT 1 FROM pg_database WHERE datname = %s",
                               (database_name,)).fetchone()
        if exists:
            raise RuntimeError("ISOLATED_DATABASE_NAME_COLLISION")
        admin.execute(sql.SQL("CREATE DATABASE {} OWNER knowflow_migrator")
                      .format(sql.Identifier(database_name)))


def _bootstrap_database(dotenv: dict[str, str], database_name: str) -> None:
    admin_password = dotenv["KNOWFLOW_DEV_POSTGRES_PASSWORD"]
    bootstrap = (REPO / "services/api/src/main/resources/db/bootstrap-roles.sql"
                 ).read_text(encoding="utf-8")
    with psycopg.connect(host="127.0.0.1", port=55432, dbname=database_name,
                         user="postgres", password=admin_password, autocommit=True) as db:
        db.execute(bootstrap)


def _drop_database(dotenv: dict[str, str], database_name: str) -> None:
    password = dotenv["KNOWFLOW_DEV_POSTGRES_PASSWORD"]
    with psycopg.connect(host="127.0.0.1", port=55432, dbname="postgres",
                         user="postgres", password=password, autocommit=True) as admin:
        admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)")
                      .format(sql.Identifier(database_name)))


def _database_name(prefix: str, run_id: str) -> str:
    name = local.require_database_name(f"{prefix}_{run_id[:12]}")
    if len(name) > 63:
        raise RuntimeError("ISOLATED_DATABASE_NAME_INVALID")
    return name


def _task_row(database_url: str, task_id: str) -> dict:
    with psycopg.connect(database_url, autocommit=True) as connection:
        row = connection.execute("""
            SELECT status, failure_code, attempt_count, fencing, index_version_id
              FROM knowflow.indexing_tasks WHERE id = %s
        """, (task_id,)).fetchone()
    if row is None:
        raise RuntimeError("INDEX_TASK_NOT_FOUND")
    return dict(zip(("status", "failure_code", "attempt_count", "fencing",
                     "index_version_id"), row, strict=True))


def _document_row(database_url: str, document_id: str) -> dict:
    with psycopg.connect(database_url, autocommit=True) as connection:
        row = connection.execute("""
            SELECT d.status, d.active_index_version_id, d.current_content_version_id,
                   (SELECT count(*) FROM knowflow.chunks c WHERE c.document_id = d.id),
                   (SELECT count(*) FROM knowflow.chunk_embeddings e
                      JOIN knowflow.chunks c ON c.id = e.chunk_id
                     WHERE c.document_id = d.id)
              FROM knowflow.documents d WHERE d.id = %s
        """, (document_id,)).fetchone()
    if row is None:
        raise RuntimeError("DOCUMENT_NOT_FOUND")
    return dict(zip(("status", "active_index_version_id", "content_version_id",
                     "chunk_rows", "embedding_rows"), row, strict=True))


def _wait_task(database_url: str, task_id: str, expected: set[str],
               timeout: float = 60) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        row = _task_row(database_url, task_id)
        if row["status"] in expected:
            return row
        time.sleep(0.15)
    raise RuntimeError("INDEX_TASK_STATE_TIMEOUT")


def _wait_marker(path: Path, process: subprocess.Popen | None, timeout: float = 60) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            return _read_json(path)
        if process is not None and process.poll() is not None:
            raise RuntimeError("PYTHON_PROCESS_EXITED_BEFORE_FAULT_GATE")
        time.sleep(0.05)
    raise RuntimeError("RECOVERY_FAULT_GATE_NOT_REACHED")


def _cleanup_state(database_url: str) -> dict:
    with psycopg.connect(database_url, autocommit=True) as connection:
        unfinished, queued = connection.execute("""
            SELECT
              (SELECT count(*) FROM knowflow.indexing_tasks
                WHERE status IN ('QUEUED', 'RUNNING')),
              (SELECT count(*) FROM knowflow.execution_cancellation_queue)
              + (SELECT count(*) FROM knowflow.storage_cleanup_queue)
              + (SELECT count(*) FROM knowflow.index_cleanup_queue)
        """).fetchone()
    return {"unfinished_tasks": unfinished, "cleanup_queue_rows": queued}


def _wait_cleanup(database_url: str, timeout: float = 60) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        counts = _cleanup_state(database_url)
        if counts == {"unfinished_tasks": 0, "cleanup_queue_rows": 0}:
            return counts
        time.sleep(0.2)
    raise RuntimeError("RECOVERY_CLEANUP_DID_NOT_DRAIN")


def _failed_candidate_state(database_url: str, index_version_id) -> dict:
    with psycopg.connect(database_url, autocommit=True) as connection:
        row = connection.execute("""
            SELECT iv.status, iv.cleaned_at IS NOT NULL, d.status,
                   d.active_index_version_id,
                   (SELECT count(*) FROM knowflow.chunks c WHERE c.index_version_id = iv.id),
                   (SELECT count(*) FROM knowflow.chunk_embeddings e WHERE e.index_version_id = iv.id)
              FROM knowflow.index_versions iv
              JOIN knowflow.documents d ON d.id = iv.document_id
             WHERE iv.id = %s
        """, (index_version_id,)).fetchone()
    if row is None:
        raise RuntimeError("FAILED_CANDIDATE_NOT_FOUND")
    return dict(zip(("status", "cleaned", "document_status", "active_index_version_id",
                     "chunk_rows", "embedding_rows"), row, strict=True))


def _wait_failed_candidate_cleanup(database_url: str, index_version_id, original_index,
                                   timeout: float = 60) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = _failed_candidate_state(database_url, index_version_id)
        if (state["document_status"] != "ACTIVE"
                or str(state["active_index_version_id"]) != str(original_index)):
            raise RuntimeError("FAILED_EMBEDDING_REPLACED_ACTIVE_INDEX")
        if (state["status"] == "FAILED" and state["cleaned"]
                and state["chunk_rows"] == 0 and state["embedding_rows"] == 0):
            return state
        time.sleep(0.2)
    raise RuntimeError("FAILED_CANDIDATE_NOT_PHYSICALLY_CLEANED")


def _error_code(response: httpx.Response) -> str | None:
    try:
        return response.json().get("code")
    except (ValueError, AttributeError):
        return None


def _internal_post(client: httpx.Client, secret: str, path: str,
                   payload: dict) -> httpx.Response:
    return client.post(path, headers={
        "Authorization": f"Bearer {secret}",
        "X-Request-ID": payload["request_id"],
    }, json=payload)


def _stale_success_completion(attempt: dict) -> dict:
    lease = attempt["lease"]
    batch = attempt["batch"]
    model_profile = "BAAI/bge-m3"
    batches = [{
        "batch_sequence": batch["batch_sequence"],
        "batch_id": batch["batch_id"],
        "batch_sha256": batch["batch_sha256"],
        "chunk_count": len(batch["chunks"]),
    }]
    count = len(batch["chunks"])
    return {
        "contract_version": CONTRACT_VERSION,
        "request_id": str(uuid.uuid4()),
        "lease": lease,
        "outcome": "SUCCEEDED",
        "manifest": {
            "chunk_count": count,
            "embedding_count": count,
            "embedding_dimensions": 1024,
            "embedding_model_profile_id": model_profile,
            "manifest_sha256": manifest_sha256(lease, model_profile, batches, count),
        },
    }


def _wait_http_ready(process, url, path):
    local.wait_ready(process, url, path)


def serve_python():
    import knowflow_ai.answering as answering
    import knowflow_ai.worker as worker
    from knowflow_ai.java_client import JavaGateway

    class RecoveryLlm(local.SyntheticLlm):
        async def stream_content(self, question, evidence, *, request_id):
            marker = os.environ.get("KNOWFLOW_RECOVERY_ANSWER_MARKER")
            if marker and BLOCK_ANSWER_MARKER in question:
                _write_json(Path(marker), {"request_id": request_id, "started": True})
                await asyncio.Event().wait()
            source_id = evidence[0]["source_id"]
            answer = f"Synthetic evidence verified. [{source_id}]"
            yield json.dumps({"answer": answer, "has_answer": True,
                              "source_ids": [source_id]}, ensure_ascii=False,
                             separators=(",", ":"))

    answering.SiliconFlowEmbeddingAdapter = local.SyntheticEmbedding
    answering.DeepSeekAdapter = RecoveryLlm
    failure_marker = os.environ.get("KNOWFLOW_RECOVERY_SECOND_EMBEDDING_MARKER")
    worker.SiliconFlowEmbeddingAdapter = (
        (lambda settings: SecondBatchFailureEmbedding(settings, marker=Path(failure_marker)))
        if failure_marker else local.SyntheticEmbedding)

    original_write_batch = JavaGateway.write_batch
    marker_dir = Path(os.environ["KNOWFLOW_RECOVERY_MARKER_DIR"])
    marker_prefix = os.environ["KNOWFLOW_RECOVERY_MARKER_PREFIX"]
    gate_fencings = {
        int(value) for value in os.environ.get("KNOWFLOW_RECOVERY_GATE_FENCINGS", "").split(",")
        if value
    }

    async def write_batch_with_fault_gate(self, batch):
        receipt = await original_write_batch(self, batch)
        fencing = batch["lease"]["fencing"]
        marker = marker_dir / f"{marker_prefix}-fence-{fencing}.json"
        if fencing in gate_fencings and not marker.exists():
            _write_json(marker, {"lease": batch["lease"], "batch": batch,
                                 "receipt": receipt})
            await asyncio.Event().wait()
        return receipt

    JavaGateway.write_batch = write_batch_with_fault_gate
    from knowflow_ai.app import create_app
    import uvicorn
    uvicorn.run(create_app(), host="127.0.0.1", port=8000,
                log_level="warning", access_log=False)


class RecoveryHarness:
    def __init__(self, args, dotenv, database_name, database_url,
                 java_env, python_env, log):
        self.args = args
        self.dotenv = dotenv
        self.database_name = database_name
        self.database_url = database_url
        self.java_env = java_env
        self.python_env = python_env
        self.log = log
        self.java_process = None
        self.python_process = None
        self.token = None
        self.sensitive_values = []
        self.knowledge_bases = []
        self.run_id = uuid.uuid4().hex
        self.marker_dir = Path(tempfile.gettempdir()) / f"knowflow-recovery-{self.run_id}"
        self.marker_dir.mkdir()

    def start_java(self):
        if self.java_process is not None and self.java_process.poll() is None:
            return
        wrapper = REPO / "services/api/mvnw.cmd" if os.name == "nt" else REPO / "services/api/mvnw"
        package = (["cmd.exe", "/d", "/c", str(wrapper), "-B", "-q",
                    "-DskipTests", "package"] if os.name == "nt"
                   else [str(wrapper), "-B", "-q", "-DskipTests", "package"])
        if self.args.maven_settings:
            package.extend(["-s", str(self.args.maven_settings.resolve())])
        if not getattr(self, "package_built", False):
            build = subprocess.run(package, cwd=REPO / "services/api", env=self.java_env,
                                   stdout=self.log, stderr=self.log, timeout=300)
            if build.returncode:
                raise RuntimeError("JAVA_PACKAGE_FAILED")
            self.package_built = True
        jar = REPO / "services/api/target/knowflow-api-0.2.0-SNAPSHOT.jar"
        java = shutil.which("java")
        if not jar.is_file() or java is None:
            raise RuntimeError("JAVA_RUNTIME_OR_PACKAGE_MISSING")
        self.java_process = subprocess.Popen(
            [java, "-jar", str(jar)], cwd=REPO, env=self.java_env,
            stdout=self.log, stderr=self.log)
        _wait_http_ready(self.java_process, "http://127.0.0.1:8080", "/actuator/health")

    def stop_java(self):
        local.stop(self.java_process)
        self.java_process = None

    def start_python(self, *, gate_fencings=(), prefix="worker", answer_marker=None,
                     second_embedding_marker=None):
        if self.python_process is not None and self.python_process.poll() is None:
            return
        env = self.python_env.copy()
        env["KNOWFLOW_RECOVERY_MARKER_DIR"] = str(self.marker_dir)
        env["KNOWFLOW_RECOVERY_MARKER_PREFIX"] = prefix
        env["KNOWFLOW_RECOVERY_GATE_FENCINGS"] = ",".join(map(str, gate_fencings))
        if answer_marker:
            env["KNOWFLOW_RECOVERY_ANSWER_MARKER"] = str(answer_marker)
        else:
            env.pop("KNOWFLOW_RECOVERY_ANSWER_MARKER", None)
        if second_embedding_marker:
            env["KNOWFLOW_RECOVERY_SECOND_EMBEDDING_MARKER"] = str(second_embedding_marker)
        else:
            env.pop("KNOWFLOW_RECOVERY_SECOND_EMBEDDING_MARKER", None)
        self.python_process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--serve"],
            cwd=REPO, env=env, stdout=self.log, stderr=self.log)
        _wait_http_ready(self.python_process, "http://127.0.0.1:8000", "/health/live")

    def stop_python(self):
        local.stop(self.python_process)
        self.python_process = None

    def client(self, timeout=15):
        return httpx.Client(base_url="http://127.0.0.1:8080", timeout=timeout,
                            trust_env=False)

    def create_owner(self):
        email = f"recovery-{self.run_id}@example.test"
        password = f"Recovery-{self.run_id[:20]}-Pass"
        self.dotenv["_recovery_password"] = password
        self.sensitive_values.append(password)
        with self.client() as client:
            response = client.post("/api/v1/auth/register", json={
                "contract_version": CONTRACT_VERSION, "email": email,
                "password": password})
        if response.status_code != 201:
            raise RuntimeError("RECOVERY_OWNER_CREATE_FAILED")
        self.token = response.json()["access_token"]
        self.sensitive_values.append(self.token)
        return self.token

    def create_knowledge_base(self, label):
        with self.client() as client:
            response = client.post("/api/v1/knowledge-bases",
                headers={"Authorization": f"Bearer {self.token}"},
                json={"contract_version": CONTRACT_VERSION,
                      "name": f"Recovery {label} {self.run_id[:8]}"})
        if response.status_code != 201:
            raise RuntimeError("RECOVERY_KNOWLEDGE_BASE_CREATE_FAILED")
        knowledge_base_id = response.json()["id"]
        self.knowledge_bases.append(knowledge_base_id)
        return knowledge_base_id

    def upload_document(self, knowledge_base_id, filename, contents=DOCUMENT_TEXT):
        with self.client() as client:
            accepted = local.upload(client, self.token, knowledge_base_id,
                                    filename, contents)
        return accepted["document_id"], accepted["task_id"]

    def marker(self, prefix, fencing):
        return self.marker_dir / f"{prefix}-fence-{fencing}.json"

    def wait_gate(self, prefix, fencing):
        return _wait_marker(self.marker(prefix, fencing), self.python_process)

    def delete_knowledge_bases_and_wait(self):
        if self.java_process is None or self.java_process.poll() is not None:
            self.start_java()
        if self.python_process is None or self.python_process.poll() is not None:
            self.start_python(prefix="cleanup")
        failures = []
        for knowledge_base_id in list(self.knowledge_bases):
            try:
                with self.client(timeout=10) as client:
                    response = client.delete(
                        f"/api/v1/knowledge-bases/{knowledge_base_id}",
                        headers={"Authorization": f"Bearer {self.token}"})
                if response.status_code not in (204, 404):
                    failures.append("KNOWLEDGE_BASE_DELETE_FAILED")
            except httpx.HTTPError:
                failures.append("KNOWLEDGE_BASE_DELETE_FAILED")
        if failures:
            raise RuntimeError(failures[0])
        self.knowledge_bases.clear()
        _wait_cleanup(self.database_url)

    def logout(self):
        if not self.token:
            return
        with self.client(timeout=10) as client:
            response = client.post("/api/v1/auth/logout",
                headers={"Authorization": f"Bearer {self.token}"})
        if response.status_code != 204:
            raise RuntimeError("RECOVERY_SESSION_LOGOUT_FAILED")
        self.token = None


def _scenario_worker_restarts(harness: RecoveryHarness) -> dict:
    database_url = harness.database_url
    harness.stop_python()
    harness.start_python(gate_fencings=(1,), prefix="single")
    knowledge_base_id = harness.create_knowledge_base("single-restart")
    document_id, task_id = harness.upload_document(knowledge_base_id, "single-restart.txt")
    first = harness.wait_gate("single", 1)
    harness.stop_python()
    harness.start_python(gate_fencings=(1,), prefix="single")
    completed = _wait_task(database_url, task_id, {"SUCCEEDED"})
    if completed["fencing"] != 2 or completed["attempt_count"] != 2:
        raise RuntimeError("WORKER_RESTART_DID_NOT_ADVANCE_FENCING")

    old_lease = first["lease"]
    old_batch = first["batch"]
    with harness.client() as client:
        stale_batch = _internal_post(
            client, harness.dotenv["KNOWFLOW_INTERNAL_SHARED_SECRET"],
            f"/internal/v1/tasks/{task_id}/index-batches", old_batch)
        stale_completion = _internal_post(
            client, harness.dotenv["KNOWFLOW_INTERNAL_SHARED_SECRET"],
            f"/internal/v1/tasks/{task_id}/completion",
            _stale_success_completion(first))
    if (_error_code(stale_batch) != "LEASE_REJECTED"
            or stale_batch.status_code != 409
            or _error_code(stale_completion) != "LEASE_REJECTED"
            or stale_completion.status_code != 409):
        raise RuntimeError("STALE_EXECUTION_WAS_NOT_FENCED")
    document = _document_row(database_url, document_id)
    if document["status"] != "ACTIVE" or document["active_index_version_id"] != completed["index_version_id"]:
        raise RuntimeError("RECOVERED_INDEX_NOT_ACTIVE")
    if document["active_index_version_id"] == old_lease["index_version_id"]:
        raise RuntimeError("STALE_INDEX_WAS_PUBLISHED")
    return {"passed": True, "first_fencing": old_lease["fencing"],
            "recovered_fencing": completed["fencing"],
            "stale_batch_rejected": True, "stale_completion_rejected": True,
            "recovered_document_ready": True}


def _scenario_retry_limit_preserves_active(harness: RecoveryHarness) -> dict:
    database_url = harness.database_url
    harness.stop_python()
    harness.start_python(prefix="retry-initial")
    knowledge_base_id = harness.create_knowledge_base("retry-limit")
    document_id, initial_task = harness.upload_document(
        knowledge_base_id, "retry-limit.txt")
    _wait_task(database_url, initial_task, {"SUCCEEDED"})
    original = str(_document_row(database_url, document_id)["active_index_version_id"])
    if not original:
        raise RuntimeError("INITIAL_ACTIVE_INDEX_MISSING")
    harness.stop_python()
    harness.start_python(gate_fencings=(1, 2, 3), prefix="retries")
    with harness.client() as client:
        rebuilt = client.post(f"/api/v1/documents/{document_id}/rebuilds",
                              headers={"Authorization": f"Bearer {harness.token}"})
    if rebuilt.status_code != 202:
        raise RuntimeError("DOCUMENT_REBUILD_NOT_ACCEPTED")
    task_id = rebuilt.json()["task_id"]
    attempts = []
    for fencing in (1, 2, 3):
        try:
            attempts.append(harness.wait_gate("retries", fencing))
        except RuntimeError as failure:
            task = _task_row(database_url, task_id)
            raise RuntimeError(
                f"RETRY_GATE_{fencing}_NOT_REACHED_{task['status']}_"
                f"{task['attempt_count']}_{task['fencing']}") from failure
        harness.stop_python()
        if fencing < 3:
            harness.start_python(gate_fencings=(1, 2, 3), prefix="retries")
    failed = _wait_task(database_url, task_id, {"FAILED"})
    if (failed["failure_code"] != "WORKER_LOST" or failed["attempt_count"] != 3
            or failed["fencing"] != 3):
        raise RuntimeError("WORKER_RETRY_LIMIT_NOT_ENFORCED")
    final_document = _document_row(database_url, document_id)
    if str(final_document["active_index_version_id"]) != original:
        raise RuntimeError("RETRY_FAILURE_REPLACED_ACTIVE_INDEX")

    harness.start_python(prefix="retry-verification")
    with harness.client(timeout=20) as client:
        answer = client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/questions",
            headers={"Authorization": f"Bearer {harness.token}"},
            json={"question": "What does the active recovery evidence say?"})
    if answer.status_code != 200:
        raise RuntimeError("PREVIOUS_ACTIVE_INDEX_NOT_QUERYABLE")
    sources = answer.json().get("sources", [])
    if not sources or sources[0].get("index_version_id") != original:
        raise RuntimeError("QUERY_DID_NOT_USE_PREVIOUS_ACTIVE_INDEX")
    return {"passed": True, "attempt_count": failed["attempt_count"],
            "failure_code": failed["failure_code"],
            "previous_active_index_preserved": True,
            "previous_active_index_queryable": True,
            "distinct_failed_candidates": len({
                item["lease"]["index_version_id"] for item in attempts})}


def _scenario_second_embedding_batch_failure(harness: RecoveryHarness) -> dict:
    harness.stop_python()
    harness.start_python(prefix="embedding-initial")
    knowledge_base_id = harness.create_knowledge_base("embedding-failure")
    document_id, initial_task = harness.upload_document(
        knowledge_base_id, "embedding-failure.txt", LONG_DOCUMENT_TEXT)
    _wait_task(harness.database_url, initial_task, {"SUCCEEDED"})
    original = str(_document_row(harness.database_url, document_id)["active_index_version_id"])
    if original == "None":
        raise RuntimeError("INITIAL_ACTIVE_INDEX_MISSING")

    harness.stop_python()
    marker = harness.marker_dir / "second-embedding-failure.json"
    harness.start_python(prefix="embedding-failure", second_embedding_marker=marker)
    with harness.client() as client:
        rebuilt = client.post(f"/api/v1/documents/{document_id}/rebuilds",
                              headers={"Authorization": f"Bearer {harness.token}"})
    if rebuilt.status_code != 202:
        raise RuntimeError("DOCUMENT_REBUILD_NOT_ACCEPTED")
    task_id = rebuilt.json()["task_id"]
    fault = _wait_marker(marker, harness.python_process)
    failed = _wait_task(harness.database_url, task_id, {"FAILED"})
    if fault != {"successful_batches": 1, "failed_batch": 2}:
        raise RuntimeError("SECOND_EMBEDDING_FAILURE_NOT_REACHED")
    if failed["failure_code"] != "MODEL_FAILURE" or failed["attempt_count"] != 1:
        raise RuntimeError("SECOND_EMBEDDING_FAILURE_NOT_REPORTED")
    with psycopg.connect(harness.database_url, autocommit=True) as db:
        prior_writes = db.execute(
            "SELECT count(*) FROM knowflow.index_batch_receipts WHERE task_id = %s",
            (task_id,)).fetchone()[0]
    if prior_writes < 1:
        raise RuntimeError("EMBEDDING_FIRST_BATCH_WAS_NOT_PERSISTED")
    failed_index = failed["index_version_id"]
    if failed_index is None or str(failed_index) == original:
        raise RuntimeError("FAILED_CANDIDATE_INDEX_INVALID")
    candidate = _wait_failed_candidate_cleanup(harness.database_url, failed_index, original)
    if str(_document_row(harness.database_url, document_id)["active_index_version_id"]) != original:
        raise RuntimeError("FAILED_EMBEDDING_REPLACED_ACTIVE_INDEX")

    harness.stop_python()
    harness.start_python(prefix="embedding-verification")
    with harness.client(timeout=20) as client:
        answer = client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/questions",
            headers={"Authorization": f"Bearer {harness.token}"},
            json={"question": "What does the active recovery evidence say?"})
    sources = answer.json().get("sources", []) if answer.status_code == 200 else []
    if not sources or sources[0].get("index_version_id") != original:
        raise RuntimeError("PREVIOUS_ACTIVE_INDEX_NOT_QUERYABLE")
    cleanup = _wait_cleanup(harness.database_url)
    return {"passed": True, "successful_embedding_batches": 1,
            "failed_embedding_batch": 2, "prior_persisted_batches": prior_writes,
            "failure_code": failed["failure_code"], "attempt_count": failed["attempt_count"],
            "previous_active_index_preserved": True, "previous_active_index_queryable": True,
            "failed_candidate_status": candidate["status"],
            "failed_candidate_cleaned": candidate["cleaned"],
            "failed_candidate_chunk_rows": candidate["chunk_rows"],
            "failed_candidate_embedding_rows": candidate["embedding_rows"],
            "cleanup_queues_drained": cleanup == {
                "unfinished_tasks": 0, "cleanup_queue_rows": 0}}


def _scenario_java_restart_recovers_question(harness: RecoveryHarness) -> dict:
    database_url = harness.database_url
    harness.stop_python()
    harness.start_python(prefix="question-initial")
    knowledge_base_id = harness.create_knowledge_base("question-restart")
    document_id, task_id = harness.upload_document(
        knowledge_base_id, "question-restart.txt")
    _wait_task(database_url, task_id, {"SUCCEEDED"})
    answer_marker = harness.marker_dir / "answer-gated.json"
    question = f"{BLOCK_ANSWER_MARKER} {harness.run_id} What does the source confirm?"
    read_result = []

    def read_stream():
        try:
            with harness.client(timeout=httpx.Timeout(None, connect=5)) as client:
                with client.stream(
                        "POST",
                        f"/api/v1/knowledge-bases/{knowledge_base_id}/questions/stream",
                        headers={"Authorization": f"Bearer {harness.token}"},
                        json={"question": question}) as response:
                    read_result.append(("status", response.status_code))
                    if response.status_code == 200:
                        for _line in response.iter_lines():
                            pass
        except (httpx.HTTPError, OSError):
            read_result.append(("closed", None))

    harness.stop_python()
    harness.start_python(prefix="answer-gate", answer_marker=answer_marker)
    reader = threading.Thread(target=read_stream, daemon=True)
    reader.start()
    marker = _wait_marker(answer_marker, harness.java_process, timeout=2.5)
    if not marker.get("started"):
        raise RuntimeError("SYNTHETIC_ANSWER_GATE_INVALID")
    harness.stop_java()
    reader.join(timeout=5)
    if reader.is_alive():
        raise RuntimeError("QUESTION_STREAM_READER_DID_NOT_CLOSE")

    with psycopg.connect(database_url, autocommit=True) as connection:
        row = connection.execute("""
            SELECT id, status, failure_code FROM knowflow.questions
             WHERE question_text = %s ORDER BY created_at DESC LIMIT 1
        """, (question,)).fetchone()
    if row is None:
        raise RuntimeError("INTERRUPTED_QUESTION_NOT_PERSISTED")
    question_id, status, failure_code = row
    if status != "PROCESSING":
        raise RuntimeError("QUESTION_NOT_PROCESSING_AT_JAVA_SHUTDOWN")
    harness.start_java()

    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        with psycopg.connect(database_url, autocommit=True) as connection:
            state = connection.execute("""
                SELECT status, failure_code, answer_text,
                       (SELECT count(*) FROM knowflow.question_sources s
                         WHERE s.question_id = q.id)
                  FROM knowflow.questions q WHERE q.id = %s
            """, (question_id,)).fetchone()
        if state[0] == "FAILED":
            break
        time.sleep(0.15)
    if state != ("FAILED", "PROCESSING_TIMEOUT", None, 0):
        raise RuntimeError("INTERRUPTED_QUESTION_RECOVERY_INVALID")
    return {"passed": True, "recovered_status": state[0],
            "failure_code": state[1], "answer_absent": state[2] is None,
            "sources_absent": state[3] == 0}


def _scenario_delete_while_worker_offline(harness: RecoveryHarness) -> dict:
    database_url = harness.database_url
    knowledge_base_id = harness.create_knowledge_base("offline-delete")
    document_id, initial_task = harness.upload_document(
        knowledge_base_id, "offline-delete.txt")
    _wait_task(database_url, initial_task, {"SUCCEEDED"})
    before = _document_row(database_url, document_id)
    harness.stop_python()
    harness.start_python(gate_fencings=(1,), prefix="offline-delete")
    with harness.client() as client:
        accepted = client.post(f"/api/v1/documents/{document_id}/rebuilds",
                               headers={"Authorization": f"Bearer {harness.token}"})
    if accepted.status_code != 202:
        raise RuntimeError("OFFLINE_DELETE_REBUILD_NOT_ACCEPTED")
    rebuild_task = accepted.json()["task_id"]
    attempt = harness.wait_gate("offline-delete", 1)
    harness.stop_python()
    with harness.client() as client:
        deleted = client.delete(f"/api/v1/documents/{document_id}",
                                headers={"Authorization": f"Bearer {harness.token}"})
    if deleted.status_code != 204:
        raise RuntimeError("OFFLINE_DOCUMENT_DELETE_FAILED")
    task_after_delete = _task_row(database_url, rebuild_task)
    harness.stop_java()
    harness.start_java()
    harness.start_python(prefix="offline-delete-restarted")

    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            cleanup = _cleanup_state(database_url)
            final_doc = _document_row(database_url, document_id)
            if cleanup == {"unfinished_tasks": 0, "cleanup_queue_rows": 0}:
                break
        except psycopg.Error:
            time.sleep(0.2)
        time.sleep(0.2)
    else:
        raise RuntimeError("OFFLINE_DELETE_CLEANUP_DID_NOT_DRAIN")
    if (final_doc["status"] != "DELETED" or final_doc["active_index_version_id"] is not None
            or final_doc["chunk_rows"] != 0 or final_doc["embedding_rows"] != 0):
        raise RuntimeError("DELETED_DOCUMENT_WAS_RESURRECTED")

    content_version_id = before["content_version_id"]
    with harness.client() as client:
        headers = {"Authorization": f"Bearer {harness.token}"}
        document_response = client.get(f"/api/v1/documents/{document_id}", headers=headers)
        file_response = client.get(
            f"/api/v1/documents/{document_id}/contents/{content_version_id}/file",
            headers=headers)
        question_response = client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/questions",
            headers=headers, json={"question": "Read the deleted document."})
    source_request = {
        "contract_version": CONTRACT_VERSION,
        "request_id": str(uuid.uuid4()),
        "lease": attempt["lease"],
    }
    with harness.client() as client:
        source_response = _internal_post(
            client, harness.dotenv["KNOWFLOW_INTERNAL_SHARED_SECRET"],
            f"/internal/v1/tasks/{rebuild_task}/source", source_request)
    if (document_response.status_code != 404 or file_response.status_code != 404
            or question_response.status_code not in (404, 409)
            or source_response.status_code not in (404, 409)
            or task_after_delete["status"] not in ("CANCELLED", "FAILED")):
        raise RuntimeError("DELETED_DOCUMENT_READ_OR_SOURCE_NOT_DENIED")
    return {"passed": True, "worker_was_offline_at_delete": True,
            "services_restarted": True, "document_remained_deleted": True,
            "document_get_denied": document_response.status_code == 404,
            "source_file_denied": file_response.status_code == 404,
            "question_retrieval_denied": question_response.status_code in (404, 409),
            "internal_source_read_denied": source_response.status_code in (404, 409),
            "cleanup_queues_drained": cleanup == {
                "unfinished_tasks": 0, "cleanup_queue_rows": 0}}


def _restore_isolated_service(env_path: Path, service: str) -> None:
    result = _run_compose(env_path, ["up", "-d", service])
    if result.returncode:
        raise RuntimeError("ISOLATED_SERVICE_RESTART_FAILED")
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        result = _run_compose(env_path, ["ps", "--format", "json"])
        if result.returncode == 0:
            items = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
            if any(item.get("Service") == service and item.get("Health") == "healthy"
                   for item in items):
                return
        time.sleep(0.5)
    raise RuntimeError("ISOLATED_SERVICE_RESTART_TIMEOUT")


def _wait_minio_ready(timeout: float = 90) -> dict:
    deadline = time.monotonic() + timeout
    attempts = 0
    status = None
    while time.monotonic() < deadline:
        attempts += 1
        try:
            response = httpx.get("http://127.0.0.1:59000/minio/health/ready",
                                 timeout=2, trust_env=False)
            status = response.status_code
            if status == 200:
                return {"passed": True, "attempts": attempts, "http_status": status}
        except httpx.HTTPError:
            status = None
        time.sleep(0.5)
    return {"passed": False, "attempts": attempts, "http_status": status}


def _safe_storage_failure_details(log, offset) -> dict:
    details = {"http_status": None, "message_kind": None, "cause_class": None}
    if log is None or offset is None:
        return details
    try:
        log.flush()
        end = log.seek(0, os.SEEK_END)
        log.seek(offset)
        data = log.read(end - offset)
        log.seek(end)
    except (OSError, ValueError):
        return details
    if isinstance(data, str):
        data = data.encode("utf-8", errors="replace")
    matches = list(re.finditer(
        rb"Source upload failed: (?:Object storage returned HTTP (?P<status>[1-9][0-9]{2})|"
        rb"(?P<failed>Object storage request failed)|"
        rb"(?P<interrupted>Object storage request was interrupted)) "
        rb"\((?P<cause>[A-Za-z_$][A-Za-z0-9_$]{0,79}|none)\)", data))
    if matches:
        match = matches[-1]
        message_kind = ("HTTP_STATUS" if match.group("status") else
                        "REQUEST_FAILED" if match.group("failed") else
                        "REQUEST_INTERRUPTED")
        details = {"http_status": int(match.group("status"))
                   if match.group("status") else None,
                   "message_kind": message_kind,
                   "cause_class": match.group("cause").decode("ascii")}
    return details


def _minio_write_canary(harness: RecoveryHarness, readiness: dict) -> dict:
    result = {
        "passed": False,
        "readiness": readiness,
        "failure_stage": None if readiness["passed"] else "readiness",
        "upload": {"attempted": False, "accepted": False, "http_status": None,
                   "error_code": None,
                   "storage_failure": {"http_status": None, "message_kind": None,
                                       "cause_class": None}},
        "readback": {"attempted": False, "http_status": None, "matches": False},
        "cleanup": {"attempted": False, "http_status": None,
                    "confirmed": False, "queues_drained": False},
    }
    if not readiness["passed"]:
        return result

    knowledge_base_id = None
    log_offset = None
    try:
        knowledge_base_id = harness.create_knowledge_base("minio-write-canary")
        filename = "minio-write-canary.txt"
        contents = b"Synthetic MinIO recovery write/read/delete canary.\n"
        result["upload"]["attempted"] = True
        try:
            harness.log.flush()
            log_offset = harness.log.seek(0, os.SEEK_END)
        except (AttributeError, OSError, ValueError):
            log_offset = None
        document_id, _task_id = harness.upload_document(
            knowledge_base_id, filename, contents.decode("utf-8"))
        result["upload"].update(accepted=True, http_status=202)

        document = _document_row(harness.database_url, document_id)
        path = (f"/api/v1/documents/{document_id}/contents/"
                f"{document['content_version_id']}/file")
        result["readback"]["attempted"] = True
        with harness.client(timeout=10) as client:
            response = client.get(path, headers={"Authorization": f"Bearer {harness.token}"})
        result["readback"].update(http_status=response.status_code,
                                  matches=response.status_code == 200 and response.content == contents)
        if not result["readback"]["matches"]:
            result["failure_stage"] = "readback"
    except RuntimeError as error:
        result["failure_stage"] = result["failure_stage"] or (
            "upload" if result["upload"]["attempted"] and not result["upload"]["accepted"]
            else "readback" if result["upload"]["accepted"] else "setup")
        match = re.fullmatch(r"UPLOAD_FAILED_(\d{3})_([A-Z][A-Z0-9_]{0,63})", str(error))
        if match:
            result["upload"].update(http_status=int(match.group(1)), error_code=match.group(2))
            result["upload"]["storage_failure"] = _safe_storage_failure_details(
                getattr(harness, "log", None), log_offset)
    except httpx.HTTPError:
        if result["upload"]["attempted"] and not result["upload"]["accepted"]:
            result["failure_stage"] = "upload"
        else:
            result["failure_stage"] = "readback"
            result["readback"]["http_status"] = None
    except Exception:
        result["failure_stage"] = result["failure_stage"] or (
            "upload" if result["upload"]["attempted"] and not result["upload"]["accepted"]
            else "readback" if result["upload"]["accepted"] else "setup")
    finally:
        if knowledge_base_id is not None:
            result["cleanup"]["attempted"] = True
            try:
                with harness.client(timeout=10) as client:
                    response = client.delete(
                        f"/api/v1/knowledge-bases/{knowledge_base_id}",
                        headers={"Authorization": f"Bearer {harness.token}"})
                result["cleanup"]["http_status"] = response.status_code
                deleted = response.status_code in (204, 404)
                if deleted:
                    cleanup = _wait_cleanup(harness.database_url)
                    result["cleanup"]["queues_drained"] = cleanup == {
                        "unfinished_tasks": 0, "cleanup_queue_rows": 0}
                    if result["cleanup"]["queues_drained"]:
                        result["cleanup"]["confirmed"] = True
                        if knowledge_base_id in harness.knowledge_bases:
                            harness.knowledge_bases.remove(knowledge_base_id)
                if not result["cleanup"]["confirmed"]:
                    result["failure_stage"] = result["failure_stage"] or "cleanup"
            except Exception:
                result["failure_stage"] = result["failure_stage"] or "cleanup"

    result["passed"] = (
        result["readiness"]["passed"]
        and result["upload"]["accepted"]
        and result["readback"]["matches"]
        and result["cleanup"]["confirmed"]
    )
    return result


def _outage_failure_code(service: str, canary_passed, cleanup_drained: bool):
    if canary_passed is False:
        return "MINIO_RECOVERY_WRITE_CANARY_FAILED"
    if not cleanup_drained:
        return f"{service.upper()}_RECOVERY_CLEANUP_FAILED"
    return None


def _scenario_service_outage(harness: RecoveryHarness, service: str) -> dict:
    if _ISOLATED_COMPOSE is None or service not in {"postgres", "minio"}:
        raise RuntimeError("OUTAGE_REQUIRES_OWN_ISOLATED_COMPOSE")
    env_path = harness.args.env_file
    harness.start_python(prefix=f"{service}-outage")
    knowledge_base_id = harness.create_knowledge_base(f"{service}-outage")
    document_id, task_id = harness.upload_document(knowledge_base_id, f"{service}-outage.txt")
    _wait_task(harness.database_url, task_id, {"SUCCEEDED"})
    before = _document_row(harness.database_url, document_id)
    original = str(before["active_index_version_id"])
    if before["active_index_version_id"] is None:
        raise RuntimeError("INITIAL_ACTIVE_INDEX_MISSING")
    document_path = f"/api/v1/documents/{document_id}"
    file_path = f"{document_path}/contents/{before['content_version_id']}/file"
    headers = {"Authorization": f"Bearer {harness.token}"}
    path = document_path if service == "postgres" else file_path
    with harness.client(timeout=10) as client:
        baseline = client.get(path, headers=headers)
    if baseline.status_code != 200:
        raise RuntimeError("OUTAGE_BASELINE_REQUEST_FAILED")
    try:
        stopped = _run_compose(env_path, ["stop", service])
        if stopped.returncode:
            raise RuntimeError("ISOLATED_SERVICE_STOP_FAILED")
        result = _run_compose(env_path, ["ps", "--all", "--format", "json"])
        items = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        if result.returncode or not any(item.get("Service") == service and
                                        item.get("State") in {"exited", "stopped"}
                                        for item in items):
            raise RuntimeError("ISOLATED_SERVICE_NOT_STOPPED")
        try:
            with harness.client(timeout=6) as client:
                response = client.get(path, headers=headers)
            unavailable = response.status_code != 200
        except httpx.TransportError:
            unavailable = True
        if not unavailable:
            raise RuntimeError("OUTAGE_REQUEST_UNEXPECTEDLY_SUCCEEDED")
    finally:
        _restore_isolated_service(env_path, service)

    readiness = None
    if service == "minio":
        readiness = _wait_minio_ready()
        if not readiness["passed"]:
            canary = _minio_write_canary(harness, readiness)
            return {"passed": False, "service": service,
                    "request_failed_during_outage": True, "request_recovered": False,
                    "failure_code": "MINIO_READY_TIMEOUT",
                    "storage_canary": canary}

    deadline = time.monotonic() + 60
    recovered = False
    while time.monotonic() < deadline:
        try:
            with harness.client(timeout=5) as client:
                response = client.get(path, headers=headers)
            if response.status_code == 200:
                recovered = True
                break
        except httpx.TransportError:
            pass
        time.sleep(0.5)
    if not recovered:
        raise RuntimeError("OUTAGE_REQUEST_DID_NOT_RECOVER")
    if service == "minio" and (not baseline.content or response.content != baseline.content):
        raise RuntimeError("RESTORED_SOURCE_BYTES_CHANGED")
    after = _document_row(harness.database_url, document_id)
    if after["status"] != "ACTIVE" or str(after["active_index_version_id"]) != original:
        raise RuntimeError("OUTAGE_REPLACED_ACTIVE_INDEX")
    with harness.client(timeout=20) as client:
        answer = client.post(f"/api/v1/knowledge-bases/{knowledge_base_id}/questions",
                             headers=headers, json={"question": "What does the evidence say?"})
    sources = answer.json().get("sources", []) if answer.status_code == 200 else []
    if not sources or sources[0].get("index_version_id") != original:
        raise RuntimeError("PREVIOUS_ACTIVE_INDEX_NOT_QUERYABLE")
    cleanup = _wait_cleanup(harness.database_url)
    canary = _minio_write_canary(harness, readiness) if service == "minio" else None
    cleanup_drained = cleanup == {"unfinished_tasks": 0, "cleanup_queue_rows": 0}
    failure_code = _outage_failure_code(
        service, canary["passed"] if canary is not None else None, cleanup_drained)
    passed = failure_code is None
    return {"passed": passed,
            **({"failure_code": failure_code} if failure_code is not None else {}),
            "service": service, "baseline_request_succeeded": True,
            "request_failed_during_outage": True, "request_recovered": True,
            "source_bytes_preserved": True if service == "minio" else None,
            "previous_active_index_preserved": True, "previous_active_index_queryable": True,
            "cleanup_queues_drained": cleanup_drained,
            **({"storage_canary": canary} if canary is not None else {})}


def _scenario_postgres_outage_during_index_write(harness: RecoveryHarness) -> dict:
    if _ISOLATED_COMPOSE is None:
        raise RuntimeError("OUTAGE_REQUIRES_OWN_ISOLATED_COMPOSE")
    database_url = harness.database_url
    env_path = harness.args.env_file
    harness.stop_python()
    harness.start_python(prefix="write-outage-initial")
    base_id = harness.create_knowledge_base("postgres-write-outage")
    document_id, initial_task = harness.upload_document(base_id, "postgres-write-outage.txt")
    _wait_task(database_url, initial_task, {"SUCCEEDED"})
    original = _document_row(database_url, document_id)["active_index_version_id"]
    if original is None:
        raise RuntimeError("INITIAL_ACTIVE_INDEX_MISSING")
    harness.stop_python()
    harness.start_python(gate_fencings=(1,), prefix="postgres-write-outage")
    with harness.client() as client:
        rebuilt = client.post(f"/api/v1/documents/{document_id}/rebuilds",
                              headers={"Authorization": f"Bearer {harness.token}"})
    if rebuilt.status_code != 202:
        raise RuntimeError("DOCUMENT_REBUILD_NOT_ACCEPTED")
    task_id = rebuilt.json()["task_id"]
    first = harness.wait_gate("postgres-write-outage", 1)
    if _document_row(database_url, document_id)["active_index_version_id"] != original:
        raise RuntimeError("CANDIDATE_PUBLISHED_BEFORE_FAILURE")
    try:
        stopped = _run_compose(env_path, ["stop", "postgres"])
        if stopped.returncode:
            raise RuntimeError("ISOLATED_SERVICE_STOP_FAILED")
        state = _run_compose(env_path, ["ps", "--all", "--format", "json"])
        items = [json.loads(line) for line in state.stdout.splitlines() if line.strip()]
        if state.returncode or not any(item.get("Service") == "postgres" and
                                       item.get("State") in {"exited", "stopped"} for item in items):
            raise RuntimeError("ISOLATED_SERVICE_NOT_STOPPED")
        try:
            with harness.client(timeout=8) as client:
                response = _internal_post(client, harness.dotenv["KNOWFLOW_INTERNAL_SHARED_SECRET"],
                                          f"/internal/v1/tasks/{task_id}/index-batches", first["batch"])
            if 200 <= response.status_code < 300:
                raise RuntimeError("INDEX_WRITE_SUCCEEDED_WITH_POSTGRES_STOPPED")
        except httpx.TransportError:
            pass
        harness.stop_python()
    finally:
        _restore_isolated_service(env_path, "postgres")
    if _document_row(database_url, document_id)["active_index_version_id"] != original:
        raise RuntimeError("CANDIDATE_PUBLISHED_DURING_OUTAGE")
    harness.start_python(gate_fencings=(1,), prefix="postgres-write-outage")
    completed = _wait_task(database_url, task_id, {"SUCCEEDED"}, timeout=90)
    if (completed["fencing"] <= first["lease"]["fencing"]
            or completed["attempt_count"] != completed["fencing"]):
        raise RuntimeError("OUTAGE_RECOVERY_DID_NOT_ADVANCE_FENCING:"
                           f"first={first['lease']['fencing']},"
                           f"recovered={completed['fencing']},attempts={completed['attempt_count']}")
    with harness.client() as client:
        stale_batch = _internal_post(client, harness.dotenv["KNOWFLOW_INTERNAL_SHARED_SECRET"],
                                     f"/internal/v1/tasks/{task_id}/index-batches", first["batch"])
        stale_completion = _internal_post(client, harness.dotenv["KNOWFLOW_INTERNAL_SHARED_SECRET"],
                                          f"/internal/v1/tasks/{task_id}/completion",
                                          _stale_success_completion(first))
    if (stale_batch.status_code != 409 or _error_code(stale_batch) != "LEASE_REJECTED"
            or stale_completion.status_code != 409 or _error_code(stale_completion) != "LEASE_REJECTED"):
        raise RuntimeError("STALE_EXECUTION_WAS_NOT_FENCED")
    active = _document_row(database_url, document_id)
    if (active["status"] != "ACTIVE" or active["active_index_version_id"] != completed["index_version_id"]
            or str(active["active_index_version_id"]) == first["lease"]["index_version_id"]):
        raise RuntimeError("RECOVERED_INDEX_NOT_ACTIVE")
    old_candidate = _wait_failed_candidate_cleanup(
        database_url, first["lease"]["index_version_id"], completed["index_version_id"])
    with harness.client(timeout=20) as client:
        answer = client.post(f"/api/v1/knowledge-bases/{base_id}/questions",
                             headers={"Authorization": f"Bearer {harness.token}"},
                             json={"question": "What does the evidence say?"})
    sources = answer.json().get("sources", []) if answer.status_code == 200 else []
    if not sources or sources[0].get("index_version_id") != str(completed["index_version_id"]):
        raise RuntimeError("RECOVERED_INDEX_NOT_QUERYABLE")
    cleanup = _wait_cleanup(database_url)
    return {"passed": True, "service": "postgres", "first_batch_persisted": True,
            "write_failed_during_outage": True, "old_active_preserved_during_outage": True,
            "first_fencing": first["lease"]["fencing"], "recovered_fencing": completed["fencing"],
            "stale_batch_rejected": True, "stale_completion_rejected": True,
            "stale_candidate_cleaned": old_candidate["cleaned"],
            "stale_candidate_chunk_rows": old_candidate["chunk_rows"],
            "stale_candidate_embedding_rows": old_candidate["embedding_rows"],
            "recovered_index_queryable": True, "cleanup_queues_drained": cleanup == {
                "unfinished_tasks": 0, "cleanup_queue_rows": 0}}


def run(args):
    if getattr(args, "isolated_outages", False) and _ISOLATED_COMPOSE is None:
        raise RuntimeError("OUTAGE_REQUIRES_OWN_ISOLATED_COMPOSE")
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=REPO, text=True).strip()
    if branch != "local":
        raise RuntimeError("RECOVERY_E2E_REQUIRES_LOCAL_BRANCH")
    code_status = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all", "--",
         "infra/compose.yml", "services/api", "services/ai/src",
         "services/ai/tools", "contracts/schemas"], cwd=REPO, text=True)
    if code_status.strip():
        raise RuntimeError("RECOVERY_CODE_INPUTS_DIRTY")
    head_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    subprocess.run(["git", "merge-base", "--is-ancestor", "main", "HEAD"],
                   cwd=REPO, check=True)
    base_commit = subprocess.check_output(
        ["git", "merge-base", "main", "HEAD"], cwd=REPO, text=True).strip()
    env_path = args.env_file.resolve()
    dotenv = local.read_env_file(env_path)
    for port in (8000, 8080):
        if not local.can_bind(port):
            raise RuntimeError(f"LOCAL_PORT_{port}_ALREADY_IN_USE")
    compose_started = _ensure_compose(env_path)

    run_id = uuid.uuid4().hex
    database_name = _database_name(args.database_prefix, run_id)
    database_created = False
    database_clean = False
    log = tempfile.TemporaryFile()
    harness = None
    secret_values = [value.encode("utf-8") for value in dotenv.values()
                     if isinstance(value, str) and len(value) >= 16]
    scenarios = {}
    failure = None
    try:
        _create_database(dotenv, database_name)
        database_created = True
        _bootstrap_database(dotenv, database_name)
        java_env, python_env, database_url = local.make_environment(
            dotenv, Path(tempfile.gettempdir()) / f"knowflow-recovery-{run_id}.marker",
            database_name)
        java_env.update({
            "SPRING_PROFILES_ACTIVE": "database,storage,db-migrate",
            "KNOWFLOW_DATABASE_MIGRATION_URL":
                f"jdbc:postgresql://127.0.0.1:55432/{database_name}",
            "KNOWFLOW_DATABASE_MIGRATION_USERNAME": "knowflow_migrator",
            "KNOWFLOW_DATABASE_MIGRATION_PASSWORD":
                dotenv["KNOWFLOW_DEV_MIGRATOR_PASSWORD"],
            "KNOWFLOW_INDEXING_LEASE_SECONDS": "5",
            "KNOWFLOW_INDEXING_HEARTBEAT_SECONDS": "1",
            "KNOWFLOW_INDEXING_MAX_ATTEMPTS": "3",
            "KNOWFLOW_INDEXING_POLL_DELAY_MILLIS": "250",
            "KNOWFLOW_INDEXING_MAX_BATCH_CHUNKS": "8",
            "KNOWFLOW_QUESTIONS_TOTAL_BUDGET_SECONDS": "3",
            "KNOWFLOW_QUESTION_RECOVERY_DELAY_MILLIS": "250",
        })
        secret_values.extend(value.encode("utf-8") for key, value in dotenv.items()
                             if key in {"KNOWFLOW_DEV_MIGRATOR_PASSWORD",
                                        "KNOWFLOW_DEV_POSTGRES_PASSWORD"})
        harness = RecoveryHarness(args, dotenv, database_name, database_url,
                                  java_env, python_env, log)
        harness.start_java()
        _wait_http_ready(harness.java_process, "http://127.0.0.1:8080",
                         "/actuator/health")
        harness.start_python(prefix="initial")
        local.require_idle_database(database_url)
        harness.create_owner()

        if getattr(args, "isolated_outages", False):
            scenarios["postgres_index_write_outage"] = _scenario_postgres_outage_during_index_write(harness)
            scenarios["postgres_outage"] = _scenario_service_outage(harness, "postgres")
            scenarios["minio_outage"] = _scenario_service_outage(harness, "minio")
            if not scenarios["minio_outage"]["passed"]:
                raise RuntimeError(scenarios["minio_outage"].get(
                    "failure_code", "MINIO_RECOVERY_ACCEPTANCE_FAILED"))
            scenarios["second_embedding_batch_failure"] = (
                _scenario_second_embedding_batch_failure(harness))
        else:
            scenarios["single_worker_restart"] = _scenario_worker_restarts(harness)
            scenarios["three_worker_losses"] = _scenario_retry_limit_preserves_active(harness)
            scenarios["second_embedding_batch_failure"] = _scenario_second_embedding_batch_failure(harness)
            scenarios["java_restart_question_recovery"] = (
                _scenario_java_restart_recovers_question(harness))
            scenarios["delete_while_worker_offline"] = (
                _scenario_delete_while_worker_offline(harness))

        harness.delete_knowledge_bases_and_wait()
        harness.logout()
        database_clean = True
    except Exception as error:
        failure = type(error).__name__ + ":" + (
            str(error) if isinstance(error, RuntimeError) else "RECOVERY_E2E_FAILED")
    finally:
        if harness is not None:
            try:
                harness.delete_knowledge_bases_and_wait()
                harness.logout()
                database_clean = True
            except Exception:
                database_clean = False
            harness.stop_python()
            harness.stop_java()
            shutil.rmtree(harness.marker_dir, ignore_errors=True)
        log.flush()
        log.seek(0)
        process_logs = log.read()
        secret_values.extend(value.encode("utf-8") for value in dotenv.values()
                             if isinstance(value, str) and len(value) >= 16)
        if harness is not None:
            secret_values.extend(value.encode("utf-8") for value in harness.sensitive_values)
        secret_in_logs = any(value in process_logs for value in secret_values)
        log.close()
        if database_created and database_clean:
            try:
                _drop_database(dotenv, database_name)
            except Exception:
                database_clean = False
        _stop_compose_services(env_path, compose_started)

    if database_created and not database_clean:
        failure = failure or "ISOLATED_DATABASE_CLEANUP_FAILED"
    if not all(local.can_bind(port) for port in (8000, 8080)):
        failure = failure or "LOCAL_SERVICE_PORT_STILL_IN_USE"
    if secret_in_logs:
        failure = failure or "LOCAL_SERVICE_SECRET_LOG_LEAK"
    schema = REPO / "contracts/schemas/protocol.schema.json"
    report = {
        "run_date": datetime.now(timezone.utc).date().isoformat(),
        "result": "DEVELOPMENT_PASS_SYNTHETIC_RECOVERY" if failure is None
                  and all(item.get("passed") for item in scenarios.values())
                  else "DEVELOPMENT_INCOMPLETE",
        "failure": failure,
        "branch": branch,
        "head_commit": head_commit,
        "base_commit": base_commit,
        "database_name": database_name,
        "database_dropped_after_cleanup": database_created and database_clean,
        "contract_version": CONTRACT_VERSION,
        "schema_sha256": sha256(schema.read_bytes()).hexdigest(),
        "scenarios": scenarios,
        "cleanup": {"isolated_database_created": database_created,
                    "isolated_database_clean": database_clean,
                    "services_ports_released": all(local.can_bind(port)
                                                   for port in (8000, 8080)),
                    "secret_in_process_logs": secret_in_logs},
        "model_calls": {"embedding_adapter": "local deterministic synthetic adapter",
                        "llm_adapter": "local deterministic synthetic adapter",
                        "external_model_calls": 0},
        "code_sha256": {
            "recovery_script": sha256(Path(__file__).read_bytes()).hexdigest(),
            "worker": sha256((AI_ROOT / "src/knowflow_ai/worker.py").read_bytes()).hexdigest(),
            "question_service": sha256((REPO / "services/api/src/main/java/com/knowflow/api/answer/QuestionService.java").read_bytes()).hexdigest(),
            "question_recovery_service": sha256((REPO / "services/api/src/main/java/com/knowflow/api/answer/QuestionRecoveryService.java").read_bytes()).hexdigest(),
            "source_read_service": sha256((REPO / "services/api/src/main/java/com/knowflow/api/indexing/SourceReadService.java").read_bytes()).hexdigest(),
        },
        "limitations": [
            "All model adapters were deterministic synthetic test implementations; no provider quality claim is made.",
            "The 40/20 candidate allocation remains public and is not a blind holdout.",
            "Independent Q review and M consumption confirmation remain pending.",
        ],
    }
    local.write_json(args.output, report)
    if report["result"] != "DEVELOPMENT_PASS_SYNTHETIC_RECOVERY":
        raise RuntimeError("RECOVERY_E2E_FAILED")
    print(f"local Java/Python/PostgreSQL/MinIO recovery E2E passed; evidence: {args.output}")


def _assert_isolation_available(project: str) -> None:
    if (not project.startswith("knowflow-outage-") or len(project) != 30
            or any(char not in "0123456789abcdef" for char in project[16:])):
        raise RuntimeError("ISOLATED_PROJECT_NAME_INVALID")
    checks = [
        ["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={project}"],
        ["docker", "network", "ls", "-q", "--filter", f"label=com.docker.compose.project={project}"],
    ]
    for command in checks:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        if result.returncode or result.stdout.strip():
            raise RuntimeError("ISOLATED_PROJECT_NOT_EMPTY")
    for suffix in ("postgres", "minio"):
        result = subprocess.run(["docker", "volume", "inspect", f"{project}-{suffix}"],
                                capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            raise RuntimeError("ISOLATED_VOLUME_ALREADY_EXISTS")


def run_isolated_outages(args):
    global _ISOLATED_COMPOSE
    if _ISOLATED_COMPOSE is not None:
        raise RuntimeError("ISOLATED_COMPOSE_ALREADY_ACTIVE")
    for port in (55432, 59000, 59001, 8000, 8080):
        if not local.can_bind(port):
            raise RuntimeError(f"LOCAL_PORT_{port}_ALREADY_IN_USE")
    project = f"knowflow-outage-{uuid.uuid4().hex[:14]}"
    _assert_isolation_available(project)
    with tempfile.TemporaryDirectory(prefix="knowflow-outage-config-") as directory:
        directory = Path(directory)
        override = directory / "override.yml"
        override.write_text(
            "volumes:\n  knowflow-api-dev-postgres:\n"
            f"    name: {project}-postgres\n  knowflow-api-dev-minio:\n"
            f"    name: {project}-minio\n", encoding="utf-8")
        env_path = directory / ".env"
        names = ("KNOWFLOW_DEV_POSTGRES_PASSWORD", "KNOWFLOW_DEV_MIGRATOR_PASSWORD",
                 "KNOWFLOW_DEV_APP_PASSWORD", "KNOWFLOW_DEV_AI_PASSWORD",
                 "KNOWFLOW_DEV_MINIO_ROOT_PASSWORD", "KNOWFLOW_INTERNAL_SHARED_SECRET")
        env_path.write_text("\n".join(f"{name}={secrets.token_hex(32)}" for name in names)
                            + "\nKNOWFLOW_DEV_MINIO_ROOT_USER=outageuser\n", encoding="utf-8")
        isolated_args = argparse.Namespace(**vars(args))
        isolated_args.env_file = env_path
        _ISOLATED_COMPOSE = (project, override)
        cleanup_ok = False
        try:
            run(isolated_args)
        finally:
            try:
                cleanup = _run_compose(env_path, ["down", "--volumes", "--remove-orphans"])
                cleanup_ok = cleanup.returncode == 0
            finally:
                _ISOLATED_COMPOSE = None
            if args.output.is_file():
                report = _read_json(args.output)
                report["isolation"] = {"compose_project": project,
                                       "exclusive_project_and_volumes": True,
                                       "compose_down_succeeded": cleanup_ok}
                _write_json(args.output, report)
            if not cleanup_ok:
                raise RuntimeError("ISOLATED_COMPOSE_CLEANUP_FAILED")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--env-file", type=Path, default=REPO / "services/api/.env")
    parser.add_argument("--maven-settings", type=Path)
    parser.add_argument("--database-prefix", default="knowflow_recovery")
    parser.add_argument("--isolated-outages", action="store_true",
                        help="Run database and object-storage outages in an owned Compose project")
    parser.add_argument("--output", type=Path,
                        default=AI_ROOT / f"docs/evidence/recovery-e2e-{CONTRACT_VERSION}.json")
    args = parser.parse_args()
    if args.serve:
        serve_python()
    elif args.isolated_outages:
        default_output = AI_ROOT / f"docs/evidence/recovery-e2e-{CONTRACT_VERSION}.json"
        if args.output == default_output or args.output.exists():
            parser.error("--isolated-outages requires a new, explicit --output path")
        run_isolated_outages(args)
    else:
        run(args)


if __name__ == "__main__":
    main()
