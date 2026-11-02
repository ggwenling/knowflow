"""Version 2 offline scoring and human review of captured RAG runs."""
import importlib.util
import json
import math
import re
from datetime import datetime
from hashlib import sha256
from pathlib import Path

_spec = importlib.util.spec_from_file_location("legacy_runner", Path(__file__).with_name("runner.py"))
legacy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(legacy)

MINIMUMS = {"recall_at_5": 0.85, "mrr_at_10": 0.75,
            "human_supported_answer_rate": 0.90, "citation_accuracy": 0.95,
            "unanswerable_refusal_rate": 0.90, "answerable_answer_rate": 0.90,
            "human_support_review_coverage": 1.0, "citation_review_coverage": 1.0}
SOURCE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", re.ASCII)
MARKER = re.compile(r"\[([A-Za-z0-9][A-Za-z0-9._:-]{0,127})\]", re.ASCII)


def _sha(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _timestamp(value):
    if not isinstance(value, str):
        return False
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.tzinfo is not None and dt.utcoffset() is not None
    except ValueError:
        return False


def _load(predictions_path, dataset_root, split):
    raw = Path(predictions_path).read_bytes()
    payload = json.loads(raw)
    manifest, questions, documents, sources, dataset_sha = legacy._load_dataset(dataset_root)
    if (not isinstance(payload, dict) or set(payload) != {"prediction_version", "dataset_id", "dataset_sha256", "run", "predictions"}
            or type(payload["prediction_version"]) is not int or payload["prediction_version"] != 2
            or payload["dataset_id"] != manifest["dataset_id"] or payload["dataset_sha256"] != dataset_sha
            or not isinstance(payload["predictions"], list)):
        raise ValueError("PREDICTION_DATASET_MISMATCH")
    run = payload["run"]
    if (not isinstance(run, dict) or set(run) != {"code_sha", "schema_sha256", "model", "config_sha256", "prompt_sha256"}
            or not isinstance(run["code_sha"], str) or re.fullmatch(r"[0-9a-f]{40}", run["code_sha"]) is None
            or not all(_sha(run[key]) for key in ("schema_sha256", "config_sha256", "prompt_sha256"))
            or not isinstance(run["model"], str) or not run["model"].strip()):
        raise ValueError("INVALID_RUN_METADATA")
    if split not in ("development", "holdout"):
        raise ValueError("INVALID_SPLIT")
    expected = {q["id"]: q for q in questions if q["split"] == split}
    if not expected:
        raise ValueError("EMPTY_SPLIT")
    received = {}
    for row in payload["predictions"]:
        if (not isinstance(row, dict) or set(row) != {"question_id", "outcome", "answer", "answer_sha256", "retrieved_evidence", "citations", "latency_ms", "error_code"}
                or not isinstance(row["question_id"], str) or row["question_id"] not in expected
                or row["question_id"] in received or row["outcome"] not in ("answered", "refused", "error")
                or not isinstance(row["answer"], str)
                or sha256(row["answer"].encode("utf-8")).hexdigest() != row["answer_sha256"]
                or not isinstance(row["retrieved_evidence"], list) or len(row["retrieved_evidence"]) > 10
                or not isinstance(row["citations"], list)
                or type(row["latency_ms"]) not in (int, float) or not math.isfinite(row["latency_ms"]) or row["latency_ms"] < 0):
            raise ValueError("INVALID_PREDICTION")
        if row["outcome"] in ("answered", "refused") and not row["answer"].strip():
            raise ValueError("INVALID_PREDICTION")
        if row["outcome"] == "error":
            if row["answer"] or not isinstance(row["error_code"], str) or not re.fullmatch(r"[A-Z0-9_]{1,80}", row["error_code"]):
                raise ValueError("INVALID_ERROR_CODE")
        elif row["error_code"] is not None:
            raise ValueError("INVALID_ERROR_CODE")
        if row["outcome"] != "answered" and row["citations"]:
            raise ValueError("INVALID_CITATIONS")
        source_ids = set()
        for span in row["retrieved_evidence"]:
            if (not isinstance(span, dict) or "source_id" not in span
                    or not isinstance(span["source_id"], str) or not SOURCE_ID.fullmatch(span["source_id"])
                    or span["source_id"] in source_ids):
                raise ValueError("INVALID_EVIDENCE_SOURCE_ID")
            source_ids.add(span["source_id"])
            legacy._validate_span({key: value for key, value in span.items() if key != "source_id"}, documents, sources)
        markers = MARKER.findall(row["answer"])
        if "[" in MARKER.sub("", row["answer"]) or "]" in MARKER.sub("", row["answer"]):
            raise ValueError("INVALID_CITATION_MARKER")
        if row["outcome"] != "answered" and markers:
            raise ValueError("INVALID_CITATIONS")
        ids = set()
        positions = set()
        for cite in row["citations"]:
            if (not isinstance(cite, dict) or set(cite) != {"id", "source_id", "marker_index", "evidence_index", "claim"}
                    or not isinstance(cite["id"], str) or not cite["id"].strip() or cite["id"] in ids
                    or type(cite["marker_index"]) is not int or not 0 <= cite["marker_index"] < len(markers)
                    or cite["marker_index"] in positions or cite["source_id"] != markers[cite["marker_index"]]
                    or type(cite["evidence_index"]) is not int
                    or not 0 <= cite["evidence_index"] < min(5, len(row["retrieved_evidence"]))
                    or row["retrieved_evidence"][cite["evidence_index"]]["source_id"] != cite["source_id"]
                    or not isinstance(cite["claim"], str) or not cite["claim"].strip()
                    or cite["claim"] not in row["answer"]):
                raise ValueError("INVALID_CITATIONS")
            ids.add(cite["id"])
            positions.add(cite["marker_index"])
        if row["outcome"] == "answered" and (not markers or len(positions) != len(markers)):
            raise ValueError("INVALID_CITATIONS")
        received[row["question_id"]] = row
    if set(received) != set(expected):
        raise ValueError("MISSING_PREDICTIONS")
    return raw, payload, expected, sources


def prepare_review(predictions_path, dataset_root, split):
    raw, payload, expected, sources = _load(predictions_path, dataset_root, split)
    entries = []
    for row in payload["predictions"]:
        citations = []
        for cite in row["citations"]:
            span = row["retrieved_evidence"][cite["evidence_index"]]
            citations.append({"id": cite["id"], "source_id": cite["source_id"], "marker_index": cite["marker_index"],
                              "claim": cite["claim"], "evidence": span,
                              "source_text": sources[span["document_id"]][span["start"]:span["end"]],
                              "judgement": "unreviewed"})
        entries.append({"question_id": row["question_id"], "question": expected[row["question_id"]]["question"],
                        "outcome": row["outcome"], "answer": row["answer"], "answer_sha256": row["answer_sha256"],
                        "support_judgement": "unreviewed" if row["outcome"] == "answered" else "not_applicable",
                        "reviewed_by": None, "reviewed_at": None, "citations": citations})
    return {"review_version": 2, "dataset_id": payload["dataset_id"], "dataset_sha256": payload["dataset_sha256"],
            "split": split, "predictions_sha256": sha256(raw).hexdigest(), "entries": entries}


def evaluate(predictions_path, *, split, dataset_root, quality_config_path=None, review_path=None):
    raw, payload, expected, sources = _load(predictions_path, dataset_root, split)
    template = prepare_review(predictions_path, dataset_root, split)
    reviews = {}
    if review_path is not None:
        review = json.loads(Path(review_path).read_bytes())
        if (not isinstance(review, dict) or set(review) != set(template)
                or any(review[k] != template[k] for k in template if k != "entries")
                or not isinstance(review["entries"], list) or len(review["entries"]) != len(template["entries"])):
            raise ValueError("REVIEW_INPUT_MISMATCH")
        entries = {e["question_id"]: e for e in review["entries"] if isinstance(e, dict) and "question_id" in e}
        if len(entries) != len(review["entries"]):
            raise ValueError("INVALID_REVIEW_ENTRIES")
        for base in template["entries"]:
            entry = entries.get(base["question_id"])
            if (not isinstance(entry, dict) or set(entry) != set(base)
                    or any(entry[k] != base[k] for k in ("question_id", "question", "outcome", "answer", "answer_sha256"))
                    or not isinstance(entry["citations"], list) or len(entry["citations"]) != len(base["citations"])):
                raise ValueError("REVIEW_INPUT_MISMATCH")
            for actual, citation in zip(entry["citations"], base["citations"], strict=True):
                if (not isinstance(actual, dict) or set(actual) != set(citation)
                        or any(actual[k] != citation[k] for k in citation if k != "judgement")
                        or actual["judgement"] not in ("supported", "unsupported", "unreviewed")):
                    raise ValueError("REVIEW_INPUT_MISMATCH")
            if entry["outcome"] == "answered":
                if entry["support_judgement"] not in ("supported", "unsupported", "unreviewed"):
                    raise ValueError("INVALID_SUPPORT_JUDGEMENT")
                if not expected[entry["question_id"]]["answerable"] and entry["support_judgement"] == "supported":
                    raise ValueError("UNANSWERABLE_MARKED_SUPPORTED")
                if (entry["support_judgement"] != "unreviewed" or any(c["judgement"] != "unreviewed" for c in entry["citations"])) and (
                        not isinstance(entry["reviewed_by"], str) or not entry["reviewed_by"].strip() or not _timestamp(entry["reviewed_at"])):
                    raise ValueError("REVIEWER_METADATA_REQUIRED")
            elif entry["support_judgement"] != "not_applicable":
                raise ValueError("INVALID_SUPPORT_JUDGEMENT")
            reviews[entry["question_id"]] = entry

    answerable = sum(q["answerable"] for q in expected.values())
    unanswerable = len(expected) - answerable
    gold_total = sum(len(q["evidence"]) for q in expected.values())
    gold_hits = reciprocal = answered_count = supported = reviewed = citations_total = citations_reviewed = citations_supported = cited_gold_overlap = 0
    answered_answerable = refused_answerable = refused_unanswerable = errors = 0
    result_rows = []
    categories = {}
    for row in payload["predictions"]:
        q = expected[row["question_id"]]
        ev = row["retrieved_evidence"]
        gold_hits += sum(legacy._covered(g, ev[:5]) for g in q["evidence"])
        if q["answerable"] and q["evidence"]:
            rank = next((i for i, span in enumerate(ev, 1) if any(legacy._covered(g, [span]) for g in q["evidence"])), None)
            if rank: reciprocal += 1 / rank
        outcome = row["outcome"]
        category = q.get("category", "uncategorized")
        category_counts = categories.setdefault(category, {"sample_count": 0, "answered_count": 0,
                                                           "refused_count": 0, "error_count": 0,
                                                           "answerable_count": 0, "unanswerable_count": 0,
                                                           "answerable_answered_count": 0, "unanswerable_refused_count": 0})
        category_counts["sample_count"] += 1
        category_counts[outcome + "_count"] += 1
        category_counts["answerable_count" if q["answerable"] else "unanswerable_count"] += 1
        category_counts["answerable_answered_count"] += q["answerable"] and outcome == "answered"
        category_counts["unanswerable_refused_count"] += not q["answerable"] and outcome == "refused"
        errors += outcome == "error"
        answered_answerable += q["answerable"] and outcome == "answered"
        refused_answerable += q["answerable"] and outcome == "refused"
        refused_unanswerable += not q["answerable"] and outcome == "refused"
        entry = reviews.get(row["question_id"])
        if outcome == "answered":
            answered_count += 1
            if entry and entry["support_judgement"] != "unreviewed":
                reviewed += 1
                supported += entry["support_judgement"] == "supported"
        citations_total += len(row["citations"])
        cited_gold_overlap += sum(any(legacy._covered(g, [ev[cite["evidence_index"]]]) for g in q["evidence"])
                                  for cite in row["citations"])
        if entry:
            citations_reviewed += sum(c["judgement"] != "unreviewed" for c in entry["citations"])
            citations_supported += sum(c["judgement"] == "supported" for c in entry["citations"])
        result_rows.append({"question_id": q["id"], "category": q.get("category", "uncategorized"),
                            "answerable": q["answerable"], "outcome": outcome, "error_code": row["error_code"]})
    ratio = lambda n, d: round(n / d, 4) if d else None
    metrics = {"sample_count": len(expected), "execution_error_count": errors,
               "execution_error_rate": ratio(errors, len(expected)), "gold_evidence_span_count": gold_total,
               "gold_evidence_span_hit_count_at_5": gold_hits, "recall_at_5": ratio(gold_hits, gold_total),
               "mrr_at_10": ratio(reciprocal, answerable), "answerable_question_count": answerable,
               "answerable_answered_count": answered_answerable, "answerable_answer_rate": ratio(answered_answerable, answerable),
               "answerable_refused_count": refused_answerable, "answerable_false_refusal_rate": ratio(refused_answerable, answerable),
               "unanswerable_question_count": unanswerable, "unanswerable_refused_count": refused_unanswerable,
               "unanswerable_refusal_rate": ratio(refused_unanswerable, unanswerable),
               "answered_count": answered_count, "human_supported_answer_count": supported,
               "human_support_reviewed_answer_count": reviewed, "human_supported_answer_rate": ratio(supported, reviewed),
               "human_support_review_coverage": ratio(reviewed, answered_count), "citation_count": citations_total,
               "citation_reviewed_count": citations_reviewed, "citation_supported_count": citations_supported,
               "citation_review_coverage": ratio(citations_reviewed, citations_total), "citation_accuracy": ratio(citations_supported, citations_reviewed),
               "cited_gold_span_overlap_count": cited_gold_overlap, "cited_gold_span_overlap_rate": ratio(cited_gold_overlap, citations_total),
               "by_category": categories,
               "latency_ms": {"p50_nearest_rank": legacy._percentile([r["latency_ms"] for r in payload["predictions"]], 0.5),
                              "p95_nearest_rank": legacy._percentile([r["latency_ms"] for r in payload["predictions"]], 0.95)}}
    gate = {"status": "incomplete", "reason": "QUALITY_CONFIG_MISSING"}
    if quality_config_path is not None:
        config = json.loads(Path(quality_config_path).read_bytes())
        if (not isinstance(config, dict) or set(config) != {"gate_version", "dataset_id", "dataset_sha256", "minimums"}
                or type(config["gate_version"]) is not int or config["gate_version"] != 2
                or config["dataset_id"] != payload["dataset_id"] or config["dataset_sha256"] != payload["dataset_sha256"]
                or not isinstance(config["minimums"], dict) or set(config["minimums"]) != set(MINIMUMS)
                or any(type(config["minimums"][k]) not in (int, float) or not math.isfinite(config["minimums"][k])
                       or not MINIMUMS[k] <= config["minimums"][k] <= 1 for k in MINIMUMS)):
            raise ValueError("INVALID_QUALITY_CONFIG")
        raw_metrics = {"recall_at_5": (gold_hits, gold_total), "mrr_at_10": (reciprocal, answerable),
                       "human_supported_answer_rate": (supported, reviewed), "citation_accuracy": (citations_supported, citations_reviewed),
                       "unanswerable_refusal_rate": (refused_unanswerable, unanswerable), "answerable_answer_rate": (answered_answerable, answerable),
                       "human_support_review_coverage": (reviewed, answered_count), "citation_review_coverage": (citations_reviewed, citations_total)}
        checks = {k: {"minimum": config["minimums"][k], "observed": metrics[k],
                      "status": "incomplete" if not raw_metrics[k][1] else "passed" if raw_metrics[k][0] / raw_metrics[k][1] >= config["minimums"][k] else "failed"}
                  for k in MINIMUMS}
        incomplete = errors > 0 or reviewed != answered_count or citations_reviewed != citations_total or any(c["status"] == "incomplete" for c in checks.values()) or any(
            row["outcome"] == "answered" and not row["citations"] for row in payload["predictions"])
        gate = {"status": "incomplete" if incomplete else "failed" if any(c["status"] == "failed" for c in checks.values()) else "passed",
                "gate_version": 2, "checks": checks}
    return {"report_version": 2, "dataset_id": payload["dataset_id"], "dataset_sha256": payload["dataset_sha256"],
            "predictions_sha256": sha256(raw).hexdigest(), "run": payload["run"], "split": split,
            "sample_count": len(expected), "question_results": result_rows, "metrics": metrics, "quality_gate": gate}
