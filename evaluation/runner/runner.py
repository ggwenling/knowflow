"""Score saved predictions against the synthetic seed without provider calls."""
import argparse
from hashlib import sha256
import importlib.util
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = ROOT / "evaluation" / "data" / "seed-v1"


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _fingerprint(manifest_path, questions_path):
    return sha256(Path(manifest_path).read_bytes() + b"\0"
                  + Path(questions_path).read_bytes()).hexdigest()


def _load_dataset(dataset_root):
    root = Path(dataset_root).resolve()
    validator_path = ROOT / "evaluation" / "data" / "tools" / "validate_seed.py"
    spec = importlib.util.spec_from_file_location("seed_validation", validator_path)
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    validator.validate(root)
    manifest_path = root / "manifest.json"
    questions_path = root / "questions.json"
    manifest = _read_json(manifest_path)
    questions = _read_json(questions_path)
    if manifest.get("synthetic") is not True or not isinstance(questions, list):
        raise ValueError("UNSUPPORTED_DATASET")
    documents = {}
    sources = {}
    for document in manifest["documents"]:
        path = (root / document["path"]).resolve()
        if not path.is_relative_to(root):
            raise ValueError("DATASET_PATH_OUTSIDE_ROOT")
        raw = path.read_bytes()
        source = raw.decode("utf-8")
        if sha256(raw).hexdigest() != document["sha256"]:
            raise ValueError("DATASET_SOURCE_HASH_MISMATCH")
        documents[document["id"]] = document
        sources[document["id"]] = source
    return manifest, questions, documents, sources, _fingerprint(manifest_path, questions_path)


def _validate_span(span, documents, sources):
    if (not isinstance(span, dict)
            or set(span) != {"document_id", "content_version_id", "start", "end",
                             "text_sha256"}
            or not isinstance(span["document_id"], str)
            or span["document_id"] not in documents
            or not isinstance(span["content_version_id"], str)
            or type(span["start"]) is not int or type(span["end"]) is not int
            or span["content_version_id"] != documents[span["document_id"]]["content_version_id"]):
        raise ValueError("INVALID_EVIDENCE_SPAN")
    source = sources[span["document_id"]]
    if (not 0 <= span["start"] < span["end"] <= len(source)
            or sha256(source[span["start"]:span["end"]].encode("utf-8")).hexdigest()
            != span["text_sha256"]):
        raise ValueError("INVALID_EVIDENCE_SPAN")


def _covered(gold, retrieved):
    return any(item["document_id"] == gold["document_id"]
               and item["content_version_id"] == gold["content_version_id"]
               and item["start"] <= gold["start"] and item["end"] >= gold["end"]
               for item in retrieved)


def _percentile(values, percentile):
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return round(ordered[index], 2)


