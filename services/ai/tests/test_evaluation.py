import importlib.util
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = _load("evaluation_runner", ROOT / "evaluation/runner/runner.py")
review_tool = _load("evaluation_review", ROOT / "evaluation/runner/review_predictions.py")
candidate_tool = _load("candidate_split", ROOT / "evaluation/data/tools/split_candidates.py")
candidate_seed = _load("candidate_seed", ROOT / "evaluation/data/tools/prepare_candidate_seed.py")
draft_tool = _load(
    "candidate_annotation_draft",
    ROOT / "evaluation/data/tools/draft_candidate_annotations.py")
finalize_tool = _load(
    "candidate_annotation_finalize",
    ROOT / "evaluation/data/tools/finalize_annotations.py")
DATASET = ROOT / "evaluation/data/seed-v1"
CANDIDATE_DATASET = ROOT / "evaluation/data/seed-v2-candidate"


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
    assert report["metrics"]["recall_at_5"] == 1.0
    assert report["metrics"]["mrr_at_10"] == 1.0
    assert report["metrics"]["complete_gold_evidence_question_rate"] == 1.0
    assert report["metrics"]["answerability_accuracy"] == 1.0
    assert report["metrics"]["unanswerable_refusal_rate"] == 1.0
    assert report["metrics"]["human_support_review_coverage"] == 1.0
    assert report["metrics"]["human_supported_answer_rate"] == 1.0
    assert report["metrics"]["answerable_question_count"] == 10
    assert report["metrics"]["unanswerable_question_count"] == 2
    assert report["metrics"]["by_category"]["uncategorized"]["sample_count"] == 12
    assert report["metrics"]["by_category"]["uncategorized"]["answerability_accuracy"] == 1.0
    assert len(report["question_results"]) == 12
    assert report["metrics"]["latency_ms"] == {
        "sample_count": 12, "p50_nearest_rank": 6.0, "p95_nearest_rank": 12.0}
    assert report["interpretation"]["acceptance_threshold"].startswith("not registered")
    assert report["quality_gate"] == {
        "status": "incomplete", "reason": "QUALITY_CONFIG_MISSING"}


def test_quality_gate_requires_dataset_bound_explicit_thresholds(tmp_path):
    predictions = tmp_path / "predictions.json"
    predictions.write_text(json.dumps(_predictions("development")), encoding="utf-8")
    manifest, _questions, _documents, _sources, dataset_sha = runner._load_dataset(DATASET)
    config = tmp_path / "quality.json"
    config.write_text(json.dumps({
        "gate_version": 1, "dataset_id": manifest["dataset_id"],
        "dataset_sha256": dataset_sha,
        "minimums": {"answerability_accuracy": 0.95, "recall_at_5": 0.9},
    }), encoding="utf-8")

    report = runner.evaluate(predictions, quality_config_path=config)

    assert report["quality_gate"]["status"] == "passed"
    gate = json.loads(config.read_text(encoding="utf-8"))
    gate["dataset_sha256"] = "0" * 64
    config.write_text(json.dumps(gate), encoding="utf-8")
    with pytest.raises(ValueError, match="INVALID_QUALITY_CONFIG"):
        runner.evaluate(predictions, quality_config_path=config)


