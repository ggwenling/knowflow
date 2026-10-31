import importlib.util
from hashlib import sha256
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = _load("evaluation_runner", ROOT / "evaluation/runner/runner.py")
candidate_tool = _load("candidate_split", ROOT / "evaluation/data/tools/split_candidates.py")
DATASET = ROOT / "evaluation/data/seed-v1"


def _predictions(split):
    manifest, questions, _documents, _sources, dataset_sha = runner._load_dataset(DATASET)
    rows = []
    for index, question in enumerate(
            (item for item in questions if item["split"] == split), 1):
        evidence = []
        for item in question["evidence"]:
            source = _sources[item["document_id"]]
            text_sha256 = sha256(source[item["start"]:item["end"]].encode("utf-8")).hexdigest()
            evidence.append({key: item[key] for key in
                             ("document_id", "content_version_id", "start", "end")}
                            | {"text_sha256": text_sha256})
        rows.append({
            "question_id": question["id"],
            "has_answer": question["answerable"],
            "retrieved_evidence": evidence,
            "cited_evidence": list(range(len(evidence))) if question["answerable"] else [],
            "support_judgement": "supported" if question["answerable"] else "not_applicable",
            "latency_ms": float(index),
        })
    return {"dataset_id": manifest["dataset_id"], "dataset_sha256": dataset_sha,
            "predictions": rows}


def test_runner_scores_saved_predictions_and_keeps_human_judgement_explicit(tmp_path):
    predictions = tmp_path / "predictions.json"
    predictions.write_text(json.dumps(_predictions("development")), encoding="utf-8")

    report = runner.evaluate(predictions)

    assert report["dataset_provenance"] == "synthetic authored seed; not human-user evaluation"
    assert report["sample_count"] == 12
    assert report["metrics"]["gold_evidence_span_recall"] == 1.0
    assert report["metrics"]["complete_gold_evidence_question_rate"] == 1.0
    assert report["metrics"]["answerability_accuracy"] == 1.0
    assert report["metrics"]["unanswerable_refusal_rate"] == 1.0
    assert report["metrics"]["human_support_review_coverage"] == 1.0
    assert report["metrics"]["human_supported_answer_rate"] == 1.0
    assert report["metrics"]["answerable_question_count"] == 10
    assert report["metrics"]["unanswerable_question_count"] == 2
    assert len(report["question_results"]) == 12
    assert report["metrics"]["latency_ms"] == {
        "sample_count": 12, "p50_nearest_rank": 6.0, "p95_nearest_rank": 12.0}
    assert report["interpretation"]["acceptance_threshold"].startswith("not registered")


def test_runner_counts_unanswerable_hallucinations_in_support_review_metrics(tmp_path):
    payload = _predictions("development")
    questions = runner._load_dataset(DATASET)[1]
    unanswerable_ids = {question["id"] for question in questions
                        if question["split"] == "development" and not question["answerable"]}
    unanswerable = [row for row in payload["predictions"]
                    if row["question_id"] in unanswerable_ids]
    unanswerable[0]["has_answer"] = True
    unanswerable[0]["support_judgement"] = "unsupported"
    unanswerable[1]["has_answer"] = True
    unanswerable[1]["support_judgement"] = "unreviewed"
    predictions = tmp_path / "hallucinations.json"
    predictions.write_text(json.dumps(payload), encoding="utf-8")

    report = runner.evaluate(predictions)

    assert report["metrics"]["answerable_answer_rate"] == 1.0
    assert report["metrics"]["questions_answered_count"] == 12
    assert report["metrics"]["human_support_reviewed_answer_count"] == 11
    assert report["metrics"]["human_support_review_coverage"] == round(11 / 12, 4)
    assert report["metrics"]["human_supported_answer_rate"] == round(10 / 11, 4)


def test_runner_refuses_dataset_drift_missing_rows_and_cross_split_predictions(tmp_path):
    payload = _predictions("development")
    path = tmp_path / "predictions.json"
    payload["predictions"].pop()
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="MISSING_PREDICTIONS"):
        runner.evaluate(path)

    payload = _predictions("development")
    payload["predictions"][0]["question_id"] = "q09"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="INVALID_PREDICTION"):
        runner.evaluate(path)

    payload = _predictions("development")
    payload["dataset_sha256"] = "0" * 64
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="PREDICTION_DATASET_MISMATCH"):
        runner.evaluate(path)


def test_runner_rejects_invalid_spans_and_citation_indexes(tmp_path):
    payload = _predictions("development")
    payload["predictions"][0]["cited_evidence"] = [3]
    path = tmp_path / "predictions.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="INVALID_CITATION_INDEX"):
        runner.evaluate(path)

    payload = _predictions("development")
    payload["predictions"][0]["retrieved_evidence"][0]["end"] = 10**9
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="INVALID_EVIDENCE_SPAN"):
        runner.evaluate(path)


def test_candidate_split_is_deterministic_and_keeps_leakage_groups_together():
    questions = [{"id": f"c{index:02}", "question": f"候选题 {index}",
                  "leakage_group": f"group-{index // 2}",
                  "annotation_status": "candidate"}
                 for index in range(60)]
    result = candidate_tool.prepare(questions, DATASET, seed=11)
    repeat = candidate_tool.prepare(questions, DATASET, seed=11)

    assert result == repeat
    assert result["target_counts"] == {"development": 40, "holdout": 20}
    assert len(result["question_ids"]["development"]) == 40
    assert len(result["question_ids"]["holdout"]) == 20
    assert result["questions_marked_reviewed_count"] == 0
    assert result["status"] == "candidate_allocation_not_a_blind_holdout"
    assert set(result["leakage_groups"]["development"]).isdisjoint(
        result["leakage_groups"]["holdout"])


def test_candidate_annotation_must_match_original_source_and_version():
    _manifest, seed_questions, _documents, _sources, _dataset_sha = runner._load_dataset(DATASET)
    reviewed = dict(seed_questions[0])
    reviewed.pop("split")
    reviewed.pop("annotation")
    reviewed["annotation_status"] = "reviewed"
    assert candidate_tool.validate_candidate_questions([reviewed], DATASET)[
        "annotation_status_counts"]["reviewed"] == 1

    reviewed["evidence"] = [dict(reviewed["evidence"][0], start=0)]
    with pytest.raises(ValueError, match="INVALID_ANNOTATION_EVIDENCE"):
        candidate_tool.validate_candidate_questions([reviewed], DATASET)


def test_annotation_template_is_explicitly_unreviewed_and_cannot_be_split():
    template = candidate_tool.annotation_template([
        {"id": "new-q01", "question": "索引何时可读？", "leakage_group": "index",
         "annotation_status": "candidate"}], DATASET)
    assert template["question_count"] == 1
    assert template["questions_marked_reviewed_count"] == 0
    assert template["status"] == "pending_annotations_not_a_blind_holdout"
    assert template["annotations"][0]["annotation_status"] == "pending"
    assert template["annotations"][0]["answerable"] is None
    assert template["annotations"][0]["evidence"] == []
    with pytest.raises(ValueError, match="INVALID_CANDIDATE"):
        candidate_tool.prepare(template["annotations"], DATASET,
                               development_count=1, holdout_count=0)


def test_candidate_split_rejects_groups_that_cannot_fill_exact_holdout():
    questions = [{"id": f"c{index:02}", "question": f"候选题 {index}",
                  "leakage_group": f"group-{index // 6}",
                  "annotation_status": "candidate"}
                 for index in range(60)]
    with pytest.raises(ValueError, match="LEAKAGE_GROUPS_CANNOT_FILL_HOLDOUT"):
        candidate_tool.assign_splits(questions)
