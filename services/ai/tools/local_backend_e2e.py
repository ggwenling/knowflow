"""Replay the local Java/Python indexing, answer, and cancellation flows."""
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
import time
from urllib.parse import quote, urlsplit
import uuid

import httpx
import psycopg


AI_ROOT = Path(__file__).resolve().parents[1]
REPO = AI_ROOT.parents[1]
VERSION = "0.2.0-draft.6"
BLOCK_MARKER = "KNOWFLOW_SYNTHETIC_BLOCK_FOR_CANCELLATION"


class SyntheticEmbedding:
    def __init__(self, *_args, **_kwargs):
        self.blocking = False

    async def embed(self, texts, *, request_id):
        if any(BLOCK_MARKER in text for text in texts):
            self.blocking = True
            record_event("started")
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                record_event("cancelled")
                raise
        return {
            "request_id": request_id,
            "model": "BAAI/bge-m3",
            "dimensions": 1024,
            "data": [{"index": i, "embedding": [0.125] * 1024}
                     for i, _ in enumerate(texts)],
        }

    async def aclose(self):
        if self.blocking:
            record_event("closed")


class SyntheticLlm:
    def __init__(self, *_args, **_kwargs):
        pass

    async def generate(self, question, evidence, *, request_id):
        source_id = evidence[0]["source_id"]
        return {"answer": f"Synthetic evidence verified. [{source_id}]",
                "has_answer": True, "source_ids": [source_id]}

    async def aclose(self):
        pass


def record_event(event: str) -> None:
    with Path(os.environ["KNOWFLOW_SYNTHETIC_STARTED_FILE"]).open("a", encoding="utf-8") as marker:
        marker.write(event + "\n")


def serve_python():
    import knowflow_ai.answering as answering
    import knowflow_ai.worker as worker

    answering.SiliconFlowEmbeddingAdapter = SyntheticEmbedding
    answering.DeepSeekAdapter = SyntheticLlm
    worker.SiliconFlowEmbeddingAdapter = SyntheticEmbedding
    original_cancel = worker.IndexWorker.cancel

    async def record_cancel(self, message):
        key = (message["task_id"], message["lease_id"], message["fencing"])
        if key in self._active and Path(os.environ["KNOWFLOW_SYNTHETIC_STARTED_FILE"]).exists():
            record_event("cancel_requested")
        await original_cancel(self, message)

    worker.IndexWorker.cancel = record_cancel
    from knowflow_ai.app import create_app
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=8000,
                log_level="warning", access_log=False)


def read_env_file(path: Path) -> dict[str, str]:
    values = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def require_local_url(value: str, name: str, scheme: str | None = None) -> None:
    parsed = urlsplit(value.replace("jdbc:", "", 1))
    if parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise RuntimeError(f"{name}_MUST_BE_LOOPBACK")
    if scheme and parsed.scheme != scheme:
        raise RuntimeError(f"{name}_SCHEME_INVALID")


def can_bind(port: int) -> bool:
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def wait_ready(process: subprocess.Popen, url: str, path: str) -> None:
    with httpx.Client(timeout=1, trust_env=False) as client:
        for _ in range(180):
            if process.poll() is not None:
                raise RuntimeError("LOCAL_SERVICE_EXITED_DURING_STARTUP")
            try:
                response = client.get(url + path)
                if response.status_code == 200:
                    return
            except httpx.TransportError:
                pass
            time.sleep(0.25)
    raise RuntimeError("LOCAL_SERVICE_START_TIMEOUT")


def wait_task(client: httpx.Client, token: str, task_id: str,
              target: str, timeout: int = 150) -> dict:
    headers = {"Authorization": f"Bearer {token}"}
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        task = client.get(f"/api/v1/tasks/{task_id}", headers=headers).json()
        if task["status"] == target:
            return task
        if task["status"] in {"FAILED", "CANCELLED"}:
            raise RuntimeError(f"INDEX_TASK_{task['status']}")
        time.sleep(0.4)
    raise RuntimeError(f"INDEX_TASK_DID_NOT_REACH_{target}")