def evaluate(predictions_path, *, split="development", dataset_root=DEFAULT_DATASET):
    if split not in ("development", "holdout"):
        raise ValueError("INVALID_SPLIT")
    manifest, questions, documents, sources, dataset_sha = _load_dataset(dataset_root)
    selected = [item for item in questions if item["split"] == split]
    if not selected:
        raise ValueError("EMPTY_SPLIT")
    expected = {item["id"]: item for item in selected}
    payload = _read_json(predictions_path)
    if (not isinstance(payload, dict)
            or set(payload) != {"dataset_id", "dataset_sha256", "predictions"}
            or payload["dataset_id"] != manifest["dataset_id"]
            or payload["dataset_sha256"] != dataset_sha
            or not isinstance(payload["predictions"], list)):
        raise ValueError("PREDICTION_DATASET_MISMATCH")

    received = {}
    latencies = []
    evidence_total = evidence_hits = full_evidence_questions = 0
    answerability_correct = answerable_count = answerable_answered = 0
    answered_count = 0
    supported_answers = reviewed_answers = 0
    unanswerable_count = unanswerable_refused = 0
    cited_total = cited_gold_overlap = 0
    question_results = []
    for prediction in payload["predictions"]:
        if (not isinstance(prediction, dict)
                or set(prediction) != {"question_id", "has_answer", "retrieved_evidence",
                                       "cited_evidence", "support_judgement", "latency_ms"}
                or not isinstance(prediction["question_id"], str)
                or prediction["question_id"] not in expected
                or prediction["question_id"] in received):
            raise ValueError("INVALID_PREDICTION")
        if type(prediction["has_answer"]) is not bool:
            raise ValueError("INVALID_PREDICTION")
        judgement = prediction["support_judgement"]
        if judgement not in ("supported", "unsupported", "unreviewed", "not_applicable"):
            raise ValueError("INVALID_SUPPORT_JUDGEMENT")
        if not prediction["has_answer"] and judgement not in ("unreviewed", "not_applicable"):
            raise ValueError("INVALID_SUPPORT_JUDGEMENT")
        retrieved = prediction["retrieved_evidence"]
        citations = prediction["cited_evidence"]
        if not isinstance(retrieved, list) or not isinstance(citations, list):
            raise ValueError("INVALID_PREDICTION")
        for span in retrieved:
            _validate_span(span, documents, sources)
        if (any(type(index) is not int or not 0 <= index < len(retrieved) for index in citations)
                or len(set(citations)) != len(citations)):
            raise ValueError("INVALID_CITATION_INDEX")
        latency = prediction["latency_ms"]
        if type(latency) not in (int, float) or not math.isfinite(latency) or latency < 0:
            raise ValueError("INVALID_LATENCY")

        question = expected[prediction["question_id"]]
        if not question["answerable"] and prediction["has_answer"] and judgement == "supported":
            raise ValueError("UNANSWERABLE_MARKED_SUPPORTED")
        if prediction["has_answer"]:
            answered_count += 1
            if judgement in ("supported", "unsupported"):
                reviewed_answers += 1
                supported_answers += judgement == "supported"
        gold = question["evidence"]
        hits = sum(_covered(item, retrieved) for item in gold)
        evidence_total += len(gold)
        evidence_hits += hits
        full_evidence_questions += bool(gold) and hits == len(gold)
        if question["answerable"]:
            answerable_count += 1
            answerable_answered += prediction["has_answer"]
        else:
            unanswerable_count += 1
            unanswerable_refused += not prediction["has_answer"]
        correct_answerability = prediction["has_answer"] == question["answerable"]
        answerability_correct += correct_answerability
        cited_hits = 0
        for index in citations:
            cited_total += 1
            cited_hits += any(_covered(item, [retrieved[index]]) for item in gold)
        cited_gold_overlap += cited_hits
        latencies.append(float(latency))
        received[prediction["question_id"]] = True
        question_results.append({
            "question_id": question["id"],
            "answerable": question["answerable"],
            "has_answer": prediction["has_answer"],
            "answerability_correct": correct_answerability,
            "gold_evidence_hits": hits,
            "gold_evidence_count": len(gold),
            "complete_gold_evidence_retrieved": bool(gold) and hits == len(gold),
            "support_judgement": judgement,
            "cited_gold_span_overlaps": cited_hits,
            "citation_count": len(citations),
            "latency_ms": float(latency),
        })

    missing = set(expected) - set(received)
    if missing:
        raise ValueError("MISSING_PREDICTIONS")
    return {
        "report_version": 1,
        "dataset_id": manifest["dataset_id"],
        "dataset_sha256": dataset_sha,
        "dataset_provenance": "synthetic authored seed; not human-user evaluation",
        "split": split,
        "sample_count": len(selected),
        "question_results": sorted(question_results, key=lambda item: item["question_id"]),
        "metrics": {
            "answerable_question_count": answerable_count,
            "unanswerable_question_count": unanswerable_count,
            "answerability_accuracy": round(answerability_correct / len(selected), 4),
            "gold_evidence_span_count": evidence_total,
            "gold_evidence_span_hit_count": evidence_hits,
            "gold_evidence_span_recall": round(evidence_hits / evidence_total, 4)
            if evidence_total else None,
            "answerable_questions_with_evidence_count": sum(
                bool(item["evidence"]) for item in selected),
            "complete_gold_evidence_question_rate": round(
                full_evidence_questions / sum(bool(item["evidence"]) for item in selected), 4)
            if any(item["evidence"] for item in selected) else None,
            "answerable_questions_answered_count": answerable_answered,
            "questions_answered_count": answered_count,
            "answerable_answer_rate": round(answerable_answered / answerable_count, 4)
            if answerable_count else None,
            "unanswerable_questions_refused_count": unanswerable_refused,
            "unanswerable_refusal_rate": round(unanswerable_refused / unanswerable_count, 4)
            if unanswerable_count else None,
            "human_support_reviewed_answer_count": reviewed_answers,
            "human_support_review_coverage": round(reviewed_answers / answered_count, 4)
            if answered_count else None,
            "human_supported_answer_rate": round(supported_answers / reviewed_answers, 4)
            if reviewed_answers else None,
            "cited_gold_span_overlap_rate": round(cited_gold_overlap / cited_total, 4)
            if cited_total else None,
            "citation_count": cited_total,
            "latency_ms": {"sample_count": len(latencies),
                           "p50_nearest_rank": _percentile(latencies, 0.50),
                           "p95_nearest_rank": _percentile(latencies, 0.95)},
        },
        "interpretation": {
            "support_judgement": "manual input; citations or string matching do not prove semantic support",
            "latency": "provided by the prediction producer; this runner does not time providers",
            "acceptance_threshold": "not registered; no pass/fail quality claim is made",
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--split", choices=("development", "holdout"), default="development")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = evaluate(args.predictions, split=args.split, dataset_root=args.dataset)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"split": report["split"], "sample_count": report["sample_count"]}))


if __name__ == "__main__":
    main()
