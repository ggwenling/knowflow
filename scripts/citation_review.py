"""Prepare and validate independent citation review worksheets for v2 captures."""
from __future__ import annotations

import argparse
import csv
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import re

from quality_common import ROOT, MODEL, canonical, digest, instant, now, read_json, verify_receipt, write_new

SOURCES = {"development": ROOT / "eval-out/seed-v2-dev-9907aca/review.json",
           "holdout": ROOT / "eval-out/seed-v2-holdout-9907aca/review.json"}
EDITABLE = ["review_support", "review_citation", "review_notes", "reviewer", "reviewed_at"]
IMMUTABLE = ["split", "question_id", "question", "outcome", "answer", "answer_sha256",
             "citation_index", "citation_id", "claim", "source_document", "content_version_id",
             "locator_start", "locator_end", "source_text_sha256", "source_text"]


def worksheet(split, data):
    rows = []
    entries = data.get("entries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("EMPTY_REVIEW")
    seen = set()
    for entry in entries:
        qid = entry["question_id"]
        if qid in seen or entry["outcome"] not in ("answered", "refused"):
            raise ValueError("INVALID_REVIEW_ENTRY")
        seen.add(qid)
        answer = entry["answer"]
        if sha256(answer.encode("utf-8")).hexdigest() != entry["answer_sha256"]:
            raise ValueError("ANSWER_HASH_MISMATCH")
        citations = entry["citations"]
        if (entry["outcome"] == "answered") != bool(citations):
            raise ValueError("INVALID_REVIEW_CITATIONS")
        for index, cite in enumerate(citations or [None]):
            evidence = cite["evidence"] if cite else {}
            source = cite["source_text"] if cite else ""
            if cite and sha256(source.encode("utf-8")).hexdigest() != evidence["text_sha256"]:
                raise ValueError("SOURCE_HASH_MISMATCH")
            row = dict.fromkeys(IMMUTABLE + EDITABLE, "")
            row.update(split=split, question_id=qid, question=entry["question"], outcome=entry["outcome"],
                       answer=answer, answer_sha256=entry["answer_sha256"])
            if cite:
                row.update(citation_index=str(index), citation_id=cite["id"], claim=cite["claim"],
                           source_document=evidence["document_id"], content_version_id=evidence["content_version_id"],
                           locator_start=str(evidence["start"]), locator_end=str(evidence["end"]),
                           source_text_sha256=evidence["text_sha256"], source_text=source)
            rows.append(row)
    return rows


def prepare(out, *, sources=SOURCES, run_id, candidate_sha, expected_counts=None, predictions=None):
    out = Path(out)
    # Refuse existing directories before writing any partial worksheet.
    if out.exists():
        raise ValueError("REVIEW_OUTPUT_EXISTS")
    manual = predictions is not None
    if manual and (not run_id.strip() or not re.fullmatch(r"[0-9a-f]{40}", candidate_sha)):
        raise ValueError("INVALID_REVIEW_CANDIDATE")
    prepared, inputs = {}, {}
    for split, path in sources.items():
        path = Path(path).resolve()
        raw = path.read_bytes()
        review = json.loads(raw)
        prepared[split] = worksheet(split, review)
        spec = {"path": str(path), "sha256": sha256(raw).hexdigest(), "rows": len(prepared[split])}
        if manual:
            prediction_path = Path(predictions[split]).resolve()
            prediction_raw = prediction_path.read_bytes()
            prediction_sha = sha256(prediction_raw).hexdigest()
            prediction = json.loads(prediction_raw)
            if (review["review_version"] != 2 or review["split"] != split
                    or prediction["prediction_version"] != 2 or review["predictions_sha256"] != prediction_sha
                    or any(review[key] != prediction[key] for key in ("dataset_id", "dataset_sha256"))):
                raise ValueError("REVIEW_PREDICTIONS_MISMATCH")
            if prediction["run"]["code_sha"] != candidate_sha:
                raise ValueError("REVIEW_CANDIDATE_MISMATCH")
            spec["predictions"] = {"path": str(prediction_path), "sha256": prediction_sha}
        inputs[split] = spec
    if expected_counts and {k: len(v) for k, v in prepared.items()} != expected_counts:
        raise ValueError("REVIEW_ROW_COUNT_MISMATCH")
    manifest = {"version": 1, "run_id": run_id, "candidate_sha": candidate_sha, "created_at": now(),
                "reviewer_kind": "manual" if manual else "automated", "sources": inputs}
    if not manual:
        manifest["required_model"] = MODEL
    out.mkdir(parents=True)
    for split, rows in prepared.items():
        with (out / (split + ".csv")).open("x", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=IMMUTABLE + EDITABLE)
            writer.writeheader()
            writer.writerows(rows)
    write_new(out / "manifest.json", manifest)
    report = {"status": "PREPARED", "rows": {k: len(v) for k, v in prepared.items()}}
    if manual:
        report["manifest_sha256"] = digest(out / "manifest.json")
    return report


def original_review(spec):
    raw = Path(spec["path"]).read_bytes()
    if sha256(raw).hexdigest() != spec["sha256"]:
        raise ValueError("ORIGINAL_REVIEW_CHANGED")
    return json.loads(raw)


def validate(directory, *, receipt=None, candidate_sha=None, manifest_sha256=None):
    directory = Path(directory)
    manual = candidate_sha is not None or manifest_sha256 is not None
    raw = (directory / "manifest.json").read_bytes()
    if manual:
        if receipt is not None or not re.fullmatch(r"[0-9a-f]{40}", candidate_sha or ""):
            raise ValueError("INVALID_REVIEW_CANDIDATE")
        if sha256(raw).hexdigest() != manifest_sha256:
            raise ValueError("REVIEW_MANIFEST_CHANGED")
    manifest = json.loads(raw)
    if manifest.get("reviewer_kind") != ("manual" if manual else "automated"):
        raise ValueError("REVIEW_MODE_MISMATCH")
    if manual and manifest["candidate_sha"] != candidate_sha:
        raise ValueError("REVIEW_CANDIDATE_MISMATCH")
    problems, reports, completed = [], {}, {}
    for split in ("development", "holdout"):
        spec = manifest["sources"][split]
        expected = worksheet(split, original_review(spec))
        if manual and digest(spec["predictions"]["path"]) != spec["predictions"]["sha256"]:
            raise ValueError("ORIGINAL_PREDICTIONS_CHANGED")
        csv_bytes = (directory / (split + ".csv")).read_bytes()
        reader = csv.DictReader(StringIO(csv_bytes.decode("utf-8-sig"), newline=""))
        if reader.fieldnames != IMMUTABLE + EDITABLE:
            raise ValueError("INVALID_WORKSHEET_HEADERS")
        rows = list(reader)
        if len(rows) != len(expected) or len(rows) != spec["rows"]:
            problems.append(f"{split}: row count mismatch")
        consistent = {}
        filled = 0
        for index, (row, base) in enumerate(zip(rows, expected), 2):
            before = len(problems)
            where = f"{split}:{index}"
            if None in row or None in row.values():
                problems.append(where + ": invalid worksheet row width")
            if any(row.get(k) != base[k] for k in IMMUTABLE):
                problems.append(where + ": immutable fields changed, reordered or duplicated")
            answered = base["outcome"] == "answered"
            support = {"supported", "not_supported"} if answered else {"refusal_correct", "refusal_incorrect"}
            if row.get("review_support") not in support:
                problems.append(where + ": final support decision required")
            if row.get("review_citation") not in ({"correct", "incorrect"} if answered else {""}):
                problems.append(where + ": final citation decision required")
            if not isinstance(row.get("review_notes"), str) or len(row["review_notes"].strip()) < 10:
                problems.append(where + ": substantive notes required")
            reviewer = row.get("reviewer") or ""
            if manual:
                if not reviewer.strip() or reviewer.strip().casefold().startswith("agent:"):
                    problems.append(where + ": human reviewer identity required")
            elif not reviewer.startswith("agent:" + MODEL + ":V:"):
                problems.append(where + ": automated reviewer identity required")
            try:
                if instant(row.get("reviewed_at")) > instant(now()):
                    raise ValueError("FUTURE_TIMESTAMP")
            except (ValueError, TypeError):
                problems.append(where + ": invalid review time")
            identity = (row.get("review_support"), row.get("reviewer"))
            if manual:
                identity += (row.get("reviewed_at"),)
            prior = consistent.setdefault(base["question_id"], identity)
            if identity != prior:
                problems.append(where + ": inconsistent answer-level decision")
            if before == len(problems):
                filled += 1
        reports[split] = {"rows": len(rows), "filled": filled,
                          "coverage": filled / len(expected) if expected else 0}
        if manual:
            reports[split]["worksheet_sha256"] = sha256(csv_bytes).hexdigest()
        completed[split] = rows
    if not manual and receipt is None:
        problems.append("trusted reviewer receipt required")
    elif not manual:
        verified = verify_receipt(receipt, role="V", run_id=manifest["run_id"],
            candidate_sha=manifest["candidate_sha"], artifact_root=directory,
            artifacts=["manifest.json", "development.csv", "holdout.csv"])
        reviewer = "agent:" + MODEL + ":V:" + verified["session_id"]
        if any(row.get("reviewer") != reviewer for rows in completed.values() for row in rows):
            problems.append("worksheet reviewer does not match execution receipt")
    status = "INCOMPLETE" if problems else "COMPLETE" if manual else "PASS"
    return {"status": status, "splits": reports,
            "problems": problems, "problem_count": len(problems)}, completed, manifest


def reviewed_bundles(completed, manifest):
    bundles = {}
    for split, rows in completed.items():
        bundle = original_review(manifest["sources"][split])
        grouped = {}
        for row in rows:
            grouped.setdefault(row["question_id"], []).append(row)
        for entry in bundle["entries"]:
            selected = grouped[entry["question_id"]]
            entry["reviewed_by"] = selected[0]["reviewer"]
            entry["reviewed_at"] = selected[0]["reviewed_at"]
            if entry["outcome"] == "answered":
                entry["support_judgement"] = "supported" if selected[0]["review_support"] == "supported" else "unsupported"
                for cite, row in zip(entry["citations"], selected, strict=True):
                    cite["judgement"] = "supported" if row["review_citation"] == "correct" else "unsupported"
        bundles[split] = bundle
    return bundles


def verify_exports(directory, *, receipt):
    report, completed, manifest = validate(directory, receipt=receipt)
    if report["status"] != "PASS":
        raise ValueError("REVIEW_INCOMPLETE")
    for split, expected in reviewed_bundles(completed, manifest).items():
        target = Path(directory) / (split + ".review.gpt-6.1-sol.json")
        if canonical(read_json(target)) != canonical(expected):
            raise ValueError("EXPORTED_REVIEW_WORKSHEET_MISMATCH")
    return report


def export_reviews(directory, *, receipt):
    return export_validated(directory, validate(directory, receipt=receipt), receipt=receipt)


def export_validated(directory, validated, *, receipt, manifest_sha256=None):
    report, completed, manifest = validated
    manual = manifest["reviewer_kind"] == "manual"
    if report["status"] != ("COMPLETE" if manual else "PASS"):
        raise ValueError("REVIEW_INCOMPLETE")
    bundles = reviewed_bundles(completed, manifest)
    suffix = "manual" if manual else MODEL
    targets = {split: Path(directory) / f"{split}.review.{suffix}.json" for split in bundles}
    if any(p.exists() for p in [*targets.values(), Path(directory) / "review-audit.json"]):
        raise FileExistsError("REVIEW_EXPORT_EXISTS")
    outputs = {}
    for split, bundle in bundles.items():
        target = targets[split]
        write_new(target, bundle)
        outputs[split] = {"file": target.name, "sha256": digest(target)}
    audit = {"outputs": outputs, "validation": report}
    if manual:
        audit.update(reviewer_kind="manual", run_id=manifest["run_id"], candidate_sha=manifest["candidate_sha"],
                     manifest_sha256=manifest_sha256)
    else:
        audit.update(manifest_sha256=digest(Path(directory) / "manifest.json"), receipt_sha256=digest(receipt))
    write_new(Path(directory) / "review-audit.json", audit)
    return outputs


def prepare_main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--development", type=Path)
    parser.add_argument("--holdout", type=Path)
    parser.add_argument("--manual", action="store_true", help="Prepare a new public capture for human review")
    parser.add_argument("--development-predictions", type=Path)
    parser.add_argument("--holdout-predictions", type=Path)
    parser.add_argument("--current-candidate", action="store_true", help="Use actual row counts for a new capture")
    args = parser.parse_args()
    predictions = None
    if args.manual:
        if not all((args.development, args.holdout, args.development_predictions, args.holdout_predictions)):
            parser.error("--manual requires both review and predictions paths for development and holdout")
        predictions = {"development": args.development_predictions, "holdout": args.holdout_predictions}
    elif args.development_predictions or args.holdout_predictions:
        parser.error("prediction paths require --manual")
    result = prepare(args.out, run_id=args.run_id, candidate_sha=args.candidate_sha,
        sources={"development": args.development or SOURCES["development"],
                 "holdout": args.holdout or SOURCES["holdout"]},
        expected_counts=None if args.current_candidate or args.manual else {"development": 56, "holdout": 30},
        predictions=predictions)
    print(json.dumps(result))
    return 0


def validate_main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--receipt", type=Path)
    mode.add_argument("--manual", action="store_true", help="Validate worksheets completed by a human reviewer")
    parser.add_argument("--candidate-sha", help="Frozen candidate SHA for manual validation")
    parser.add_argument("--manifest-sha256", help="Manifest SHA-256 recorded when preparing manual worksheets")
    parser.add_argument("--export", action="store_true")
    args = parser.parse_args()
    if args.manual and not (args.candidate_sha and args.manifest_sha256):
        parser.error("--manual requires --candidate-sha and --manifest-sha256")
    if not args.manual and (args.candidate_sha or args.manifest_sha256):
        parser.error("--candidate-sha and --manifest-sha256 require --manual")
    validated = validate(args.dir, receipt=args.receipt, candidate_sha=args.candidate_sha,
                         manifest_sha256=args.manifest_sha256)
    report, _, _ = validated
    complete = report["status"] in ("COMPLETE", "PASS")
    if complete and args.export:
        report["outputs"] = export_validated(args.dir, validated, receipt=args.receipt,
                                             manifest_sha256=args.manifest_sha256)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if complete else 1