@pytest.mark.parametrize("outcome", ["passed", "failed", "incomplete"])
def test_cli_quality_gate_exit_status(tmp_path, outcome):
    payload = _predictions("development")
    if outcome == "failed":
        payload["predictions"][0]["has_answer"] = False
        payload["predictions"][0]["cited_evidence"] = []
        payload["predictions"][0]["support_judgement"] = "not_applicable"
    elif outcome == "incomplete":
        for row in payload["predictions"]:
            if row["has_answer"]:
                row["support_judgement"] = "unreviewed"
    predictions = tmp_path / "predictions.json"
    predictions.write_text(json.dumps(payload), encoding="utf-8")
    metric = "human_supported_answer_rate" if outcome == "incomplete" else "answerability_accuracy"
    config = tmp_path / "quality.json"
    config.write_text(json.dumps({"gate_version": 1, "dataset_id": payload["dataset_id"],
                                  "dataset_sha256": payload["dataset_sha256"],
                                  "minimums": {metric: 1.0}}), encoding="utf-8")
    output = tmp_path / "report.json"
    result = subprocess.run([sys.executable, str(ROOT / "evaluation/runner/runner.py"),
                             "--predictions", str(predictions), "--quality-config", str(config),
                             "--output", str(output)], capture_output=True, text=True)
    assert result.returncode == (0 if outcome == "passed" else 1), result.stderr
    assert json.loads(output.read_text(encoding="utf-8"))["quality_gate"]["status"] == outcome


def test_support_review_bundle_is_bound_to_predictions_and_requires_reviewer_timestamp(tmp_path):
    predictions = tmp_path / "predictions.json"
    predictions.write_text(json.dumps(_predictions("development")), encoding="utf-8")
    bundle_path = tmp_path / "review.json"
    bundle_path.write_text(json.dumps(review_tool.prepare_bundle(
        predictions, created_at="2026-11-01T00:00:00Z")), encoding="utf-8")
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    answers = [item for item in bundle["entries"] if item["has_answer"]]
    for answer in answers:
        answer.update(support_judgement="supported", reviewed_by="reviewer-1",
                      reviewed_at="2026-11-01T00:01:00Z")
    bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
    output = tmp_path / "reviewed-predictions.json"

    review_tool.merge_reviews(predictions, bundle_path, output)

    reviewed = json.loads(output.read_text(encoding="utf-8"))
    assert next(item for item in reviewed["predictions"]
                if item["question_id"] == answers[0]["question_id"])["support_judgement"] == "supported"
    predictions.write_text(json.dumps(_predictions("development")) + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="REVIEW_INPUT_MISMATCH"):
        review_tool.merge_reviews(predictions, bundle_path, output)


def test_runner_groups_answerability_metrics_by_question_category(tmp_path, monkeypatch):
    manifest, questions, documents, sources, dataset_sha = runner._load_dataset(DATASET)
    for question in questions:
        question["category"] = "factual" if question["answerable"] else "no_answer"
    monkeypatch.setattr(runner, "_load_dataset", lambda _root: (
        manifest, questions, documents, sources, dataset_sha))
    predictions = tmp_path / "categorized.json"
    predictions.write_text(json.dumps(_predictions("development")), encoding="utf-8")

    report = runner.evaluate(predictions)

    categories = report["metrics"]["by_category"]
    assert set(categories) == {"factual", "no_answer"}
    assert sum(item["sample_count"] for item in categories.values()) == report["sample_count"]
    assert all("answerability_accuracy" in item for item in categories.values())
    assert categories["factual"]["answerable_answer_rate"] is not None
    assert categories["factual"]["unanswerable_refusal_rate"] is None
    assert categories["no_answer"]["answerable_answer_rate"] is None
    assert categories["no_answer"]["unanswerable_refusal_rate"] is not None


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
                  "annotation_status": "candidate", "category": "factual"}
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


