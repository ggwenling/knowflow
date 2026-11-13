"""Exercise Java upload/index/answer and v2 collection with local fake providers."""
import argparse
import asyncio
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import secrets
import socket
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


def assert_fake_evaluation_success(payload, scorer_result, expected_samples):
    """Require completed QA rows and the deterministic fake's answer/citation contract."""
    predictions = payload.get("predictions") if isinstance(payload, dict) else None
    if not isinstance(predictions, list) or len(predictions) != expected_samples:
        raise RuntimeError("EVALUATION_SAMPLE_COUNT_MISMATCH")
    metrics = scorer_result.get("metrics", {})
    if (scorer_result.get("sample_count") != expected_samples
            or metrics.get("execution_error_count") != 0):
        raise RuntimeError("EVALUATION_EXECUTION_ERRORS")
    for row in predictions:
        citations = row.get("citations") if isinstance(row, dict) else None
        if (row.get("outcome") != "answered" or not isinstance(citations, list)
                or len(citations) != 1 or not isinstance(citations[0].get("source_id"), str)
                or row.get("answer") != "Synthetic answer [" + citations[0]["source_id"] + "]"
                or not any(item.get("source_id") == citations[0]["source_id"]
                           for item in row.get("retrieved_evidence", []))):
            raise RuntimeError("DETERMINISTIC_FAKE_ANSWER_MISMATCH")


