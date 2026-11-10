"""Collect dataset predictions through Java and the authenticated evaluation service."""
import argparse
import asyncio
from hashlib import sha256
import importlib.util
import json
import os
import re
from pathlib import Path
import time
from urllib.parse import urlsplit

import httpx
import psycopg
from psycopg.rows import dict_row
from knowflow_ai.budget import BudgetLedger, SOFT_STOP_MICROYUAN
from knowflow_ai.protocol import CONTRACT_VERSION


ROOT = Path(__file__).resolve().parents[2]


def load(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


scorer = load(ROOT / "evaluation/runner/runner.py")
collector = load(Path(__file__).with_name("collect.py"))


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


async def _cleanup_knowledge_base(java, knowledge_base_id, output, status):
    """Delete the temporary knowledge base without masking an earlier failure."""
    try:
        deleted = await java.delete("/api/v1/knowledge-bases/" + knowledge_base_id)
        failed = deleted.status_code != 204
    except httpx.HTTPError:
        failed = True
    if failed:
        status["complete"] = False
        status["failures"].append({"code": "EVALUATION_CLEANUP_FAILED"})
        try:
            write_json(output.with_suffix(".status.json"), status)
        except OSError:
            pass
    return failed


def _budget_stop_reason(ledger):
    reason = ledger.stop_reason()
    if reason in ("BUDGET_SOFT_STOP", "BUDGET_EXCEEDED"):
        return reason
    if ledger.summary()["reserved_microyuan"] >= SOFT_STOP_MICROYUAN:
        return "BUDGET_SOFT_STOP"
    return reason


async def collect_dataset(*, java, ai, dataset, split, output, run_metadata, fetch_row, ledger,
                          limit=None):
    if (not isinstance(run_metadata, dict)
            or set(run_metadata) != {"code_sha", "schema_sha256", "config_sha256", "prompt_sha256", "model"}
            or not isinstance(run_metadata["model"], str) or not run_metadata["model"].strip()
            or any(not isinstance(run_metadata[key], str)
                   or re.fullmatch("[0-9a-f]{" + str(length) + "}", run_metadata[key]) is None
                   for key, length in (("code_sha", 40), ("schema_sha256", 64),
                                       ("config_sha256", 64), ("prompt_sha256", 64)))):
        raise ValueError("INVALID_RUN_METADATA")
    manifest, questions, _documents, _sources, fingerprint = scorer._load_dataset(dataset)
    if manifest.get("privacy") == "local_only" and not output.resolve().is_relative_to(ROOT / ".blindtest/out"):
        raise ValueError("PRIVATE_OUTPUT_OUTSIDE_IGNORED_DIRECTORY")
    selected = [question for question in questions if question["split"] == split]
    if limit is not None:
        if type(limit) is not int or limit < 1:
            raise ValueError("INVALID_COLLECTION_LIMIT")
        selected = selected[:limit]
    if not selected or output.exists():
        raise ValueError("INVALID_COLLECTION_OUTPUT_OR_SPLIT")
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {"prediction_version": 2, "dataset_id": manifest["dataset_id"],
               "dataset_sha256": fingerprint, "run": run_metadata, "predictions": []}
    diagnostics_payload = {"prediction_version": 2, "dataset_id": manifest["dataset_id"],
                           "dataset_sha256": fingerprint, "diagnostics": []}
    diagnostics_path = output.with_suffix(".diagnostics.json")
    public_sources_payload = {"sidecar_version": 1, "dataset_id": manifest["dataset_id"],
                              "dataset_sha256": fingerprint, "split": split, "questions": []}
    public_sources_path = output.with_suffix(".public-sources.json")
    status = {"complete": False, "failures": [], "budget_steps": []}
    status_path = output.with_suffix(".status.json")

    def check_budget():
        stop = _budget_stop_reason(ledger)
        if stop is not None:
            status["failures"].append({"code": stop})
            write_json(status_path, status)
            raise ValueError(stop)

    check_budget()
    created = await java.post("/api/v1/knowledge-bases",
                              json={"contract_version": CONTRACT_VERSION, "name": "Evaluation collection"})
    if created.status_code != 201:
        raise ValueError("EVALUATION_KNOWLEDGE_BASE_CREATE_FAILED")
    knowledge_base_id = created.json()["id"]
    cleanup_failed = False
    try:
        write_json(status_path, status)
        mappings = {}
        for document in manifest["documents"]:
            check_budget()
            raw = (Path(dataset) / document["path"]).read_bytes()
            if sha256(raw).hexdigest() != document["sha256"]:
                raise ValueError("DATASET_CHANGED_DURING_COLLECTION")
            uploaded = await java.post(f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
                                       files={"file": (document["id"] + ".txt", raw, "text/plain")})
            if uploaded.status_code != 202:
                check_budget()
                raise ValueError("EVALUATION_UPLOAD_FAILED")
            accepted = uploaded.json()
            deadline = time.monotonic() + 180
            while True:
                task_response = await java.get("/api/v1/tasks/" + accepted["task_id"])
                task_response.raise_for_status()
                task = task_response.json()
                if task["status"] == "SUCCEEDED":
                    break
                check_budget()
                if task["status"] in ("FAILED", "CANCELLED") or time.monotonic() >= deadline:
                    raise ValueError("EVALUATION_INDEX_NOT_READY")
                await asyncio.sleep(.2)
            detail_response = await java.get("/api/v1/documents/" + accepted["document_id"])
            detail_response.raise_for_status()
            detail = detail_response.json()
            if detail["status"] != "READY" or detail["source_sha256"] != document["sha256"]:
                raise ValueError("EVALUATION_DOCUMENT_MISMATCH")
            index = await fetch_row("SELECT content_version_id FROM knowflow.index_versions WHERE id = %s",
                                    (detail["active_index_version_id"],))
            key = (accepted["document_id"], str(index["content_version_id"]), detail["active_index_version_id"])
            mappings[key] = {"source_bytes": raw, "source_sha256": document["sha256"],
                             "dataset_document_id": document["id"],
                             "dataset_content_version_id": document["content_version_id"]}
            status["budget_steps"].append({"stage": "index", **ledger.summary()})
            write_json(status_path, status)

        async def lookup(key):
            row = await fetch_row("SELECT id, request_id, failure_code FROM knowflow.questions "
                                  "WHERE idempotency_key = %s AND knowledge_base_id = %s",
                                  (key, knowledge_base_id))
            return {name: str(value) if name == "id" else value for name, value in row.items()} if row else None

        for question_index, question in enumerate(selected):
            check_budget()
            diagnostics = {}
            public_sources = []
            try:
                row = await collector.collect_question(
                    java=java, ai=ai, knowledge_base_id=knowledge_base_id,
                    question=question["question"], question_id=question["id"],
                    mappings=mappings, lookup_question=lookup,
                    diagnostics_out=diagnostics, public_sources_out=public_sources)
            except (ValueError, httpx.HTTPError):
                status["failures"].append({"question_id": question["id"], "code": "COLLECTION_INCOMPLETE"})
                row = {"question_id": question["id"], "outcome": "error", "answer": "",
                       "answer_sha256": sha256(b"").hexdigest(), "retrieved_evidence": [], "citations": [],
                       "latency_ms": 0, "error_code": "COLLECTION_INCOMPLETE"}
                diagnostics = {}
            else:
                if row["outcome"] == "error":
                    status["failures"].append({"question_id": question["id"],
                                               "error_code": row["error_code"]})
            payload["predictions"].append(row)
            diagnostics_payload["diagnostics"].append(
                {"question_id": question["id"], "outcome": row["outcome"],
                 "citation": diagnostics or None})
            public_sources_payload["questions"].extend(public_sources)
            status["budget_steps"].append({"stage": "question", **ledger.summary()})
            write_json(output, payload)
            write_json(diagnostics_path, diagnostics_payload)
            write_json(public_sources_path, public_sources_payload)
            write_json(status_path, status)
            if question_index + 1 < len(selected) or row["outcome"] == "error":
                check_budget()
        status["complete"] = not status["failures"]
        write_json(status_path, status)
        if not status["complete"]:
            raise ValueError("COLLECTION_INCOMPLETE")
        return payload
    finally:
        cleanup_failed = await _cleanup_knowledge_base(java, knowledge_base_id, output, status)
    if cleanup_failed:
        raise ValueError("EVALUATION_CLEANUP_FAILED")


async def main_async(args):
    for value in (args.java_url, args.ai_url):
        endpoint = urlsplit(value)
        if (endpoint.scheme != "http" or endpoint.hostname not in ("127.0.0.1", "localhost", "::1")
                or endpoint.username or endpoint.password or endpoint.path not in ("", "/")
                or endpoint.query or endpoint.fragment):
            raise ValueError("EVALUATION_ENDPOINT_MUST_BE_LOOPBACK")
    def query(sql, params):
        with psycopg.connect(os.environ["KNOWFLOW_EVALUATION_DATABASE_URL"], row_factory=dict_row) as db:
            return db.execute(sql, params).fetchone()
    async def fetch(sql, params):
        return await asyncio.to_thread(query, sql, params)
    async with httpx.AsyncClient(base_url=args.java_url, timeout=40, trust_env=False,
                               headers={"Authorization": "Bearer " + os.environ["KNOWFLOW_EVALUATION_ACCESS_TOKEN"]}) as java:
        async with httpx.AsyncClient(base_url=args.ai_url, timeout=40, trust_env=False, headers={
                "Authorization": "Bearer " + os.environ["KNOWFLOW_INTERNAL_SHARED_SECRET"],
                "X-Evaluation-Secret": os.environ["KNOWFLOW_EVALUATION_CONTROL_SECRET"]}) as ai:
            await collect_dataset(java=java, ai=ai, dataset=args.dataset, split=args.split, output=args.output,
                                  run_metadata=json.loads(args.run_metadata.read_text(encoding="utf-8")), fetch_row=fetch,
                                  ledger=BudgetLedger.from_environment(os.environ),
                                  limit=args.limit)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java-url", default="http://127.0.0.1:8080")
    parser.add_argument("--ai-url", default="http://127.0.0.1:8000")
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--split", choices=("development", "holdout"), default="development")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--run-metadata", required=True, type=Path)
    parser.add_argument("--limit", type=int, help="Collect only the first N selected questions")
    args = parser.parse_args()
    try:
        asyncio.run(main_async(args))
    except (ValueError, KeyError, OSError, httpx.HTTPError, psycopg.Error):
        print("EVALUATION_COLLECTION_FAILED")
        return 1
    print("EVALUATION_COLLECTION_COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