def stop(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    if os.name == "nt":
        command = ["taskkill", "/PID", str(process.pid), "/T", "/F"]
        result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode and process.poll() is None:
            raise subprocess.CalledProcessError(result.returncode, command)
    else:
        process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def make_environment(dotenv: dict[str, str], marker_file: Path) -> tuple[dict, dict, str]:
    required = (
        "KNOWFLOW_DEV_APP_PASSWORD", "KNOWFLOW_DEV_AI_PASSWORD",
        "KNOWFLOW_DEV_MINIO_ROOT_USER", "KNOWFLOW_DEV_MINIO_ROOT_PASSWORD",
        "KNOWFLOW_INTERNAL_SHARED_SECRET",
    )
    if any(not dotenv.get(key) for key in required):
        raise RuntimeError("LOCAL_DEV_ENV_MISSING_REQUIRED_VALUE")
    secret = dotenv["KNOWFLOW_INTERNAL_SHARED_SECRET"]
    if not 32 <= len(secret) <= 256:
        raise RuntimeError("LOCAL_DEV_INTERNAL_SECRET_INVALID")

    database_url = "jdbc:postgresql://127.0.0.1:55432/knowflow"
    storage_url = "http://127.0.0.1:59000"
    java_env = os.environ.copy()
    java_env.update({
        "SPRING_PROFILES_ACTIVE": "database,storage",
        "KNOWFLOW_DATABASE_URL": database_url,
        "KNOWFLOW_DATABASE_USERNAME": "knowflow_app",
        "KNOWFLOW_DATABASE_PASSWORD": dotenv["KNOWFLOW_DEV_APP_PASSWORD"],
        "KNOWFLOW_STORAGE_ENDPOINT": storage_url,
        "KNOWFLOW_STORAGE_BUCKET": "knowflow-documents",
        "KNOWFLOW_STORAGE_ACCESS_KEY": dotenv["KNOWFLOW_DEV_MINIO_ROOT_USER"],
        "KNOWFLOW_STORAGE_SECRET_KEY": dotenv["KNOWFLOW_DEV_MINIO_ROOT_PASSWORD"],
        "KNOWFLOW_AI_BASE_URL": "http://127.0.0.1:8000",
        "KNOWFLOW_INTERNAL_SHARED_SECRET": secret,
        "KNOWFLOW_INDEXING_SCHEDULER_ENABLED": "true",
        "KNOWFLOW_INDEXING_POLL_DELAY_MILLIS": "250",
        "NO_PROXY": "127.0.0.1,localhost",
        "no_proxy": "127.0.0.1,localhost",
    })
    ai_password = quote(dotenv["KNOWFLOW_DEV_AI_PASSWORD"], safe="")
    app_password = quote(dotenv["KNOWFLOW_DEV_APP_PASSWORD"], safe="")
    application_database_url = (
        f"postgresql://knowflow_app:{app_password}@127.0.0.1:55432/knowflow")
    python_env = os.environ.copy()
    python_env.update({
        "KNOWFLOW_INTERNAL_SHARED_SECRET": secret,
        "KNOWFLOW_JAVA_BASE_URL": "http://127.0.0.1:8080",
        "KNOWFLOW_CONTRACT_PATH": str(REPO / "contracts/schemas/protocol.schema.json"),
        "KNOWFLOW_AI_DATABASE_URL":
            f"postgresql://knowflow_ai:{ai_password}@127.0.0.1:55432/knowflow",
        "KNOWFLOW_EMBEDDING_KEY_ENV": "EMBEDING_KEY",
        "KNOWFLOW_LLM_KEY_ENV": "DEEPSEEK_API_KEY",
        "KNOWFLOW_EMBEDDING_BASE_URL": "https://api.siliconflow.cn/v1",
        "KNOWFLOW_LLM_BASE_URL": "https://api.deepseek.com",
        "EMBEDING_KEY": "synthetic-local-key-" + "x" * 32,
        "DEEPSEEK_API_KEY": "synthetic-local-key-" + "x" * 32,
        "KNOWFLOW_SYNTHETIC_STARTED_FILE": str(marker_file),
        "NO_PROXY": "127.0.0.1,localhost",
        "no_proxy": "127.0.0.1,localhost",
    })
    require_local_url(database_url, "JAVA_DATABASE_URL", "postgresql")
    require_local_url(python_env["KNOWFLOW_AI_DATABASE_URL"], "AI_DATABASE_URL", "postgresql")
    return java_env, python_env, application_database_url


def upload(client: httpx.Client, token: str, knowledge_base_id: str,
           filename: str, text: str) -> dict:
    response = client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": (filename, text.encode("utf-8"), "text/plain")},
    )
    if response.status_code != 202:
        raise RuntimeError(f"UPLOAD_FAILED_{response.status_code}")
    return response.json()


