"""Exercise worker and question recovery with real local services and synthetic models."""
import argparse
import asyncio
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
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


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8", newline="\n")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_compose(env_path: Path, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "compose", "-f", str(REPO / "services/api/compose.dev.yml"),
         "--env-file", str(env_path), *args],
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
    worker.SiliconFlowEmbeddingAdapter = local.SyntheticEmbedding

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

    def start_python(self, *, gate_fencings=(), prefix="worker", answer_marker=None):
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

    def upload_document(self, knowledge_base_id, filename):
        with self.client() as client:
            accepted = local.upload(client, self.token, knowledge_base_id,
                                    filename, DOCUMENT_TEXT)
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


def run(args):
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=REPO, text=True).strip()
    if branch != "local":
        raise RuntimeError("RECOVERY_E2E_REQUIRES_LOCAL_BRANCH")
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

        scenarios["single_worker_restart"] = _scenario_worker_restarts(harness)
        scenarios["three_worker_losses"] = _scenario_retry_limit_preserves_active(harness)
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--env-file", type=Path, default=REPO / "services/api/.env")
    parser.add_argument("--maven-settings", type=Path)
    parser.add_argument("--database-prefix", default="knowflow_recovery")
    parser.add_argument("--output", type=Path,
                        default=AI_ROOT / f"docs/evidence/recovery-e2e-draft{CONTRACT_VERSION.rsplit('.', 1)[1]}.json")
    args = parser.parse_args()
    if args.serve:
        serve_python()
    else:
        run(args)


if __name__ == "__main__":
    main()
