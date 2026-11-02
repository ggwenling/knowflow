"""Run an isolated synthetic API workload; never call a real model provider."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import platform
from pathlib import Path
import re
import secrets
import socket
import subprocess
import tempfile
import threading
import time
import uuid

import httpx

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "infra/compose.yml"
CONTRACT = "0.2.0-draft.10"
BUILD_INPUTS = ("infra", "services/api", "services/ai/src", "services/ai/Dockerfile",
                "services/ai/pyproject.toml", "services/ai/uv.lock", "services/ai/tools/local_backend_e2e.py",
                "services/ai/tools/browser_e2e_server.py", "contracts/schemas")


def percentile(values, fraction):
    return sorted(values)[math.ceil(len(values) * fraction) - 1] if values else None


def summarize(values):
    return {"sample_count": len(values), "p50_ms": percentile(values, .5),
            "p95_ms": percentile(values, .95)}


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def docker(args, *, check=True, timeout=600):
    return subprocess.run(["docker", *args], cwd=ROOT, capture_output=True,
                          text=True, check=check, timeout=timeout)


def clean_build_revision():
    status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all", "--", *BUILD_INPUTS],
                            cwd=ROOT, capture_output=True, text=True, check=True).stdout
    if status.strip():
        raise RuntimeError("DIRTY_BUILD_INPUTS")
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                          text=True, check=True).stdout.strip()


def compose_files(directory, port):
    env = directory / "perf.env"
    names = ("POSTGRES_PASSWORD", "MIGRATOR_PASSWORD", "APP_PASSWORD", "AI_PASSWORD")
    values = {"KNOWFLOW_DEV_" + name: secrets.token_hex(32) for name in names}
    values.update({"KNOWFLOW_DEV_MINIO_ROOT_USER": "knowflowperf",
                   "KNOWFLOW_DEV_MINIO_ROOT_PASSWORD": secrets.token_hex(32),
                   "KNOWFLOW_INTERNAL_SHARED_SECRET": secrets.token_hex(32),
                   "KNOWFLOW_E2E_DUMMY_EMBEDDING_KEY": secrets.token_hex(32),
                   "KNOWFLOW_E2E_DUMMY_LLM_KEY": secrets.token_hex(32)})
    env.write_text("\n".join(f"{key}={value}" for key, value in values.items()) + "\n", encoding="utf-8")
    override = directory / "override.yml"
    command = ["python", "-c", "import logging,runpy,sys; logging.basicConfig(level=logging.INFO); logging.getLogger('knowflow_ai.answering').setLevel(logging.INFO); sys.path.insert(0, '/workspace/services/ai/tools'); sys.argv=['browser_e2e_server.py','--host','0.0.0.0']; runpy.run_path('/workspace/services/ai/tools/browser_e2e_server.py',run_name='__main__')"]
    override.write_text(f'services:\n  api:\n    ports:\n      - "127.0.0.1:{port}:8080"\n    networks: [knowflow, web-edge]\n  ai:\n    command: {json.dumps(command)}\n', encoding="utf-8")
    return env, override


def setup_owner(client):
    response = client.post("/api/v1/auth/register", json={"contract_version": CONTRACT,
                           "email": f"perf-{uuid.uuid4().hex}@example.test",
                           "password": f"Perf-{secrets.token_hex(16)}"})
    response.raise_for_status()
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def index_documents(client, headers, count):
    response = client.post("/api/v1/knowledge-bases", headers=headers,
                           json={"contract_version": CONTRACT, "name": f"Synthetic performance {count}"})
    response.raise_for_status()
    base_id = response.json()["id"]
    started = time.monotonic()
    tasks = []
    for i in range(count):
        body = (f"Synthetic performance document {i}. Java owns publication. "
                "A document is searchable after READY.\n").encode()
        result = client.post(f"/api/v1/knowledge-bases/{base_id}/documents", headers=headers,
                             files={"file": (f"document-{i:03}.txt", body, "text/plain")})
        result.raise_for_status()
        tasks.append(result.json()["task_id"])
    remaining = set(tasks)
    deadline = time.monotonic() + max(240, count * 5)
    while remaining and time.monotonic() < deadline:
        for task_id in list(remaining):
            result = client.get(f"/api/v1/tasks/{task_id}", headers=headers)
            result.raise_for_status()
            status = result.json()["status"]
            if status == "SUCCEEDED":
                remaining.remove(task_id)
            elif status in ("FAILED", "CANCELLED"):
                raise RuntimeError("INDEX_TASK_" + status)
        if remaining:
            time.sleep(.3)
    if remaining:
        raise RuntimeError("INDEX_TIMEOUT")
    return base_id, round((time.monotonic() - started) * 1000, 2)


def question(base_url, headers, base_id):
    request_id = uuid.uuid4().hex
    request_headers = {**headers, "X-Request-ID": request_id}
    started = time.monotonic()
    first_ms = None
    event = None
    terminal = None
    retrieval_request_id = None
    sequence = 0
    started_event = False
    sources_event = False
    error_code = None
    retryable = None
    try:
        with httpx.Client(base_url=base_url, timeout=45, trust_env=False) as client:
            with client.stream("POST", f"/api/v1/knowledge-bases/{base_id}/questions/stream",
                               headers=request_headers, json={"question": "When is a document searchable?"}) as response:
                if response.status_code != 200:
                    return {"request_id": request_id, "outcome": "http_error", "status": response.status_code}
                for line in response.iter_lines():
                    if line.startswith("event:"):
                        event = line[6:].strip()
                    elif line.startswith("data:") and event:
                        try:
                            data = json.loads(line[5:].strip())
                        except json.JSONDecodeError:
                            return {"request_id": request_id, "outcome": "stream_error"}
                        event_request_id = data.get("request_id") if isinstance(data, dict) else None
                        if event_request_id:
                            if retrieval_request_id and retrieval_request_id != event_request_id:
                                return {"request_id": request_id, "outcome": "stream_error"}
                            retrieval_request_id = event_request_id
                        if (not isinstance(data, dict) or not isinstance(event_request_id, str)
                                or not event_request_id or type(data.get("sequence")) is not int
                                or data["sequence"] != sequence + 1 or data.get("event") != event):
                            return {"request_id": request_id, "outcome": "protocol_error"}
                        sequence += 1
                        if event == "started" and sequence == 1:
                            started_event = True
                        elif event == "delta" and started_event and not sources_event:
                            if not isinstance(data.get("delta"), str) or not data["delta"]:
                                return {"request_id": request_id, "outcome": "protocol_error"}
                            if first_ms is None:
                                first_ms = round((time.monotonic() - started) * 1000, 2)
                        elif event == "sources" and started_event and not sources_event:
                            if not isinstance(data.get("sources"), list) or type(data.get("has_answer")) is not bool:
                                return {"request_id": request_id, "outcome": "protocol_error"}
                            sources_event = True
                        elif event == "completed" and started_event and sources_event and first_ms is not None:
                            terminal = event
                            break
                        elif event == "error":
                            code = data.get("code")
                            if not isinstance(code, str) or not re.fullmatch(r"[A-Z0-9_]{1,80}", code) or type(data.get("retryable")) is not bool:
                                return {"request_id": request_id, "outcome": "protocol_error"}
                            error_code, retryable = code, data["retryable"]
                            terminal = event
                            break
                        else:
                            return {"request_id": request_id, "outcome": "protocol_error"}
                elapsed = round((time.monotonic() - started) * 1000, 2)
                return {"request_id": request_id, "outcome": "success" if terminal == "completed" else "stream_error",
                        "retrieval_request_id": retrieval_request_id, "first_delta_ms": first_ms, "total_ms": elapsed,
                        "error_code": error_code, "retryable": retryable}
    except httpx.HTTPError:
        return {"request_id": request_id, "outcome": "transport_error"}


def run_questions(base_url, headers, base_id, concurrency, count):
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(question, base_url, headers, base_id) for _ in range(count)]
        rows = [future.result() for future in futures]
    success = [row for row in rows if row["outcome"] == "success"]
    return {"concurrency": concurrency, "requested": count, "succeeded": len(success),
            "failed": len(rows) - len(success),
            "retryable_ai_failures": sum(row.get("error_code") == "AI_PROCESSING_FAILED" and row.get("retryable") is True for row in rows),
            "outcomes": {kind: sum(row["outcome"] == kind for row in rows)
                         for kind in sorted({row["outcome"] for row in rows})},
            "first_delta": summarize([r["first_delta_ms"] for r in success if r["first_delta_ms"] is not None]),
            "complete": summarize([r["total_ms"] for r in success]), "requests": rows}


def retrieval_timings(logs, request_ids):
    result = {}
    for line in logs.splitlines():
        match = re.search(r"ai_stage request_id=([A-Za-z0-9._:-]+) stage=retrieval duration_ms=(\d+)", line)
        if match and match.group(1) in request_ids:
            result[match.group(1)] = int(match.group(2))
    return result


def measurement_status(cases):
    loads = [load for case in cases for load in case["loads"]]
    if not loads or any(load["failed"] for load in loads):
        return "completed_with_errors" if loads else "incomplete"
    if any(load["first_delta"]["sample_count"] != load["succeeded"]
           or load["retrieval"]["sample_count"] != load["succeeded"] for load in loads):
        return "incomplete"
    return "completed"


def resource_samples(base, project, stop, samples):
    """Sample only services belonging to this explicitly named Compose project."""
    while not stop.is_set():
        try:
            ids = docker([*base, "ps", "-q", "api", "ai", "postgres", "minio"], timeout=10).stdout.split()
            if ids:
                output = docker(["stats", "--no-stream", "--format", "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}", *ids], timeout=15).stdout
                for line in output.splitlines():
                    name, cpu, memory = line.split("\t")
                    match = re.fullmatch(r"([\d.]+)\s*([KMGT]?i?B)", memory.split("/", 1)[0].strip())
                    if not name.startswith(project + "-") or not match:
                        continue
                    unit = match.group(2)
                    factor = {"B": 1, "kB": 1000, "KB": 1000, "MB": 1000**2, "GB": 1000**3,
                              "TB": 1000**4, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3, "TiB": 1024**4}[unit]
                    service = name[len(project) + 1:].rsplit("-", 1)[0]
                    samples.append((service, float(cpu.rstrip("%")), round(float(match.group(1)) * factor)))
        except (subprocess.SubprocessError, ValueError, KeyError):
            pass
        stop.wait(2)


def summarize_resources(samples):
    return {service: {"samples": len(rows), "peak_cpu_percent": max(r[1] for r in rows),
                      "peak_memory_bytes": max(r[2] for r in rows)}
            for service in sorted({r[0] for r in samples})
            if (rows := [r for r in samples if r[0] == service])}


def run(args):
    revision = clean_build_revision()
    project = "knowflow-perf-" + uuid.uuid4().hex[:12]
    if docker(["ps", "-aq", "--filter", f"label=com.docker.compose.project={project}"]).stdout.strip():
        raise RuntimeError("PROJECT_ALREADY_EXISTS")
    if docker(["volume", "ls", "-q", "--filter", f"label=com.docker.compose.project={project}"]).stdout.strip():
        raise RuntimeError("PROJECT_VOLUME_ALREADY_EXISTS")
    port = free_port()
    docker_info = docker(["info", "--format", "{{.NCPU}} {{.MemTotal}} {{.ServerVersion}}"]).stdout.strip().split()
    other_running = docker(["ps", "-q"]).stdout.splitlines()
    report = {"run_at": datetime.now(timezone.utc).isoformat(), "project": project,
              "source_revision": revision,
              "environment": {"os": platform.platform(), "cpu_count": os.cpu_count(),
                              "docker_cpus": int(docker_info[0]), "docker_memory_bytes": int(docker_info[1]),
                              "docker_version": docker_info[2],
                              "other_running_container_count": len(other_running),
                              "mode": "synthetic adapters, local Docker, no external model calls",
                              "retrieval": "AI service stage log; excludes question embedding",
                              "first_delta": "client elapsed time until first SSE delta",
                              "resources": "docker stats samples; observed maxima, not continuous peaks"},
              "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in (Path(__file__), COMPOSE, ROOT / "services/ai/tools/browser_e2e_server.py")},
              "cases": [], "status": "incomplete"}
    with tempfile.TemporaryDirectory(prefix="knowflow-perf-") as temp:
        env, override = compose_files(Path(temp), port)
        base = ["compose", "--project-name", project, "-f", str(COMPOSE), "-f", str(override), "--env-file", str(env)]
        started = False
        stop = threading.Event()
        resource_rows = []
        sampler = None
        try:
            started = True
            docker([*base, "up", "--build", "--quiet-build", "--wait", "--wait-timeout", "240", "api"])
            if clean_build_revision() != revision:
                raise RuntimeError("BUILD_INPUTS_CHANGED")
            report["images"] = {}
            for service in ("api", "ai", "postgres", "minio"):
                container_id = docker([*base, "ps", "-q", service]).stdout.strip()
                report["images"][service] = docker(["inspect", "--format", "{{.Image}}", container_id]).stdout.strip()
            sampler = threading.Thread(target=resource_samples, args=(base, project, stop, resource_rows), daemon=True)
            sampler.start()
            base_url = f"http://127.0.0.1:{port}"
            with httpx.Client(base_url=base_url, timeout=45, trust_env=False) as client:
                headers = setup_owner(client)
                for count in args.documents:
                    base_id, index_ms = index_documents(client, headers, count)
                    case = {"document_count": count, "index_elapsed_ms": index_ms, "loads": []}
                    report["cases"].append(case)
                    for concurrency in args.concurrency:
                        case["loads"].append(run_questions(base_url, headers, base_id, concurrency, args.samples))
            ids = {r["retrieval_request_id"] for c in report["cases"] for load in c["loads"] for r in load["requests"] if r.get("retrieval_request_id")}
            logs = docker([*base, "logs", "--no-color", "ai"])
            durations = retrieval_timings(logs.stdout + "\n" + logs.stderr, ids)
            for case in report["cases"]:
                for load in case["loads"]:
                    load["retrieval"] = summarize([durations[r["retrieval_request_id"]] for r in load["requests"]
                                                  if r.get("retrieval_request_id") in durations])
            report["status"] = measurement_status(report["cases"])
        except (RuntimeError, httpx.HTTPError, subprocess.SubprocessError) as error:
            report["failure"] = type(error).__name__
            raise
        finally:
            stop.set()
            if sampler:
                sampler.join(timeout=20)
            report["resources"] = summarize_resources(resource_rows)
            if started:
                cleanup = docker([*base, "down", "--volumes", "--remove-orphans"], check=False)
                report["cleanup_exit_code"] = cleanup.returncode
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--documents", nargs="+", type=int, default=[10, 100])
    parser.add_argument("--concurrency", nargs="+", type=int, default=[1, 4, 8])
    parser.add_argument("--samples", type=int, default=8)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if any(not 1 <= n <= 100 for n in args.documents) or any(not 1 <= n <= 32 for n in args.concurrency) or not 1 <= args.samples <= 1000:
        parser.error("invalid workload bounds")
    result = run(args)
    print(json.dumps({"status": result["status"], "cases": len(result["cases"]), "output": str(args.output)}))
    if result["cleanup_exit_code"] != 0 or result["status"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
