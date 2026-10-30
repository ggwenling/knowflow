"""One live embedding request with original synthetic text and redacted evidence."""
import argparse
import asyncio
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time
import uuid
from zoneinfo import ZoneInfo

from knowflow_ai.adapters import ProcessingError
from knowflow_ai.config import ConfigurationError
from knowflow_ai.embedding import EmbeddingSettings, SiliconFlowEmbeddingAdapter


SYNTHETIC_TEXT = "KnowFlow 合成样本：接口返回内容必须保留原文依据，并使用一致的内容版本。"


async def run() -> dict:
    report = {
        "recorded_at": datetime.now(ZoneInfo("Asia/Hong_Kong")).isoformat(),
        "status": "FAILED",
        "provider": "siliconflow",
        "endpoint": "https://api.siliconflow.cn/v1/embeddings",
        "requested_model": "BAAI/bge-m3",
        "expected_dimensions": 1024,
        "input_kind": "single_original_synthetic_text",
        "input_sha256": hashlib.sha256(SYNTHETIC_TEXT.encode("utf-8")).hexdigest(),
        "network_attempted": False,
        "automatic_retries": 0,
    }
    try:
        settings = EmbeddingSettings.from_environment()
    except ConfigurationError as exc:
        report.update(status="WAITING_INPUT", error=str(exc))
        return report

    adapter = SiliconFlowEmbeddingAdapter(settings)
    started = time.monotonic()
    report["network_attempted"] = True
    try:
        response = await adapter.embed([SYNTHETIC_TEXT], request_id="smoke-" + uuid.uuid4().hex)
        vector = response["data"][0]["embedding"]
        report.update(
            status="LIVE_EMBEDDING_PASSED",
            response_model=response["model"],
            vector_count=len(response["data"]),
            vector_dimensions=len(vector),
            vector_all_finite=all(type(value) in (int, float) and math.isfinite(value)
                                  for value in vector),
            usage=response.get("usage"),
            duration_ms=round((time.monotonic() - started) * 1000),
        )
    except ProcessingError as exc:
        report.update(status="FAILED", error=exc.code, retryable=exc.retryable,
                      duration_ms=round((time.monotonic() - started) * 1000))
    except Exception:
        report.update(status="FAILED", error="UNEXPECTED_FAILURE",
                      duration_ms=round((time.monotonic() - started) * 1000))
    finally:
        await adapter.aclose()

    try:
        report["git_head_at_run"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        report["git_head_at_run"] = None
    report["runner_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report["adapter_sha256"] = hashlib.sha256(
        Path(__file__).parents[1].joinpath("src/knowflow_ai/embedding.py").read_bytes()).hexdigest()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with args.output.open("x", encoding="utf-8") as target:
            report = asyncio.run(run())
            json.dump(report, target, ensure_ascii=False, indent=2, allow_nan=False)
            target.write("\n")
    except FileExistsError:
        parser.error("output already exists; choose a new evidence file")
    print(report["status"])
    return 0 if report["status"] == "LIVE_EMBEDDING_PASSED" else 2 if report["status"] == "WAITING_INPUT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