def db_counts(database_url: str, document_id: str, task_id: str) -> dict:
    with psycopg.connect(database_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT status FROM knowflow.indexing_tasks WHERE id = %s",
                           (task_id,))
            task_status = cursor.fetchone()[0]
            cursor.execute("SELECT count(*) FROM knowflow.chunks WHERE document_id = %s",
                           (document_id,))
            chunks = cursor.fetchone()[0]
            cursor.execute("SELECT count(*) FROM knowflow.chunk_embeddings WHERE document_id = %s",
                           (document_id,))
            embeddings = cursor.fetchone()[0]
            cursor.execute("SELECT count(*) FROM knowflow.execution_cancellation_queue WHERE task_id = %s",
                           (task_id,))
            cancels = cursor.fetchone()[0]
            cursor.execute("""
                SELECT count(*) FROM knowflow.storage_cleanup_queue q
                JOIN knowflow.content_versions c ON c.object_key = q.object_key
                WHERE c.document_id = %s
            """, (document_id,))
            storage = cursor.fetchone()[0]
            cursor.execute("""
                SELECT count(*) FROM knowflow.index_cleanup_queue q
                JOIN knowflow.index_versions i ON i.id = q.index_version_id
                WHERE i.document_id = %s
            """, (document_id,))
            indexes = cursor.fetchone()[0]
    return {"task_status": task_status, "chunk_rows": chunks, "embedding_rows": embeddings,
            "cancellation_outbox_rows": cancels, "storage_outbox_rows": storage,
            "index_outbox_rows": indexes}


