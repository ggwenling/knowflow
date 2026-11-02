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
    manifest_path = root / "manifest.json"
    questions_path = root / "questions.json"
    manifest = _read_json(manifest_path)
    questions = _read_json(questions_path)
    required_question_fields = {
        "id", "question", "answerable", "reference_answer", "evidence",
        "split", "leakage_group",
    }
    if (not isinstance(questions, list) or not questions
            or any(not isinstance(item, dict) for item in questions)
            or any(
                not required_question_fields <= item.keys()
                or type(item.get("answerable")) is not bool
                or not isinstance(item.get("reference_answer"), str)
                or not item["reference_answer"].strip()
                or not isinstance(item.get("evidence"), list)
                or item.get("split") not in ("development", "holdout")
                or item.get("annotation_status") not in (None, "reviewed")
                for item in questions
            )):
        raise ValueError("DATASET_ANNOTATIONS_PENDING")
    validator_path = ROOT / "evaluation" / "data" / "tools" / "validate_seed.py"
    spec = importlib.util.spec_from_file_location("seed_validation", validator_path)
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    validator.validate(root)
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


def evaluate(predictions_path, *, split="development", dataset_root=DEFAULT_DATASET,
             quality_config_path=None, review_path=None):
    initial = _read_json(predictions_path)
    if isinstance(initial, dict) and initial.get("prediction_version") == 2:
        spec = importlib.util.spec_from_file_location("runner_v2", Path(__file__).with_name("runner_v2.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.evaluate(predictions_path, split=split, dataset_root=dataset_root,
                               quality_config_path=quality_config_path, review_path=review_path)
    if review_path is not None:
        raise ValueError("V1_REVIEW_PATH_UNSUPPORTED")
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
    evidence_hits_at_5 = 0
    reciprocal_rank_sum = reciprocal_rank_count = 0
    answerability_correct = answerable_count = answerable_answered = 0
    answered_count = 0
    supported_answers = reviewed_answers = 0
    unanswerable_count = unanswerable_refused = 0
    cited_total = cited_gold_overlap = 0
    question_results = []
    category_stats = {}
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
        category = question.get("category", "uncategorized")
        category_stats.setdefault(category, {
            "sample_count": 0, "answerability_correct_count": 0,
            "answerable_count": 0, "answerable_answered_count": 0,
            "unanswerable_count": 0, "unanswerable_refused_count": 0,
        })
        category_result = category_stats[category]
        category_result["sample_count"] += 1
        if not question["answerable"] and prediction["has_answer"] and judgement == "supported":
            raise ValueError("UNANSWERABLE_MARKED_SUPPORTED")
        if prediction["has_answer"]:
            answered_count += 1
            if judgement in ("supported", "unsupported"):
                reviewed_answers += 1
                supported_answers += judgement == "supported"
        gold = question["evidence"]
        hits = sum(_covered(item, retrieved) for item in gold)
        hits_at_5 = sum(_covered(item, retrieved[:5]) for item in gold)
        evidence_hits_at_5 += hits_at_5
        evidence_total += len(gold)
        evidence_hits += hits
        full_evidence_questions += bool(gold) and hits == len(gold)
        if question["answerable"] and gold:
            reciprocal_rank_count += 1
            rank = next((index for index, candidate in enumerate(retrieved[:10], 1)
                         if any(_covered(item, [candidate]) for item in gold)), None)
            if rank is not None:
                reciprocal_rank_sum += 1 / rank
        if question["answerable"]:
            answerable_count += 1
            answerable_answered += prediction["has_answer"]
            category_result["answerable_count"] += 1
            category_result["answerable_answered_count"] += prediction["has_answer"]
        else:
            unanswerable_count += 1
            unanswerable_refused += not prediction["has_answer"]
            category_result["unanswerable_count"] += 1
            category_result["unanswerable_refused_count"] += not prediction["has_answer"]
        correct_answerability = prediction["has_answer"] == question["answerable"]
        answerability_correct += correct_answerability
        category_result["answerability_correct_count"] += correct_answerability
        cited_hits = 0
        for index in citations:
            cited_total += 1
            cited_hits += any(_covered(item, [retrieved[index]]) for item in gold)
        cited_gold_overlap += cited_hits
        latencies.append(float(latency))
        received[prediction["question_id"]] = True
        question_results.append({
            "question_id": question["id"],
            "category": category,
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
    for values in category_stats.values():
        values["answerability_accuracy"] = round(
            values["answerability_correct_count"] / values["sample_count"], 4)
        if values["answerable_count"]:
            values["answerable_answer_rate"] = round(
                values["answerable_answered_count"] / values["answerable_count"], 4)
        else:
            values["answerable_answer_rate"] = None
        if values["unanswerable_count"]:
            values["unanswerable_refusal_rate"] = round(
                values["unanswerable_refused_count"] / values["unanswerable_count"], 4)
        else:
            values["unanswerable_refusal_rate"] = None
    report = {
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
            "recall_at_5": round(evidence_hits_at_5 / evidence_total, 4)
            if evidence_total else None,
            "mrr_at_10": round(reciprocal_rank_sum / reciprocal_rank_count, 4)
            if reciprocal_rank_count else None,
            "mrr_at_10_question_count": reciprocal_rank_count,
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
            "by_category": dict(sorted(category_stats.items())),
        },
        "interpretation": {
            "support_judgement": "manual input; citations or string matching do not prove semantic support",
            "latency": "provided by the prediction producer; this runner does not time providers",
            "acceptance_threshold": "not registered; no pass/fail quality claim is made",
        },
    }
    if quality_config_path is None:
        report["quality_gate"] = {"status": "incomplete", "reason": "QUALITY_CONFIG_MISSING"}
    else:
        config = _read_json(quality_config_path)
        if (not isinstance(config, dict)
                or set(config) != {"gate_version", "dataset_id", "dataset_sha256", "minimums"}
                or type(config["gate_version"]) is not int or config["gate_version"] != 1
                or config["dataset_id"] != manifest["dataset_id"]
                or config["dataset_sha256"] != dataset_sha
                or not isinstance(config["minimums"], dict)
                or not config["minimums"]
                or set(config["minimums"]) - {
                    "answerability_accuracy", "gold_evidence_span_recall", "recall_at_5",
                    "mrr_at_10", "answerable_answer_rate", "unanswerable_refusal_rate",
                    "human_support_review_coverage", "human_supported_answer_rate",
                    "cited_gold_span_overlap_rate"}):
            raise ValueError("INVALID_QUALITY_CONFIG")
        checks = {}
        failed = False
        incomplete = False
        for metric, minimum in sorted(config["minimums"].items()):
            if (type(minimum) not in (int, float) or not math.isfinite(minimum)
                    or not 0 <= minimum <= 1):
                raise ValueError("INVALID_QUALITY_CONFIG")
            observed = report["metrics"].get(metric)
            passed = observed is not None and observed >= minimum
            checks[metric] = {"minimum": minimum, "observed": observed,
                              "status": "passed" if passed else
                              "incomplete" if observed is None else "failed"}
            failed |= observed is not None and not passed
            incomplete |= observed is None
        report["quality_gate"] = {
            "status": "failed" if failed else "incomplete" if incomplete else "passed",
            "gate_version": config["gate_version"], "checks": checks,
        }
        report["interpretation"]["acceptance_threshold"] = (
            "explicit dataset-bound thresholds applied; not independent user-quality approval")
    report["formal_acceptance"] = {"status": "incomplete", "reason": "V1_NO_SEMANTIC_CITATION_REVIEW"}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--split", choices=("development", "holdout"), default="development")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--quality-config", type=Path)
    parser.add_argument("--review", type=Path, help="Version 2 human review bundle")
    parser.add_argument("--formal", action="store_true", help="Require a complete version 2 formal quality gate")
    args = parser.parse_args()
    report = evaluate(args.predictions, split=args.split, dataset_root=args.dataset,
                      quality_config_path=args.quality_config, review_path=args.review)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"split": report["split"], "sample_count": report["sample_count"]}))
    if ((args.formal and (report.get("report_version") != 2 or report["quality_gate"]["status"] != "passed"))
            or (args.quality_config is not None and report["quality_gate"]["status"] != "passed")):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
