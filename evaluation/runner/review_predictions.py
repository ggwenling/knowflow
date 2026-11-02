"""Create and merge a dataset-bound human support review bundle."""
import argparse
import importlib.util
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _timestamp(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00").utcoffset() == timezone.utc.utcoffset(None)
    except ValueError:
        return False


def prepare_bundle(predictions_path, *, created_at=None, dataset_root=None, split="development"):
    raw = Path(predictions_path).read_bytes()
    payload = json.loads(raw)
    if isinstance(payload, dict) and payload.get("prediction_version") == 2:
        spec = importlib.util.spec_from_file_location("runner_v2", Path(__file__).with_name("runner_v2.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.prepare_review(predictions_path, dataset_root or module.legacy.DEFAULT_DATASET, split)
    if (not isinstance(payload, dict)
            or set(payload) != {"dataset_id", "dataset_sha256", "predictions"}
            or not isinstance(payload["predictions"], list)):
        raise ValueError("INVALID_PREDICTIONS")
    entries = []
    seen = set()
    for row in payload["predictions"]:
        if (not isinstance(row, dict) or set(row) != {
                "question_id", "has_answer", "retrieved_evidence", "cited_evidence",
                "support_judgement", "latency_ms"}
                or not isinstance(row["question_id"], str)
                or type(row["has_answer"]) is not bool
                or row["question_id"] in seen):
            raise ValueError("INVALID_PREDICTIONS")
        seen.add(row["question_id"])
        entries.append({"question_id": row["question_id"],
                        "has_answer": row["has_answer"],
                        "support_judgement": "unreviewed" if row["has_answer"] else "not_applicable",
                        "reviewed_by": None, "reviewed_at": None})
    return {"review_version": 1, "dataset_id": payload["dataset_id"],
            "dataset_sha256": payload["dataset_sha256"],
            "predictions_sha256": sha256(raw).hexdigest(),
            "created_at": created_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "entries": entries}


def merge_reviews(predictions_path, review_path, output_path):
    raw = Path(predictions_path).read_bytes()
    predictions = json.loads(raw)
    review = _read(review_path)
    if (not isinstance(review, dict)
            or set(review) != {"review_version", "dataset_id", "dataset_sha256",
                               "predictions_sha256", "created_at", "entries"}
            or review["review_version"] != 1
            or review["dataset_id"] != predictions.get("dataset_id")
            or review["dataset_sha256"] != predictions.get("dataset_sha256")
            or review["predictions_sha256"] != sha256(raw).hexdigest()
            or not _timestamp(review["created_at"])):
        raise ValueError("REVIEW_INPUT_MISMATCH")
    original = {row["question_id"]: row for row in predictions["predictions"]}
    entries = review["entries"]
    if (not isinstance(entries, list) or len(entries) != len(original)
            or any(not isinstance(entry, dict) or set(entry) != {
                "question_id", "has_answer", "support_judgement", "reviewed_by", "reviewed_at"}
                for entry in entries)):
        raise ValueError("INVALID_REVIEW_ENTRIES")
    by_id = {entry["question_id"]: entry for entry in entries}
    if len(by_id) != len(entries) or set(by_id) != set(original):
        raise ValueError("INVALID_REVIEW_ENTRIES")
    merged = json.loads(raw)
    for row in merged["predictions"]:
        entry = by_id[row["question_id"]]
        if entry["has_answer"] is not row["has_answer"]:
            raise ValueError("REVIEW_INPUT_MISMATCH")
        if row["has_answer"]:
            if (entry["support_judgement"] not in ("supported", "unsupported")
                    or not isinstance(entry["reviewed_by"], str)
                    or not entry["reviewed_by"].strip()
                    or not _timestamp(entry["reviewed_at"])):
                raise ValueError("SUPPORT_REVIEW_INCOMPLETE")
        elif entry["support_judgement"] != "not_applicable":
            raise ValueError("INVALID_SUPPORT_JUDGEMENT")
        row["support_judgement"] = entry["support_judgement"]
    Path(output_path).write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--split", choices=("development", "holdout"), default="development")
    args = parser.parse_args()
    if args.review is None:
        result = prepare_bundle(args.predictions, dataset_root=args.dataset, split=args.split)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
    else:
        if _read(args.predictions).get("prediction_version") == 2:
            raise ValueError("V2_PASS_REVIEW_DIRECTLY_TO_RUNNER")
        merge_reviews(args.predictions, args.review, args.output)


if __name__ == "__main__":
    main()
