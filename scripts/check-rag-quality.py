"""Score a candidate-bound, independently reviewed public holdout run."""
import argparse
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evaluation/runner"))
import runner_v2 as runner

DATASET = ROOT / "evaluation/data/seed-v2-reviewed"


def check(args):
    payload = json.loads(args.predictions.read_bytes())
    if payload["run"]["code_sha"] != args.candidate or payload["run"]["model"] != "deepseek-flash":
        raise SystemExit("RAG_CANDIDATE_MISMATCH")
    config = {"gate_version": 2, "dataset_id": payload["dataset_id"],
              "dataset_sha256": payload["dataset_sha256"],
              "minimums": {**runner.MINIMUMS, "citation_accuracy": .96}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    config_path = args.output.with_suffix(".thresholds.json")
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    report = runner.evaluate(args.predictions, split="holdout", dataset_root=DATASET,
                             quality_config_path=config_path, review_path=args.review)
    baseline = json.loads(args.baseline.read_bytes())
    runs = baseline["p95_ms"]
    if (baseline["dataset_sha256"] != report["dataset_sha256"]
            or baseline["model"] != "deepseek-flash" or len(runs) != 3
            or any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0 for value in runs)):
        raise SystemExit("RAG_LATENCY_BASELINE_INVALID")
    maximum = statistics.median(runs) * 1.25
    observed = report["metrics"]["latency_ms"]["p95_nearest_rank"]
    report["latency_gate"] = {"p95_max_ms": maximum, "observed_ms": observed, "passed": observed <= maximum}
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if (report["sample_count"] != 20 or report["quality_gate"]["status"] != "passed"
            or not report["latency_gate"]["passed"]):
        raise SystemExit("RAG_QUALITY_GATE_FAILED")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("predictions", "review", "baseline", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--candidate", required=True)
    check(parser.parse_args())