def test_candidate_seed_builds_60_unreviewed_questions_and_exact_40_20_split(tmp_path):
    dataset_root = tmp_path / "seed-v2-candidate"
    _documents, count = candidate_seed.build(dataset_root)
    questions = json.loads((dataset_root / "questions.json").read_text(encoding="utf-8"))
    checked_in_root = ROOT / "evaluation" / "data" / "seed-v2-candidate"

    assert count == 60
    assert (dataset_root / "questions.json").read_bytes() == (
        checked_in_root / "questions.json").read_bytes()
    manifest_bytes = (dataset_root / "manifest.json").read_bytes()
    assert b"\r" not in manifest_bytes
    assert manifest_bytes == (checked_in_root / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    for item in manifest["documents"]:
        assert (dataset_root / item["path"]).read_bytes() == (
            checked_in_root / item["path"]).read_bytes()
    assert candidate_tool.validate_candidate_questions(questions, dataset_root)[
        "annotation_status_counts"] == {"candidate": 60, "reviewed": 0}
    assert {category: sum(item["category"] == category for item in questions)
            for category in ("factual", "rewrite", "multi_evidence",
                             "chinese_keyword", "no_answer")} == {
        "factual": 15, "rewrite": 15, "multi_evidence": 10,
        "chinese_keyword": 10, "no_answer": 10,
    }
    split = candidate_tool.assign_splits(questions)
    assert len(split["development"]) == 40
    assert len(split["holdout"]) == 20
    assert set(split["development_groups"]).isdisjoint(split["holdout_groups"])
    assert len(split["development_groups"]) + len(split["holdout_groups"]) == 36

    by_id = {item["id"]: item for item in questions}
    assert by_id["candidate-01"]["question"] == "创建索引任务请求需要提供哪些必填字段？"
    assert "documentId" not in by_id["candidate-01"]["question"]
    assert "profileId" not in by_id["candidate-01"]["question"]
    equivalent_groups = {
        "candidate-41": "fact-01",
        "candidate-42": "fact-05",
        "candidate-43": "fact-07",
        "candidate-44": "identity-notfound",
        "candidate-45": "fact-08",
        "candidate-46": "fact-10",
        "candidate-47": "parse-boundary",
        "candidate-48": "fact-14",
        "candidate-49": "rollback-timeout",
    }
    assert {question_id: by_id[question_id]["leakage_group"]
            for question_id in equivalent_groups} == equivalent_groups

    assignment = {question_id: split_name
                  for split_name in ("development", "holdout")
                  for question_id in split[split_name]}
    for family in (
            ("candidate-01", "candidate-16", "candidate-41"),
            ("candidate-05", "candidate-20", "candidate-42"),
            ("candidate-07", "candidate-22", "candidate-43"),
            ("candidate-08", "candidate-23", "candidate-45"),
            ("candidate-10", "candidate-25", "candidate-46"),
            ("candidate-14", "candidate-29", "candidate-48"),
            ("candidate-35", "candidate-44"),
            ("candidate-36", "candidate-49"),
            ("candidate-38", "candidate-47")):
        assert len({assignment[question_id] for question_id in family}) == 1
    assert {assignment[question_id] for question_id in
            ("candidate-07", "candidate-22", "candidate-43")} == {"development"}
    assert {assignment[question_id] for question_id in
            ("candidate-08", "candidate-23", "candidate-45")} == {"holdout"}

    split_manifest = candidate_tool.prepare(questions, dataset_root)
    assert split_manifest["validation"]["leakage_group_count"] == 36
    assert split_manifest == json.loads(
        (checked_in_root / "split-manifest.json").read_text(encoding="utf-8"))
    annotation_template = candidate_tool.annotation_template(questions, dataset_root)
    assert annotation_template == json.loads(
        (checked_in_root / "annotation-template.json").read_text(encoding="utf-8"))
    assert annotation_template["source_manifest_sha256"] == sha256(manifest_bytes).hexdigest()

    manifest_path = dataset_root / "manifest.json"
    manifest_path.write_bytes(manifest_bytes.replace(b"\n", b"\r\n"))
    assert candidate_tool.annotation_template(questions, dataset_root)[
        "source_manifest_sha256"] == annotation_template["source_manifest_sha256"]


def test_candidate_annotation_must_match_original_source_and_version():
    _manifest, seed_questions, _documents, _sources, _dataset_sha = runner._load_dataset(DATASET)
    reviewed = dict(seed_questions[0])
    reviewed.pop("split")
    reviewed.pop("annotation")
    reviewed["annotation_status"] = "reviewed"
    reviewed["category"] = "factual"
    assert candidate_tool.validate_candidate_questions([reviewed], DATASET)[
        "annotation_status_counts"]["reviewed"] == 1

    reviewed["evidence"] = [dict(reviewed["evidence"][0], start=0)]
    with pytest.raises(ValueError, match="INVALID_ANNOTATION_EVIDENCE"):
        candidate_tool.validate_candidate_questions([reviewed], DATASET)


def test_annotation_template_is_explicitly_unreviewed_and_cannot_be_split():
    template = candidate_tool.annotation_template([
        {"id": "new-q01", "question": "索引何时可读？", "leakage_group": "index",
         "annotation_status": "candidate", "category": "factual"}], DATASET)
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
                  "annotation_status": "candidate", "category": "factual"}
                 for index in range(60)]
    with pytest.raises(ValueError, match="LEAKAGE_GROUPS_CANNOT_FILL_HOLDOUT"):
        candidate_tool.assign_splits(questions)


