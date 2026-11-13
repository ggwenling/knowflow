"""Freeze p95 observations from three successful runs of one candidate."""
import json
from pathlib import Path
import sys

directory = Path(sys.argv[1])
reports = [json.loads((directory / str(i) / "report.json").read_bytes()) for i in (1, 2, 3)]
identity = reports[0]["run"]
if any(not report["passed"] or report["predictions"] != 20 or report["run"] != identity for report in reports):
    raise SystemExit("RAG_BASELINE_RUN_MISMATCH")
fingerprints = {json.loads((directory / str(i) / "report.predictions.json").read_bytes())["dataset_sha256"]
                for i in (1, 2, 3)}
if len(fingerprints) != 1:
    raise SystemExit("RAG_BASELINE_DATASET_MISMATCH")
baseline = {"code_sha": identity["code_sha"], "model": identity["model"],
            "dataset_sha256": fingerprints.pop(),
            "p95_ms": [report["metrics"]["latency_ms"]["p95_nearest_rank"] for report in reports]}
(directory / "rag-latency-baseline.json").write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
