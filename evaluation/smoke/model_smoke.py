"""Explicitly configured live API smoke; standard library only, no model fallback."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import socket
import subprocess
import time
from urllib import error, parse, request
from zoneinfo import ZoneInfo

FIXTURE = Path(__file__).with_name("fixture.json")
MAX_RESPONSE_BYTES = 1_048_576


class SmokeFailure(Exception):
    """Only a fixed, non-sensitive error code may be serialized."""


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SmokeFailure("REDIRECT_REJECTED")


def read_config(env):
    missing = []
    config = {}
    for role in ("EMBEDDING", "LLM"):
        prefix = "KNOWFLOW_" + role
        model = env.get(prefix + "_MODEL", "").strip()
        if not model:
            missing.append(prefix + "_MODEL")
        elif not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}", model):
            raise SmokeFailure("INVALID_MODEL_IDENTIFIER")
        if role == "EMBEDDING" and model.rsplit("/", 1)[-1].lower().startswith("bge-reranker"):
            raise SmokeFailure("RERANKER_IS_NOT_EMBEDDING")
        # Separate endpoints require explicit credential selectors. Never forward a
        # shared provider key to a newly configured provider by silent fallback.
        separate_url = env.get(prefix + "_BASE_URL", "").strip()
        base_url = separate_url or env.get("KNOWFLOW_MODEL_BASE_URL", "").strip()
        if not base_url:
            missing.append(prefix + "_BASE_URL")
        else:
            try:
                url = parse.urlsplit(base_url)
                url.port
            except ValueError:
                raise SmokeFailure("INVALID_HTTPS_BASE_URL") from None
            if (url.scheme != "https" or not url.hostname or url.username is not None
                    or url.password is not None or url.query or url.fragment):
                raise SmokeFailure("INVALID_HTTPS_BASE_URL")
        key_name = env.get(prefix + "_KEY_ENV")
        if key_name is None and not separate_url:
            key_name = env.get("KNOWFLOW_MODEL_KEY_ENV", "OPENAI_API_KEY")
        if key_name is None:
            missing.append(prefix + "_KEY_ENV")
        elif not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key_name):
            raise SmokeFailure("INVALID_KEY_VARIABLE_NAME")
        elif not env.get(key_name):
            missing.append(key_name)
        config[role.lower()] = {
            "base_url": base_url.rstrip("/"), "model": model,
            "key": env.get(key_name) if key_name else None,
        }
    dimension = env.get("KNOWFLOW_EMBEDDING_DIMENSIONS")
    if not dimension:
        missing.append("KNOWFLOW_EMBEDDING_DIMENSIONS")
    else:
        try:
            dimension = int(dimension)
        except ValueError:
            raise SmokeFailure("INVALID_DIMENSIONS") from None
        if not 1 <= dimension <= 65536:
            raise SmokeFailure("INVALID_DIMENSIONS")
    thinking = env.get("KNOWFLOW_LLM_THINKING", "default")
    if thinking not in ("default", "enabled", "disabled"):
        raise SmokeFailure("INVALID_THINKING_MODE")
    config["llm"]["thinking"] = thinking
    config["dimensions"] = dimension
    return (None, list(dict.fromkeys(missing))) if missing else (config, [])


def post_json(opener, config, path, payload, timeout):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        config["base_url"] + path,
        data=body,
        headers={
            "Authorization": "Bearer " + config["key"],
            "Content-Type": "application/json",
        },
        method="POST",
    )
    start = time.monotonic()
    try:
        with opener.open(req, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except error.HTTPError as exc:
        code = (
            "AUTH_REJECTED" if exc.code in (401, 403)
            else "RATE_LIMITED" if exc.code == 429
            else "HTTP_FAILURE"
        )
        status = exc.code
        exc.close()
        return {"status": "FAILED", "error": code, "http_status": status,
                "elapsed_ms": round((time.monotonic() - start) * 1000, 3)}, None
    except (TimeoutError, socket.timeout):
        return {"status": "FAILED", "error": "TIMEOUT"}, None
    except error.URLError as exc:
        code = "TIMEOUT" if isinstance(exc.reason, TimeoutError) else "NETWORK_FAILURE"
        return {"status": "FAILED", "error": code}, None
    if len(raw) > MAX_RESPONSE_BYTES:
        raise SmokeFailure("RESPONSE_TOO_LARGE")
    try:
        result = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise SmokeFailure("INVALID_JSON_RESPONSE") from None
    if not isinstance(result, dict):
        raise SmokeFailure("INVALID_RESPONSE_SHAPE")
    metadata = {"status": "RECEIVED", "elapsed_ms": round((time.monotonic() - start) * 1000, 3)}
    usage = result.get("usage", {})
    if isinstance(usage, dict):
        metadata["usage"] = {
            k: usage[k] for k in ("prompt_tokens", "completion_tokens", "total_tokens")
            if type(usage.get(k)) is int and 0 <= usage[k] <= 10**9
        }
    return metadata, result


def validate_embeddings(result, count, dimension):
    rows = result.get("data")
    if not isinstance(rows, list) or len(rows) != count:
        raise SmokeFailure("EMBEDDING_COUNT_MISMATCH")
    indices = set()
    for row in rows:
        if not isinstance(row, dict) or type(row.get("index")) is not int:
            raise SmokeFailure("INVALID_EMBEDDING_INDEX")
        indices.add(row["index"])
        vector = row.get("embedding")
        if not isinstance(vector, list) or len(vector) != dimension:
            raise SmokeFailure("EMBEDDING_DIMENSION_MISMATCH")
        if any(type(x) not in (int, float) or not math.isfinite(x) for x in vector):
            raise SmokeFailure("INVALID_EMBEDDING_VALUE")
        if not any(x != 0 for x in vector):
            raise SmokeFailure("ZERO_EMBEDDING")
    if indices != set(range(count)):
        raise SmokeFailure("INVALID_EMBEDDING_INDEX")
    return {"count": count, "observed_dimensions": dimension, "finite_nonzero": True}


def validate_provider_model(result, requested_model):
    if result.get("model") != requested_model:
        raise SmokeFailure("PROVIDER_MODEL_MISMATCH")


def validate_answer(result, fixture):
    try:
        answer = result["choices"][0]["message"]["content"]
        finish = result["choices"][0]["finish_reason"]
    except (KeyError, IndexError, TypeError):
        raise SmokeFailure("INVALID_CHAT_RESPONSE") from None
    if not isinstance(answer, str) or not answer.strip():
        raise SmokeFailure("EMPTY_CHAT_RESPONSE")
    if finish != "stop":
        raise SmokeFailure("INCOMPLETE_CHAT_RESPONSE")
    if not all(term in answer for term in fixture["answer_must_contain"]):
        raise SmokeFailure("CHINESE_FACT_CHECK_FAILED")
    if not re.search(r"[\u4e00-\u9fff]", answer):
        raise SmokeFailure("CHINESE_ANSWER_MISSING")
    return {"synthetic_fact_check": True, "answer_sha256": hashlib.sha256(answer.encode()).hexdigest()}


def runtime_metadata():
    metadata = {"python": platform.python_version(), "machine": platform.machine(),
                "logical_cpus": os.cpu_count()}
    for key, file in (("cpu_quota", "cpu.max"), ("memory_limit_bytes", "memory.max")):
        path = Path("/sys/fs/cgroup") / file
        metadata[key] = path.read_text().strip() if path.is_file() else "unavailable"
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False,
        cwd=Path(__file__).resolve().parents[2],
    )
    metadata["git_head"] = result.stdout.strip() if result.returncode == 0 else None
    return metadata


def run(env, timeout):
    report = {
        "schema_version": 2,
        "recorded_at": datetime.now(ZoneInfo("Asia/Hong_Kong")).isoformat(),
        "fixture_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "runtime": runtime_metadata(),
        "network_attempted": False,
        "cost": {"amount": None, "reason": "Official rates support estimates; actual account billing was not retrieved."},
        "checks": {},
    }
    try:
        config, missing = read_config(env)
        if missing:
            report.update(status="WAITING_INPUT", missing_configuration=missing)
            return report, 2
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        report["configuration"] = {
            "embedding_model": config["embedding"]["model"], "llm_model": config["llm"]["model"],
            "expected_dimensions": config["dimensions"], "timeout_seconds": timeout,
            "max_attempts_per_endpoint": 1,
            "llm_thinking": config["llm"]["thinking"],
        }
        opener = request.build_opener(NoRedirect())
        report["network_attempted"] = True
        checks = report["checks"]
        checks["embedding"], result = post_json(opener, config["embedding"], "/embeddings", {
            "model": config["embedding"]["model"], "input": fixture["embedding_inputs"],
        }, timeout)
        if result is not None:
            try:
                validate_provider_model(result, config["embedding"]["model"])
            except SmokeFailure as exc:
                checks["embedding"].update(status="FAILED", error=exc.args[0])
                report["status"] = "FAILED"
                return report, 1
            checks["embedding"].update(validate_embeddings(result, 2, config["dimensions"]), status="PASSED")
            checks["embedding"]["provider_model_matches_request"] = True
        else:
            report["status"] = "FAILED"
            return report, 1  # Avoid a second billable call after an embedding failure.
        payload = {
            "model": config["llm"]["model"],
            "messages": [
                {"role": "system", "content": "只根据提供的合成资料回答问题。"},
                {"role": "user", "content": fixture["excerpt"] + "\n" + fixture["question"]},
            ],
            "max_tokens": 128,
        }
        if config["llm"]["thinking"] != "default":
            payload["thinking"] = {"type": config["llm"]["thinking"]}
        checks["chat"], result = post_json(opener, config["llm"], "/chat/completions", payload, timeout)
        if result is not None:
            try:
                validate_provider_model(result, config["llm"]["model"])
            except SmokeFailure as exc:
                checks["chat"].update(status="FAILED", error=exc.args[0])
                report["status"] = "FAILED"
                return report, 1
            checks["chat"].update(validate_answer(result, fixture), status="PASSED")
            checks["chat"]["provider_model_matches_request"] = True
        report["status"] = "LIVE_SMOKE_PASSED" if result is not None else "FAILED"
        return report, 0 if result is not None else 1
    except SmokeFailure as exc:
        report.update(status="FAILED", error=exc.args[0])
    except Exception:
        # Provider exceptions may contain authorization headers or private response bodies.
        report.update(status="FAILED", error="UNEXPECTED_FAILURE")
    return report, 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout", default=20.0, type=float)
    args = parser.parse_args()
    if not 0 < args.timeout <= 30:
        parser.error("--timeout must be in (0, 30]")
    if args.output.exists():
        parser.error("output already exists; choose a new evidence file")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Reserve the path before making any billable calls.
    with args.output.open("x", encoding="utf-8") as target:
        report, code = run(os.environ, args.timeout)
        json.dump(report, target, ensure_ascii=False, indent=2, allow_nan=False)
        target.write("\n")
    print(report["status"])
    return code


if __name__ == "__main__":
    raise SystemExit(main())
