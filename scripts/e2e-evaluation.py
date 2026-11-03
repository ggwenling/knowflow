"""Exercise Java upload/index/answer and v2 collection with local fake providers."""
import argparse
import asyncio
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/ai/tools"))
import recovery_e2e as recovery


def load(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resource_counts(project):
    result = {}
    for kind, command in (("containers", ["ps", "-aq"]), ("networks", ["network", "ls", "-q"]),
                          ("volumes", ["volume", "ls", "-q"])):
        rows = subprocess.check_output(["docker", *command, "--filter", "label=com.docker.compose.project=" + project], text=True)
        result[kind] = len(rows.split())
    return result


def run(output):
    for port in (55432, 59000, 59001, 8000, 8080):
        if not recovery.local.can_bind(port):
            raise RuntimeError("EVALUATION_SMOKE_PORT_IN_USE")
    project = "knowflow-eval-" + uuid4().hex[:12]
    if any(resource_counts(project).values()):
        raise RuntimeError("EVALUATION_PROJECT_ALREADY_EXISTS")
    with tempfile.TemporaryDirectory(prefix="knowflow-eval-") as temp, tempfile.TemporaryFile() as log:
        temp = Path(temp)
        env_file = temp / ".env"
        values = {"KNOWFLOW_DEV_" + name: secrets.token_hex(32) for name in (
            "POSTGRES_PASSWORD", "MIGRATOR_PASSWORD", "APP_PASSWORD", "AI_PASSWORD", "MINIO_ROOT_PASSWORD")}
        values.update({"KNOWFLOW_DEV_MINIO_ROOT_USER": "evaluationtest",
                       "KNOWFLOW_INTERNAL_SHARED_SECRET": secrets.token_hex(32)})
        env_file.write_text("\n".join(key + "=" + value for key, value in values.items()), encoding="utf-8")
        compose_file = temp / "compose.yml"
        compose_text = (ROOT / "services/api/compose.dev.yml").read_text(encoding="utf-8")
        compose_text = compose_text.replace("knowflow-api-dev-postgres", project + "-postgres")
        compose_text = compose_text.replace("knowflow-api-dev-minio", project + "-minio")
        compose_file.write_text(compose_text, encoding="utf-8")
        compose = ["docker", "compose", "--project-name", project, "--project-directory", str(ROOT / "services/api"),
                   "-f", str(compose_file), "--env-file", str(env_file)]
        harness = None
        report = {"passed": False, "real_provider_calls": 0, "project": project}
        try:
            subprocess.run(compose + ["up", "-d", "--wait", "--wait-timeout", "120"],
                           stdout=log, stderr=log, check=True, timeout=150)
            java_env, python_env, database_url = recovery.local.make_environment(values, temp / "marker")
            java_env.update({"SPRING_PROFILES_ACTIVE": "database,storage,db-migrate",
                             "KNOWFLOW_DATABASE_MIGRATION_URL": "jdbc:postgresql://127.0.0.1:55432/knowflow",
                             "KNOWFLOW_DATABASE_MIGRATION_USERNAME": "knowflow_migrator",
                             "KNOWFLOW_DATABASE_MIGRATION_PASSWORD": values["KNOWFLOW_DEV_MIGRATOR_PASSWORD"]})
            python_env.update({"KNOWFLOW_BUDGET_LEDGER_PATH": str(temp / "budget.sqlite3"),
                               "KNOWFLOW_EVALUATION_CONTROL_SECRET": secrets.token_hex(32)})
            harness = recovery.RecoveryHarness(SimpleNamespace(maven_settings=None), values, "knowflow",
                                               database_url, java_env, python_env, log)
            harness.start_java()
            harness.python_process = subprocess.Popen(
                [sys.executable, str(ROOT / "evaluation/collector/fake_service.py")], cwd=ROOT,
                env=python_env, stdout=log, stderr=log)
            recovery.local.wait_ready(harness.python_process, "http://127.0.0.1:8000", "/health/live")
            harness.create_owner()
            collector = load(ROOT / "evaluation/collector/run.py")
            metadata = {"code_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                        "schema_sha256": sha256((ROOT / "contracts/schemas/protocol.schema.json").read_bytes()).hexdigest(),
                        "model": "fake", "config_sha256": sha256(b"fake-evaluation-smoke-v1").hexdigest(),
                        "prompt_sha256": sha256(b"fake-deterministic-answer-v1").hexdigest()}
            async def collect():
                from psycopg.rows import dict_row
                def query(sql, params):
                    with recovery.psycopg.connect(database_url, row_factory=dict_row) as db:
                        return db.execute(sql, params).fetchone()
                async def fetch(sql, params):
                    return await asyncio.to_thread(query, sql, params)
                async with collector.httpx.AsyncClient(base_url="http://127.0.0.1:8080", timeout=40, trust_env=False,
                        headers={"Authorization": "Bearer " + harness.token}) as java:
                    async with collector.httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=40, trust_env=False,
                            headers={"Authorization": "Bearer " + values["KNOWFLOW_INTERNAL_SHARED_SECRET"],
                                     "X-Evaluation-Secret": python_env["KNOWFLOW_EVALUATION_CONTROL_SECRET"]}) as ai:
                        return await collector.collect_dataset(java=java, ai=ai, dataset=ROOT / "evaluation/data/seed-v1",
                            split="development", output=temp / "predictions.json", run_metadata=metadata,
                            fetch_row=fetch, ledger=collector.BudgetLedger(temp / "budget.sqlite3"))
            payload = asyncio.run(collect())
            scorer = collector.scorer.evaluate(temp / "predictions.json", dataset_root=ROOT / "evaluation/data/seed-v1")
            recovery._wait_cleanup(database_url)
            harness.logout()
            report.update(passed=True, predictions=len(payload["predictions"]),
                          scorer_samples=scorer["sample_count"], fake_budget=collector.BudgetLedger(temp / "budget.sqlite3").summary())
        except Exception as error:
            report["failure_type"] = type(error).__name__
            # Logs contain only generated credentials, but keep even these local.
            report["failure_stage"] = "local_evaluation_smoke"
            raise
        finally:
            try:
                if harness is not None:
                    harness.stop_python()
                    harness.stop_java()
            finally:
                cleanup = subprocess.run(compose + ["down", "--volumes", "--remove-orphans"], stdout=log, stderr=log, timeout=120)
                report["cleanup_exit_code"] = cleanup.returncode
                report["remaining_resources"] = resource_counts(project)
                if cleanup.returncode or any(report["remaining_resources"].values()):
                    report["passed"] = False
                if harness is not None:
                    harness.marker_dir.rmdir()
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if not report["passed"]:
            raise RuntimeError("EVALUATION_SMOKE_FAILED")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        run(args.output)
    except Exception:
        print("EVALUATION_SMOKE_FAILED")
        raise SystemExit(1)
    print("EVALUATION_SMOKE_PASSED")
