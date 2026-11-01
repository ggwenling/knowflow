"""Validate a human review file and materialize an independent scored dataset."""
import argparse
from datetime import datetime
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile


TOOLS = Path(__file__).resolve().parent


def _load_tool(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_candidate_tools = _load_tool("candidate_split_validation", TOOLS / "split_candidates.py")
_seed_validator = _load_tool("reviewed_seed_validation", TOOLS / "validate_seed.py")


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _canonical_sha256(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def _write_json(path, value):
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _verify_split(candidates, split_manifest, candidates_sha256):
    if (not isinstance(split_manifest, dict)
            or split_manifest.get("split_manifest_version") != 1
            or split_manifest.get("status") != "candidate_allocation_not_a_blind_holdout"
            or split_manifest.get("input_sha256") != candidates_sha256
            or split_manifest.get("target_counts") != {"development": 40, "holdout": 20}):
        raise ValueError("SPLIT_MANIFEST_MISMATCH")
    ids = {item["id"] for item in candidates}
    if len(ids) != 60:
        raise ValueError("CANDIDATE_QUESTION_COUNT_MISMATCH")
    question_ids = split_manifest.get("question_ids")
    if not isinstance(question_ids, dict) or set(question_ids) != {"development", "holdout"}:
        raise ValueError("SPLIT_MANIFEST_MISMATCH")
    development, holdout = question_ids["development"], question_ids["holdout"]
    if (not isinstance(development, list) or not isinstance(holdout, list)
            or len(development) != 40 or len(holdout) != 20
            or len(set(development)) != 40 or len(set(holdout)) != 20
            or set(development) & set(holdout)
            or set(development) | set(holdout) != ids):
        raise ValueError("SPLIT_QUESTION_IDS_MISMATCH")
    by_id = {item["id"]: item for item in candidates}
    split_by_id = {question_id: "development" for question_id in development}
    split_by_id.update({question_id: "holdout" for question_id in holdout})
    groups_by_split = {
        split: sorted({by_id[question_id]["leakage_group"] for question_id in members})
        for split, members in (("development", development), ("holdout", holdout))
    }
    recorded_groups = split_manifest.get("leakage_groups", {})
    if (groups_by_split["development"] != recorded_groups.get("development")
            or groups_by_split["holdout"] != recorded_groups.get("holdout")
            or set(groups_by_split["development"]) & set(groups_by_split["holdout"])):
        raise ValueError("SPLIT_LEAKAGE_GROUP_MISMATCH")
    return split_by_id


def _verify_review(review, *, dataset_id, source_manifest_sha256,
                   candidates_sha256, candidates, source_root):
    if not isinstance(review, dict) or review.get("status") != "human_reviewed":
        raise ValueError("ANNOTATIONS_NOT_HUMAN_REVIEWED")
    if (review.get("review_version") != 1
            or review.get("dataset_id") != dataset_id
            or review.get("source_manifest_sha256") != source_manifest_sha256
            or review.get("candidate_questions_sha256") != candidates_sha256):
        raise ValueError("REVIEW_SOURCE_DIGEST_MISMATCH")
    reviewer = review.get("reviewer")
    if (not isinstance(reviewer, dict) or set(reviewer) != {"id", "reviewed_at"}
            or not isinstance(reviewer["id"], str) or not reviewer["id"].strip()
            or not isinstance(reviewer["reviewed_at"], str)):
        raise ValueError("REVIEWER_METADATA_REQUIRED")
    try:
        reviewed_at = datetime.fromisoformat(reviewer["reviewed_at"].replace("Z", "+00:00"))
    except ValueError as invalid:
        raise ValueError("REVIEW_TIMESTAMP_INVALID") from invalid
    if reviewed_at.tzinfo is None or reviewed_at.utcoffset() is None:
        raise ValueError("REVIEW_TIMESTAMP_INVALID")

    annotations = review.get("annotations")
    if not isinstance(annotations, list) or len(annotations) != len(candidates):
        raise ValueError("REVIEW_QUESTION_SET_MISMATCH")
    candidate_by_id = {item["id"]: item for item in candidates}
    annotation_ids = [item.get("id") for item in annotations if isinstance(item, dict)]
    if (len(annotation_ids) != len(annotations)
            or len(set(annotation_ids)) != len(annotation_ids)
            or set(annotation_ids) != set(candidate_by_id)):
        raise ValueError("REVIEW_QUESTION_SET_MISMATCH")
    for annotation in annotations:
        if (set(annotation) != _candidate_tools.REVIEWED_FIELDS
                or annotation.get("annotation_status") != "reviewed"):
            raise ValueError("ANNOTATIONS_NOT_HUMAN_REVIEWED")
        candidate = candidate_by_id[annotation["id"]]
        if any(annotation[key] != candidate[key]
               for key in ("id", "question", "leakage_group", "category")):
            raise ValueError("REVIEW_QUESTION_METADATA_DRIFT")
    _candidate_tools.validate_candidate_questions(annotations, source_root)
    return reviewer, annotations


def finalize(candidates_path, split_manifest_path, review_path, source_root, output_root):
    candidates_path = Path(candidates_path).resolve()
    split_manifest_path = Path(split_manifest_path).resolve()
    review_path = Path(review_path).resolve()
    source_root = Path(source_root).resolve()
    output_root = Path(output_root).resolve()
    if output_root == source_root or source_root in output_root.parents:
        raise ValueError("OUTPUT_MUST_BE_SEPARATE_FROM_CANDIDATE_SOURCE")
    if output_root.exists():
        raise FileExistsError("OUTPUT_DATASET_ALREADY_EXISTS")

    candidates = _read_json(candidates_path)
    source_manifest_path = source_root / "manifest.json"
    manifest_bytes = source_manifest_path.read_bytes().replace(b"\r\n", b"\n")
    source_manifest = json.loads(manifest_bytes)
    source_manifest_sha256 = sha256(manifest_bytes).hexdigest()
    candidates_sha256 = _canonical_sha256(candidates)
    split_manifest = _read_json(split_manifest_path)
    if (not isinstance(candidates, list)
            or any(item.get("annotation_status") != "candidate" for item in candidates)):
        raise ValueError("INVALID_CANDIDATE_SET")
    _candidate_tools.validate_candidate_questions(candidates, source_root)
    split_by_id = _verify_split(candidates, split_manifest, candidates_sha256)
    review = _read_json(review_path)
    reviewer, annotations = _verify_review(
        review, dataset_id=source_manifest["dataset_id"],
        source_manifest_sha256=source_manifest_sha256,
        candidates_sha256=candidates_sha256, candidates=candidates,
        source_root=source_root)

    annotation_by_id = {item["id"]: item for item in annotations}
    questions = []
    for candidate in candidates:
        annotation = annotation_by_id[candidate["id"]]
        questions.append({
            "id": candidate["id"],
            "question": candidate["question"],
            "answerable": annotation["answerable"],
            "reference_answer": annotation["reference_answer"],
            "evidence": annotation["evidence"],
            "split": split_by_id[candidate["id"]],
            "leakage_group": candidate["leakage_group"],
            "category": candidate["category"],
            "annotation_status": "reviewed",
            "annotation": "Human-reviewed reference annotation, not a model prediction or user result.",
        })

    output_manifest = dict(source_manifest)
    output_manifest.update({
        "dataset_id": "qingzhu-seed-v2-reviewed",
        "source_dataset_id": source_manifest["dataset_id"],
        "description": "Human-reviewed reference annotations over the synthetic Qingzhu corpus; not human-user evaluation.",
        "annotation_provenance": {
            "status": "human_reviewed_reference_annotations",
            "reviewer_id": reviewer["id"],
            "reviewed_at": reviewer["reviewed_at"],
            "source_manifest_sha256": source_manifest_sha256,
            "candidate_questions_sha256": candidates_sha256,
            "split_manifest_sha256": sha256(split_manifest_path.read_bytes()).hexdigest(),
        },
    })

    output_root.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=output_root.name + ".tmp-",
                                  dir=output_root.parent))
    try:
        for document in source_manifest["documents"]:
            source = source_root / document["path"]
            target = stage / document["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        _write_json(stage / "manifest.json", output_manifest)
        _write_json(stage / "questions.json", questions)
        _seed_validator.validate(stage)
        stage.rename(output_root)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return {"dataset_id": output_manifest["dataset_id"],
            "question_count": len(questions),
            "split_counts": {"development": 40, "holdout": 20},
            "reviewer_id": reviewer["id"],
            "output": str(output_root)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--source-dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(finalize(args.candidates, args.split_manifest, args.review,
                              args.source_dataset, args.output), ensure_ascii=False))


if __name__ == "__main__":
    main()
