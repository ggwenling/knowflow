"""Validate candidate annotations and assign leakage groups to a 40/20 split."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import random

QUESTION_CATEGORIES = {"factual", "rewrite", "multi_evidence",
                       "chinese_keyword", "no_answer"}
REVIEWED_FIELDS = {"id", "question", "leakage_group", "annotation_status", "category",
                   "answerable", "reference_answer", "evidence"}
CANDIDATE_FIELDS = {"id", "question", "leakage_group", "annotation_status", "category"}
EVIDENCE_FIELDS = {"document_id", "content_version_id", "start", "end", "unit",
                   "quote", "line_start", "line_end"}


def validate_candidate_questions(questions, dataset_root):
    root = Path(dataset_root).resolve()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    documents = {}
    for item in manifest["documents"]:
        path = (root / item["path"]).resolve()
        if not path.is_relative_to(root):
            raise ValueError("DATASET_PATH_OUTSIDE_ROOT")
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        if sha256(raw).hexdigest() != item["sha256"]:
            raise ValueError("DATASET_SOURCE_HASH_MISMATCH")
        documents[item["id"]] = (item, text)

    if not isinstance(questions, list) or not questions:
        raise ValueError("EMPTY_CANDIDATE_SET")
    ids = set()
    groups = {}
    counts = {"candidate": 0, "reviewed": 0}
    for question in questions:
        if not isinstance(question, dict):
            raise ValueError("INVALID_CANDIDATE")
        status = question.get("annotation_status")
        if not isinstance(status, str):
            raise ValueError("INVALID_CANDIDATE")
        expected_fields = CANDIDATE_FIELDS if status == "candidate" else REVIEWED_FIELDS
        if (status not in counts or set(question) != expected_fields
                or not isinstance(question["id"], str) or not question["id"]
                or question["id"] in ids
                or not isinstance(question["question"], str) or not question["question"].strip()
                or not isinstance(question["leakage_group"], str)
                or not question["leakage_group"]
                or not isinstance(question["category"], str)
                or question["category"] not in QUESTION_CATEGORIES):
            raise ValueError("INVALID_CANDIDATE")
        ids.add(question["id"])
        counts[status] += 1
        groups.setdefault(question["leakage_group"], []).append(question["id"])
        if status == "candidate":
            continue
        if (type(question["answerable"]) is not bool
                or not isinstance(question["reference_answer"], str)
                or not question["reference_answer"].strip()
                or not isinstance(question["evidence"], list)
                or bool(question["evidence"]) != question["answerable"]):
            raise ValueError("INVALID_ANNOTATION")
        for evidence in question["evidence"]:
            if (not isinstance(evidence, dict) or set(evidence) != EVIDENCE_FIELDS
                    or not isinstance(evidence["document_id"], str)
                    or evidence["document_id"] not in documents
                    or type(evidence["start"]) is not int or type(evidence["end"]) is not int
                    or type(evidence["line_start"]) is not int
                    or type(evidence["line_end"]) is not int
                    or evidence["unit"] != "unicode_code_point"):
                raise ValueError("INVALID_ANNOTATION_EVIDENCE")
            document, source = documents[evidence["document_id"]]
            start, end = evidence["start"], evidence["end"]
            if (evidence["content_version_id"] != document["content_version_id"]
                    or not 0 <= start < end <= len(source)
                    or source[start:end] != evidence["quote"]
                    or source.count("\n", 0, start) + 1 != evidence["line_start"]
                    or source.count("\n", 0, end) + 1 != evidence["line_end"]):
                raise ValueError("INVALID_ANNOTATION_EVIDENCE")
    return {"question_count": len(questions), "leakage_group_count": len(groups),
            "annotation_status_counts": counts, "groups": groups}


def assign_splits(questions, *, development_count=40, holdout_count=20, seed=20261031):
    if (type(development_count) is not int or type(holdout_count) is not int
            or development_count < 1 or holdout_count < 1
            or len(questions) != development_count + holdout_count):
        raise ValueError("CANDIDATE_SPLIT_COUNT_MISMATCH")
    groups = {}
    for question in questions:
        groups.setdefault(question["leakage_group"], []).append(question["id"])
    group_names = sorted(groups)
    random.Random(seed).shuffle(group_names)

    # Find a whole-group subset that fills the reserved holdout exactly.
    reachable = {0: ()}
    for group in group_names:
        size = len(groups[group])
        for count in sorted(reachable, reverse=True):
            target = count + size
            if target <= holdout_count and target not in reachable:
                reachable[target] = reachable[count] + (group,)
    if holdout_count not in reachable:
        raise ValueError("LEAKAGE_GROUPS_CANNOT_FILL_HOLDOUT")
    holdout_groups = set(reachable[holdout_count])
    holdout_ids = sorted(question["id"] for question in questions
                         if question["leakage_group"] in holdout_groups)
    development_ids = sorted(set(question["id"] for question in questions) - set(holdout_ids))
    return {"development": development_ids, "holdout": holdout_ids,
            "development_groups": sorted(set(group_names) - holdout_groups),
            "holdout_groups": sorted(holdout_groups)}


def prepare(questions, dataset_root, *, development_count=40,
            holdout_count=20, seed=20261031):
    validation = validate_candidate_questions(questions, dataset_root)
    split = assign_splits(questions, development_count=development_count,
                          holdout_count=holdout_count, seed=seed)
    canonical = json.dumps(questions, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":")).encode("utf-8")
    return {
        "split_manifest_version": 1,
        "status": "candidate_allocation_not_a_blind_holdout",
        "input_sha256": sha256(canonical).hexdigest(),
        "seed": seed,
        "target_counts": {"development": development_count, "holdout": holdout_count},
        "validation": {key: value for key, value in validation.items() if key != "groups"},
        "question_ids": {"development": split["development"], "holdout": split["holdout"]},
        "leakage_groups": {"development": split["development_groups"],
                            "holdout": split["holdout_groups"]},
        "questions_marked_reviewed_count": validation["annotation_status_counts"]["reviewed"],
    }


def annotation_template(candidate_questions, dataset_root):
    """Prepare blank annotations; the unfinished records fail split validation."""
    root = Path(dataset_root).resolve()
    manifest_bytes = (root / "manifest.json").read_bytes().replace(b"\r\n", b"\n")
    manifest = json.loads(manifest_bytes)
    validate_candidate_questions(candidate_questions, dataset_root)
    return {
        "template_version": 1,
        "status": "pending_annotations_not_a_blind_holdout",
        "dataset_id": manifest["dataset_id"],
        "source_manifest_sha256": sha256(manifest_bytes).hexdigest(),
        "question_count": len(candidate_questions),
        "questions_marked_reviewed_count": 0,
        "source_catalog": [{key: item[key] for key in
                            ("id", "path", "content_version_id", "sha256")}
                           for item in manifest["documents"]],
        "annotations": [{"id": item["id"], "question": item["question"],
                         "leakage_group": item["leakage_group"], "category": item["category"],
                         "annotation_status": "pending", "answerable": None,
                         "reference_answer": "", "evidence": []}
                        for item in candidate_questions],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=20261031)
    parser.add_argument("--annotation-template", action="store_true")
    args = parser.parse_args()
    questions = json.loads(args.input.read_text(encoding="utf-8"))
    result = (annotation_template(questions, args.dataset) if args.annotation_template
              else prepare(questions, args.dataset, seed=args.seed))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    summary = ({"question_count": result["question_count"], "status": result["status"]}
               if args.annotation_template else result["validation"])
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