def run(output, real_split=None, *, offline_quality=False):
    quality = real_split or offline_quality
    if real_split and any(not os.environ.get(name) for name in (
            "KNOWFLOW_LLM_API_KEY", "KNOWFLOW_EMBEDDING_API_KEY", "KNOWFLOW_BUDGET_PRICE_FILE",
            "KNOWFLOW_BUDGET_POLICY_FILE")):
        raise RuntimeError("REAL_EVALUATION_CONFIGURATION_REQUIRED")
    listeners = [socket.socket() for _ in range(5)]
    try:
        for listener in listeners:
            listener.bind(("127.0.0.1", 0))
        postgres, minio, console, ai_port, java_port = [listener.getsockname()[1] for listener in listeners]
    finally:
        for listener in listeners:
            listener.close()
    ai_url, java_url = f"http://127.0.0.1:{ai_port}", f"http://127.0.0.1:{java_port}"
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
        for old, port in ((55432, postgres), (59000, minio), (59001, console)):
            compose_text = compose_text.replace(f"127.0.0.1:{old}:", f"127.0.0.1:{port}:")
        compose_file.write_text(compose_text, encoding="utf-8")
        compose = ["docker", "compose", "--project-name", project, "--project-directory", str(ROOT / "services/api"),
                   "-f", str(compose_file), "--env-file", str(env_file)]
        harness = None
        report = {"passed": False, "real_provider_calls": 0, "project": project}
        try:
            subprocess.run(compose + ["up", "-d", "--wait", "--wait-timeout", "120"],
                           stdout=log, stderr=log, check=True, timeout=150)
            java_env, python_env, database_url = recovery.local.make_environment(values, temp / "marker")
            database_url = database_url.replace(":55432/", f":{postgres}/")
            java_env.update({"SPRING_PROFILES_ACTIVE": "database,storage,db-migrate",
                             "SERVER_PORT": str(java_port), "KNOWFLOW_AI_BASE_URL": ai_url,
                             "KNOWFLOW_STORAGE_ENDPOINT": f"http://127.0.0.1:{minio}",
                             "KNOWFLOW_DATABASE_URL": f"jdbc:postgresql://127.0.0.1:{postgres}/knowflow",
                             "KNOWFLOW_DATABASE_MIGRATION_URL": f"jdbc:postgresql://127.0.0.1:{postgres}/knowflow",
                             "KNOWFLOW_DATABASE_MIGRATION_USERNAME": "knowflow_migrator",
                             "KNOWFLOW_DATABASE_MIGRATION_PASSWORD": values["KNOWFLOW_DEV_MIGRATOR_PASSWORD"]})
            python_env.update({"KNOWFLOW_BUDGET_LEDGER_PATH": str(temp / "budget.sqlite3"),
                               "KNOWFLOW_EVALUATION_AI_PORT": str(ai_port), "KNOWFLOW_JAVA_BASE_URL": java_url,
                               "KNOWFLOW_AI_DATABASE_URL": python_env["KNOWFLOW_AI_DATABASE_URL"].replace(
                                   ":55432/", f":{postgres}/"),
                               "KNOWFLOW_EVALUATION_CONTROL_SECRET": secrets.token_hex(32)})
            if real_split:
                python_env.update({"KNOWFLOW_EMBEDDING_KEY_ENV": "KNOWFLOW_EMBEDDING_API_KEY",
                                   "KNOWFLOW_LLM_KEY_ENV": "KNOWFLOW_LLM_API_KEY",
                                   "KNOWFLOW_LLM_MODEL": "deepseek-flash",
                                   "KNOWFLOW_EMBEDDING_MODEL": "BAAI/bge-m3",
                                   "KNOWFLOW_EMBEDDING_DIMENSIONS": "1024"})
            if offline_quality:
                python_env["KNOWFLOW_OFFLINE_QUALITY"] = "1"
            harness = recovery.RecoveryHarness(SimpleNamespace(maven_settings=None), values, "knowflow",
                                               database_url, java_env, python_env, log)
            harness.start_java()
            harness.python_process = subprocess.Popen(
                [sys.executable, str(ROOT / "evaluation/collector" /
                                     ("quality_service.py" if quality else "fake_service.py"))], cwd=ROOT,
                env=python_env, stdout=log, stderr=log)
            recovery.local.wait_ready(harness.python_process, ai_url, "/health/live")
            harness.create_owner()
            collector = load(ROOT / "evaluation/collector/run.py")
            metadata = {"code_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                        "schema_sha256": sha256((ROOT / "contracts/schemas/protocol.schema.json").read_bytes()).hexdigest(),
                        "model": "fake", "config_sha256": sha256(b"fake-evaluation-smoke-v1").hexdigest(),
                        "prompt_sha256": sha256(b"fake-deterministic-answer-v1").hexdigest()}
            dataset = ROOT / "evaluation/data" / ("seed-v2-reviewed" if quality else "seed-v1")
            predictions = output.with_suffix(".predictions.json") if quality else temp / "predictions.json"
            split = real_split or ("holdout" if offline_quality else "development")
            if real_split:
                ai_source = ROOT / "services/ai/src/knowflow_ai"
                metadata.update(model="deepseek-flash",
                                config_sha256=sha256(b"deepseek-flash|BAAI/bge-m3|sse|serial").hexdigest(),
                                prompt_sha256=sha256(b"".join((ai_source / name).read_bytes() for name in
                                    ("answering.py", "langchain_answer.py", "streaming.py"))).hexdigest())
            async def collect():
                from psycopg.rows import dict_row
                def query(sql, params):
                    with recovery.psycopg.connect(database_url, row_factory=dict_row) as db:
                        return db.execute(sql, params).fetchone()
                async def fetch(sql, params):
                    return await asyncio.to_thread(query, sql, params)
                async with collector.httpx.AsyncClient(base_url=java_url, timeout=40, trust_env=False,
                        headers={"Authorization": "Bearer " + harness.token}) as java:
                    async with collector.httpx.AsyncClient(base_url=ai_url, timeout=40, trust_env=False,
                            headers={"Authorization": "Bearer " + values["KNOWFLOW_INTERNAL_SHARED_SECRET"],
                                     "X-Evaluation-Secret": python_env["KNOWFLOW_EVALUATION_CONTROL_SECRET"]}) as ai:
                        return await collector.collect_dataset(java=java, ai=ai, dataset=dataset,
                            split=split, output=predictions, run_metadata=metadata,
                            fetch_row=fetch, ledger=collector.BudgetLedger(temp / "budget.sqlite3"),
                            streaming=bool(quality))
            payload = asyncio.run(collect())
            if quality:
                scorer = load(ROOT / "evaluation/runner/runner_v2.py")
                scored = scorer.evaluate(predictions, dataset_root=dataset, split=split, allow_followup=bool(real_split))
                if scored["metrics"]["execution_error_count"] or scored["sample_count"] != (20 if split == "holdout" else 40):
                    raise RuntimeError("REAL_EVALUATION_INCOMPLETE")
                metrics = scored["metrics"]
                report.update(metrics=metrics, run=metadata)
                if offline_quality:
                    for metric, minimum in {"recall_at_5": .85, "mrr_at_10": .75,
                            "cited_gold_span_overlap_rate": .96, "unanswerable_refusal_rate": 1,
                            "answerable_answer_rate": .90}.items():
                        if metrics[metric] is None or metrics[metric] < minimum:
                            raise RuntimeError("OFFLINE_QUALITY_GATE_FAILED:" + metric)
                else:
                    review = scorer.prepare_review(predictions, dataset, split, allow_followup=True)
                    output.with_suffix(".review.json").write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
                    report["real_provider_calls"] = None
            else:
                scorer = collector.scorer.evaluate(predictions, dataset_root=dataset)
                _manifest, expected_questions, _documents, _sources, _fingerprint = collector.scorer._load_dataset(dataset)
                expected_samples = sum(question["split"] == split for question in expected_questions)
                assert_fake_evaluation_success(payload, scorer, expected_samples)
                report.update(scorer_samples=scorer["sample_count"])
            recovery._wait_cleanup(database_url)
            harness.logout()
            report.update(passed=True, predictions=len(payload["predictions"]),
                          budget=collector.BudgetLedger(temp / "budget.sqlite3").summary())
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
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--real-split", choices=("development", "holdout"))
    modes.add_argument("--offline-quality", action="store_true")
    args = parser.parse_args()
    try:
        run(args.output, args.real_split, offline_quality=args.offline_quality)
    except Exception as error:
        print("EVALUATION_SMOKE_FAILED:", type(error).__name__,
              str(error) if str(error).startswith(("OFFLINE_QUALITY_GATE_FAILED:", "REAL_EVALUATION_")) else "")
        raise SystemExit(1)
    print("EVALUATION_SMOKE_PASSED")