def _review_fixture():
    candidates = json.loads((CANDIDATE_DATASET / "questions.json").read_text(encoding="utf-8"))
    split = json.loads(
        (CANDIDATE_DATASET / "split-manifest.json").read_text(encoding="utf-8"))
    draft = draft_tool.draft_annotations(CANDIDATE_DATASET)
    annotations = []
    for item in draft["annotations"]:
        reviewed = dict(item)
        reviewed["annotation_status"] = "reviewed"
        annotations.append(reviewed)
    review = {
        "review_version": 1,
        "status": "human_reviewed",
        "dataset_id": draft["dataset_id"],
        "source_manifest_sha256": draft["source_manifest_sha256"],
        "candidate_questions_sha256": draft["candidate_questions_sha256"],
        "reviewer": {"id": "test-only-fixture", "reviewed_at": "2026-01-01T00:00:00Z"},
        "annotations": annotations,
    }
    return candidates, split, review


def _write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_machine_draft_is_complete_source_grounded_and_still_pending():
    draft = draft_tool.draft_annotations(CANDIDATE_DATASET)

    assert draft["question_count"] == 60
    assert draft["human_reviewed"] is False
    assert draft["questions_marked_reviewed_count"] == 0
    assert draft["status"] == "machine_authored_pending_human_review"
    assert sum(item["answerable"] for item in draft["annotations"]) == 50
    assert all(item["annotation_status"] == "machine_draft"
               for item in draft["annotations"])
    reviewed_shape = [dict(item, annotation_status="reviewed")
                      for item in draft["annotations"]]
    validation = candidate_tool.validate_candidate_questions(
        reviewed_shape, CANDIDATE_DATASET)
    assert validation["annotation_status_counts"] == {"candidate": 0, "reviewed": 60}

    with pytest.raises(ValueError, match="DATASET_ANNOTATIONS_PENDING"):
        runner._load_dataset(CANDIDATE_DATASET)