def wait_cancelled(database_url: str, task_id: str, timeout: int = 60) -> None:
    deadline = time.monotonic() + timeout
    with psycopg.connect(database_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            while time.monotonic() < deadline:
                cursor.execute("SELECT status FROM knowflow.indexing_tasks WHERE id = %s",
                               (task_id,))
                row = cursor.fetchone()
                if row and row[0] == "CANCELLED":
                    return
                if row and row[0] in {"FAILED", "SUCCEEDED"}:
                    raise RuntimeError(f"CANCEL_TASK_FINISHED_{row[0]}")
                time.sleep(0.2)
    raise RuntimeError("CANCEL_TASK_DID_NOT_REACH_CANCELLED")


def require_idle_database(database_url: str) -> None:
    with psycopg.connect(database_url) as connection:
        unfinished, cleanup = connection.execute("""
            SELECT (SELECT count(*) FROM knowflow.indexing_tasks WHERE status IN ('QUEUED', 'RUNNING')),
                   (SELECT count(*) FROM knowflow.execution_cancellation_queue)
                 + (SELECT count(*) FROM knowflow.storage_cleanup_queue)
                 + (SELECT count(*) FROM knowflow.index_cleanup_queue)
        """).fetchone()
    if unfinished:
        raise RuntimeError("LOCAL_DATABASE_HAS_UNFINISHED_INDEX_TASKS")
    if cleanup:
        raise RuntimeError("LOCAL_DATABASE_HAS_PENDING_CLEANUP")


def wait_document_cleanup(database_url: str, document_id: str, task_id: str,
                          timeout: int = 60) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        counts = db_counts(database_url, document_id, task_id)
        if all(counts[key] == 0 for key in ("chunk_rows", "embedding_rows",
                                             "cancellation_outbox_rows", "storage_outbox_rows",
                                             "index_outbox_rows")):
            return counts
        time.sleep(0.1)
    raise RuntimeError("SYNTHETIC_DOCUMENT_CLEANUP_INCOMPLETE")


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(args) -> None:
    env_path = args.env_file.resolve()
    dotenv = read_env_file(env_path)
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=REPO, text=True).strip()
    if branch != "local":
        raise RuntimeError("EXPECTED_LOCAL_BRANCH")
    subprocess.run(["git", "merge-base", "--is-ancestor", "main", "HEAD"],
                   cwd=REPO, check=True)
    base_commit = subprocess.check_output(["git", "merge-base", "main", "HEAD"], cwd=REPO, text=True).strip()
    for port in (8000, 8080):
        if not can_bind(port):
            raise RuntimeError(f"LOCAL_PORT_{port}_ALREADY_IN_USE")
    compose = subprocess.run(
        ["docker", "compose", "-f", str(REPO / "services/api/compose.dev.yml"),
         "--env-file", str(env_path), "ps", "--format", "json"],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=20)
    containers = [json.loads(line) for line in compose.stdout.splitlines() if line.strip()]
    health = {container["Service"]: container["Health"] for container in containers}
    if compose.returncode or any(health.get(service) != "healthy" for service in ("postgres", "minio")):
        raise RuntimeError("LOCAL_POSTGRES_MINIO_NOT_HEALTHY")

    marker_file = Path(tempfile.gettempdir()) / f"knowflow-e2e-{uuid.uuid4().hex}.marker"
    java_env, python_env, application_database_url = make_environment(dotenv, marker_file)
    require_idle_database(application_database_url)
    java_log = None
    python_log = None
    java_process = None
    python_process = None
    log_data = []
    token = None
    log_sensitive = [value for value in dotenv.values() if len(value) >= 16]
    knowledge_base_id = None
    run_id = uuid.uuid4().hex
    smoke = {"registered_owner": False, "knowledge_base_created": False,
             "authenticated_upload": False, "index_dispatched": False,
             "document_ready": False, "read_only_retrieval": False,
             "synthetic_answer_and_source": False, "synthetic_cancellation": False,
             "active_cancel_delivered_and_adapter_closed": False,
             "no_late_chunk_or_embedding": False, "knowledge_base_deleted": False,
             "document_cleanup_queues_drained": False,
             "session_logged_out": False}
    java_log = tempfile.TemporaryFile()
    python_log = tempfile.TemporaryFile()
    try:
        python_process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--serve"],
            cwd=REPO, env=python_env, stdout=python_log, stderr=python_log)
        wait_ready(python_process, "http://127.0.0.1:8000", "/health/live")

        wrapper = REPO / "services/api/mvnw.cmd" if os.name == "nt" else REPO / "services/api/mvnw"
        package = (["cmd.exe", "/d", "/c", str(wrapper), "-B", "-q", "-DskipTests", "package"]
                   if os.name == "nt" else [str(wrapper), "-B", "-q", "-DskipTests", "package"])
        if args.maven_settings:
            package.extend(["-s", str(args.maven_settings.resolve())])
        build = subprocess.run(package, cwd=REPO / "services/api", env=java_env,
                               stdout=java_log, stderr=java_log, timeout=300)
        if build.returncode:
            raise RuntimeError("JAVA_PACKAGE_FAILED")
        jar = REPO / "services/api/target/knowflow-api-0.2.0-SNAPSHOT.jar"
        java = shutil.which("java")
        if not jar.is_file() or java is None:
            raise RuntimeError("JAVA_RUNTIME_OR_PACKAGE_MISSING")
        java_process = subprocess.Popen(
            [java, "-jar", str(jar)], cwd=REPO, env=java_env,
            stdout=java_log, stderr=java_log)
        wait_ready(java_process, "http://127.0.0.1:8080", "/actuator/health")

        with httpx.Client(base_url="http://127.0.0.1:8080", timeout=15,
                          trust_env=False) as client:
            email = f"local-e2e-{run_id}@example.test"
            password = f"Local-E2E-{run_id[:24]}-Pass"
            log_sensitive.append(password)
            response = client.post("/api/v1/auth/register", json={
                "contract_version": VERSION, "email": email, "password": password})
            if response.status_code != 201:
                raise RuntimeError(f"REGISTER_FAILED_{response.status_code}")
            token = response.json()["access_token"]
            log_sensitive.append(token)
            smoke["registered_owner"] = True
            headers = {"Authorization": f"Bearer {token}"}
            response = client.post("/api/v1/knowledge-bases", headers=headers,
                                   json={"contract_version": VERSION,
                                         "name": f"Local synthetic {run_id[:8]}"})
            if response.status_code != 201:
                raise RuntimeError(f"KNOWLEDGE_BASE_CREATE_FAILED_{response.status_code}")
            knowledge_base_id = response.json()["id"]
            smoke["knowledge_base_created"] = True

            result = upload(client, token, knowledge_base_id, "synthetic-e2e.txt",
                            "Synthetic evidence states that local cross-service indexing works.")
            smoke["authenticated_upload"] = True
            task_id, document_id = result["task_id"], result["document_id"]
            smoke["index_dispatched"] = True
            wait_task(client, token, task_id, "SUCCEEDED")
            document = client.get(f"/api/v1/documents/{document_id}", headers=headers).json()
            if document["status"] != "READY" or not document.get("active_index_version_id"):
                raise RuntimeError("DOCUMENT_NOT_READY")
            smoke["document_ready"] = True

            answer = client.post(
                f"/api/v1/knowledge-bases/{knowledge_base_id}/questions",
                headers=headers, json={"question": "What does the synthetic evidence verify?"})
            if answer.status_code != 200:
                raise RuntimeError(f"QUESTION_FAILED_{answer.status_code}")
            answer_data = answer.json()
            if (not answer_data.get("has_answer") or not answer_data.get("sources")
                    or "Synthetic evidence verified" not in answer_data.get("answer", "")
                    or "local cross-service indexing works" not in answer_data["sources"][0].get("quote", "")):
                raise RuntimeError("ANSWER_SOURCE_VALIDATION_FAILED")
            smoke["read_only_retrieval"] = True
            smoke["synthetic_answer_and_source"] = True

            result = upload(client, token, knowledge_base_id, "synthetic-cancel.txt",
                            f"{BLOCK_MARKER} This active embedding must be cancelled.")
            cancel_task, cancel_doc = result["task_id"], result["document_id"]
            marker_deadline = time.monotonic() + 60
            while time.monotonic() < marker_deadline and not marker_file.exists():
                if python_process.poll() is not None:
                    raise RuntimeError("PYTHON_PROCESS_EXITED_DURING_CANCEL_TEST")
                time.sleep(0.1)
            if not marker_file.exists():
                raise RuntimeError("SYNTHETIC_EMBEDDING_DID_NOT_START")
            deleted = client.delete(f"/api/v1/documents/{cancel_doc}", headers=headers)
            if deleted.status_code != 204:
                raise RuntimeError(f"CANCEL_DOCUMENT_DELETE_FAILED_{deleted.status_code}")
            wait_cancelled(application_database_url, cancel_task, timeout=60)
            smoke["synthetic_cancellation"] = True
            expected_events = ["started", "cancel_requested", "cancelled", "closed"]
            cancel_deadline = time.monotonic() + 60
            while time.monotonic() < cancel_deadline:
                events = marker_file.read_text(encoding="utf-8").splitlines()
                cancel_counts = db_counts(application_database_url, cancel_doc, cancel_task)
                if events == expected_events and cancel_counts["cancellation_outbox_rows"] == 0:
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError("ACTIVE_CANCELLATION_NOT_DELIVERED_AND_CLOSED")
            smoke["active_cancel_delivered_and_adapter_closed"] = True
            time.sleep(1)
            cancel_counts = db_counts(application_database_url, cancel_doc, cancel_task)
            smoke["no_late_chunk_or_embedding"] = (
                cancel_counts["task_status"] == "CANCELLED"
                and cancel_counts["chunk_rows"] == 0
                and cancel_counts["embedding_rows"] == 0
                and cancel_counts["cancellation_outbox_rows"] == 0)
            if not smoke["no_late_chunk_or_embedding"]:
                raise RuntimeError("CANCELLATION_LEFT_LATE_WRITES_OR_OUTBOX")

            response = client.delete(f"/api/v1/knowledge-bases/{knowledge_base_id}",
                                     headers=headers)
            if response.status_code != 204:
                raise RuntimeError(f"KNOWLEDGE_BASE_DELETE_FAILED_{response.status_code}")
            knowledge_base_id = None
            smoke["knowledge_base_deleted"] = True
            cleanup_counts = {
                "indexed_document": wait_document_cleanup(application_database_url, document_id, task_id),
                "cancelled_document": wait_document_cleanup(application_database_url, cancel_doc, cancel_task),
            }
            smoke["document_cleanup_queues_drained"] = True
            response = client.post("/api/v1/auth/logout", headers=headers)
            if response.status_code != 204:
                raise RuntimeError(f"SESSION_LOGOUT_FAILED_{response.status_code}")
            token = None
            smoke["session_logged_out"] = True

        result = "DEVELOPMENT_PASS_SYNTHETIC_ADAPTERS" if all(smoke.values()) else "DEVELOPMENT_INCOMPLETE"
    finally:
        if token or knowledge_base_id:
            try:
                with httpx.Client(base_url="http://127.0.0.1:8080", timeout=5,
                                  trust_env=False) as cleanup:
                    if token and knowledge_base_id:
                        cleanup.delete(f"/api/v1/knowledge-bases/{knowledge_base_id}",
                                       headers={"Authorization": f"Bearer {token}"})
                    if token:
                        cleanup.post("/api/v1/auth/logout",
                                     headers={"Authorization": f"Bearer {token}"})
            except httpx.HTTPError:
                pass
        stop(java_process)
        stop(python_process)
        for log in (java_log, python_log):
            if log:
                log.flush()
                log.seek(0)
                log_data.append(log.read())
        marker_file.unlink(missing_ok=True)
        if java_log:
            java_log.close()
        if python_log:
            python_log.close()

    if not all(can_bind(port) for port in (8000, 8080)):
        raise RuntimeError("LOCAL_SERVICE_PORT_STILL_IN_USE")
    secret_values = [value.encode("utf-8") for value in log_sensitive]
    secret_in_logs = any(value in data for value in secret_values for data in log_data)
    if secret_in_logs:
        raise RuntimeError("LOCAL_SERVICE_SECRET_LOG_LEAK")
    schema = REPO / "contracts/schemas/protocol.schema.json"
    code_hashes = {
        "replay_script": sha256(Path(__file__).read_bytes()).hexdigest(),
        "python_worker": sha256((AI_ROOT / "src/knowflow_ai/worker.py").read_bytes()).hexdigest(),
        "python_cancel_route": sha256((AI_ROOT / "src/knowflow_ai/app.py").read_bytes()).hexdigest(),
        "java_deletion_outbox": sha256((REPO / "services/api/src/main/java/com/knowflow/api/document/DeletionOutboxScheduler.java").read_bytes()).hexdigest(),
    }
    write_json(args.output, {
        "run_date": datetime.now(timezone.utc).date().isoformat(),
        "result": result,
        "branch": branch,
        "base_commit": base_commit,
        "contract_version": VERSION,
        "schema_sha256": sha256(schema.read_bytes()).hexdigest(),
        "runtime": {"java": "local Spring Boot service with database/storage profiles",
                    "python": "local synthetic-adapter Uvicorn process",
                    "database": "local PostgreSQL with pgvector 0.8.1",
                    "object_storage": "local MinIO"},
        "flow": smoke,
        "cancellation_database_after_cancel": cancel_counts,
        "document_cleanup_after_knowledge_base_delete": cleanup_counts,
        "model_calls": {"embedding_adapter": "local deterministic synthetic adapter",
                        "llm_adapter": "local deterministic synthetic adapter",
                        "external_model_calls": 0},
        "secret_in_process_logs": secret_in_logs,
        "code_sha256": code_hashes,
        "limitations": ["Real SiliconFlow/DeepSeek model calls were not performed.",
                        "Synthetic owner accounts remain in the local development database; sessions are logged out and knowledge bases are deleted.",
                        "Q review and M consumption confirmation remain pending."],
    })
    if result != "DEVELOPMENT_PASS_SYNTHETIC_ADAPTERS":
        raise RuntimeError("LOCAL_E2E_INCOMPLETE")
    print(f"local Java/Python/PostgreSQL/MinIO E2E passed; evidence: {args.output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--env-file", type=Path, default=REPO / "services/api/.env")
    parser.add_argument("--maven-settings", type=Path)
    parser.add_argument("--output", type=Path,
                        default=AI_ROOT / "docs/evidence/local-backend-e2e-draft6-replay.json")
    args = parser.parse_args()
    if args.serve:
        serve_python()
    else:
        run(args)


if __name__ == "__main__":
    main()