def test_human_review_fixture_finalizes_and_runs_through_offline_evaluator(tmp_path):
    _candidates, _split, review = _review_fixture()
    review["prior_agent_review"] = {"reviewer": {"id": "agent:fixture"}, "sha256": "a" * 64}
    review["human_review_time_note"] = "Confirmation time; completion time unknown."
    review_path = tmp_path / "review.json"
    output = tmp_path / "reviewed-dataset"
    _write_json(review_path, review)

    result = finalize_tool.finalize(
        CANDIDATE_DATASET / "questions.json",
        CANDIDATE_DATASET / "split-manifest.json",
        review_path, CANDIDATE_DATASET, output)

    assert result["question_count"] == 60
    assert result["split_counts"] == {"development": 40, "holdout": 20}
    manifest, questions, _documents, sources, dataset_sha = runner._load_dataset(output)
    assert manifest["dataset_id"] == "qingzhu-seed-v2-reviewed"
    assert manifest["annotation_provenance"]["reviewer_id"] == "test-only-fixture"
    assert manifest["annotation_provenance"]["review_file_sha256"] == sha256(review_path.read_bytes()).hexdigest()
    assert manifest["annotation_provenance"]["prior_agent_review"] == review["prior_agent_review"]
    assert manifest["annotation_provenance"]["human_review_time_note"] == review["human_review_time_note"]
    assert {split: sum(item["split"] == split for item in questions)
            for split in ("development", "holdout")} == {"development": 40, "holdout": 20}

    predictions = []
    for index, question in enumerate(
            (item for item in questions if item["split"] == "development"), 1):
        evidence = []
        for item in question["evidence"]:
            source = sources[item["document_id"]]
            evidence.append({
                "document_id": item["document_id"],
                "content_version_id": item["content_version_id"],
                "start": item["start"],
                "end": item["end"],
                "text_sha256": sha256(
                    source[item["start"]:item["end"]].encode("utf-8")).hexdigest(),
            })
        predictions.append({
            "question_id": question["id"],
            "has_answer": question["answerable"],
            "retrieved_evidence": evidence,
            "cited_evidence": list(range(len(evidence))) if evidence else [],
            "support_judgement": "supported" if evidence else "not_applicable",
            "latency_ms": float(index),
        })
    prediction_path = tmp_path / "predictions.json"
    _write_json(prediction_path, {
        "dataset_id": manifest["dataset_id"],
        "dataset_sha256": dataset_sha,
        "predictions": predictions,
    })
    report = runner.evaluate(prediction_path, dataset_root=output)
    assert report["sample_count"] == 40
    assert report["dataset_provenance"] == "synthetic authored seed; not human-user evaluation"
    assert report["metrics"]["gold_evidence_span_recall"] == 1.0
    assert report["metrics"]["answerability_accuracy"] == 1.0


def test_finalizer_rejects_pending_draft_without_creating_output(tmp_path):
    draft = draft_tool.draft_annotations(CANDIDATE_DATASET)
    review_path = tmp_path / "machine-draft.json"
    output = tmp_path / "should-not-exist"
    _write_json(review_path, draft)

    with pytest.raises(ValueError, match="ANNOTATIONS_NOT_HUMAN_REVIEWED"):
        finalize_tool.finalize(
            CANDIDATE_DATASET / "questions.json",
            CANDIDATE_DATASET / "split-manifest.json",
            review_path, CANDIDATE_DATASET, output)
    assert not output.exists()


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ("missing-question", "REVIEW_QUESTION_SET_MISMATCH"),
        ("question-drift", "REVIEW_QUESTION_METADATA_DRIFT"),
        ("bad-span", "INVALID_ANNOTATION_EVIDENCE"),
        ("stale-digest", "REVIEW_SOURCE_DIGEST_MISMATCH"),
        ("split-leak", "SPLIT_LEAKAGE_GROUP_MISMATCH"),
    ],
)
def test_finalizer_rejects_incomplete_or_drifted_review(tmp_path, change, error):
    candidates, split, review = _review_fixture()
    if change == "missing-question":
        review["annotations"].pop()
    elif change == "question-drift":
        review["annotations"][0]["question"] = "替换后的问题"
    elif change == "bad-span":
        review["annotations"][0]["evidence"][0]["start"] += 1
    elif change == "stale-digest":
        review["source_manifest_sha256"] = "0" * 64
    elif change == "split-leak":
        split["leakage_groups"]["development"].append(
            split["leakage_groups"]["holdout"][0])

    review_path = tmp_path / "review.json"
    split_path = tmp_path / "split.json"
    output = tmp_path / "invalid-dataset"
    _write_json(review_path, review)
    _write_json(split_path, split)

    with pytest.raises(ValueError, match=error):
        finalize_tool.finalize(
            CANDIDATE_DATASET / "questions.json", split_path,
            review_path, CANDIDATE_DATASET, output)
    assert not output.exists()
