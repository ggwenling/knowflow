"""Offline tests for the public candidate's manual review entry point."""
import csv
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1]
RUNNER = SCRIPTS.parent / "evaluation" / "runner"
sys.path.insert(0, str(RUNNER))
from runner_v2 import MINIMUMS, prepare_review

SPLITS = ("development", "holdout")
CANDIDATE = "a" * 40


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def fixture(root):
    dataset = root / "dataset"
    dataset.mkdir()
    documents, questions = [], []
    rows = {split: [] for split in SPLITS}
    for i in range(15):
        split, qid = SPLITS[i % 2], f"q{i}"
        answerable = i < 10
        text = f"档案编号是 {i}。"
        evidence, citations, gold = [], [], []
        if answerable:
            name = f"doc{i}.txt"
            (dataset / name).write_text(text, encoding="utf-8")
            text_sha = sha256(text.encode()).hexdigest()
            documents.append(dict(id=f"doc{i}", path=name, license="CC0-1.0", sha256=text_sha,
                                  bytes=len(text.encode()), characters=len(text), content_version_id="v1"))
            span = dict(document_id=f"doc{i}", content_version_id="v1", start=0, end=len(text))
            gold.append(dict(span, quote=text, line_start=1, line_end=1, unit="unicode_code_point"))
            evidence.append(dict(span, text_sha256=text_sha, source_id="s"))
            citations.append(dict(id="c", source_id="s", marker_index=0, evidence_index=0, claim=text))
        answer = f"{text} [s]" if answerable else "资料不足，无法回答。"
        questions.append(dict(id=qid, question=f"合成问题 {i}", reference_answer=answer,
                              answerable=answerable, evidence=gold, leakage_group=qid, split=split))
        rows[split].append(dict(question_id=qid, outcome="answered" if answerable else "refused",
                                answer=answer, answer_sha256=sha256(answer.encode()).hexdigest(),
                                retrieved_evidence=evidence, citations=citations, latency_ms=1, error_code=None))
    manifest_path, questions_path = dataset / "manifest.json", dataset / "questions.json"
    dump(manifest_path, dict(dataset_id="synthetic-manual", synthetic=True, documents=documents))
    dump(questions_path, questions)
    dataset_sha = sha256(manifest_path.read_bytes() + b"\0" + questions_path.read_bytes()).hexdigest()
    run = dict(code_sha=CANDIDATE, model="fixture", schema_sha256="b" * 64,
               config_sha256="c" * 64, prompt_sha256="d" * 64)
    config = root / "quality.json"
    dump(config, dict(gate_version=2, dataset_id="synthetic-manual",
                      dataset_sha256=dataset_sha, minimums=MINIMUMS))
    for split in SPLITS:
        prediction = root / f"{split}.predictions.json"
        dump(prediction, dict(prediction_version=2, dataset_id="synthetic-manual",
                              dataset_sha256=dataset_sha, run=run, predictions=rows[split]))
        dump(root / f"{split}.original.json", prepare_review(prediction, dataset, split))
    return dataset, config


class ManualCitationReviewTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.dataset, self.config = fixture(self.root)
        self.out = self.root / "worksheet"
        self.prepare_args = [
            "--manual", "--run-id", "manual-fixture", "--candidate-sha", CANDIDATE,
            "--development", self.root / "development.original.json",
            "--holdout", self.root / "holdout.original.json",
            "--development-predictions", self.root / "development.predictions.json",
            "--holdout-predictions", self.root / "holdout.predictions.json",
        ]
        prepared = self.run_command("prepare-citation-review.py", "--out", self.out, *self.prepare_args)
        self.assertEqual(prepared.returncode, 0, prepared.stderr or prepared.stdout)
        report = json.loads(prepared.stdout)
        self.assertEqual(report["rows"], {"development": 8, "holdout": 7})
        self.validate_args = [
            "--manual", "--candidate-sha", CANDIDATE, "--manifest-sha256", report["manifest_sha256"],
        ]

    def run_command(self, script, *args):
        path = RUNNER / script if script == "runner.py" else SCRIPTS / script
        return subprocess.run([sys.executable, str(path), *map(str, args)], cwd=self.root,
                              capture_output=True, encoding="utf-8", check=False)

    def validate(self, *args, manual=True):
        options = self.validate_args if manual else []
        return self.run_command("validate-citation-review.py", "--dir", self.out, *options, *args)

    def fill(self, split, **first_row_changes):
        path = self.out / f"{split}.csv"
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            rows, headers = list(reader), reader.fieldnames
        for row in rows:
            answered = row["outcome"] == "answered"
            row.update(review_support="supported" if answered else "refusal_correct",
                       review_citation="correct" if answered else "",
                       review_notes="核对合成原文，记录对应答案和拒答的理由。",
                       reviewer="fixture-reviewer", reviewed_at=datetime.now(timezone.utc).isoformat())
        rows[0].update(first_row_changes)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)

    def test_roundtrip_exports_and_scores_both_splits(self):
        originals = {p: p.read_bytes() for p in self.root.glob("*.json")}
        self.fill("development")
        self.fill("holdout", review_citation="incorrect")
        exported = self.validate("--export")
        self.assertEqual(exported.returncode, 0, exported.stderr or exported.stdout)
        report = json.loads(exported.stdout)
        self.assertEqual(report["status"], "COMPLETE")
        audit = json.loads((self.out / "review-audit.json").read_bytes())
        self.assertEqual(audit["candidate_sha"], CANDIDATE)
        self.assertEqual(audit["manifest_sha256"], self.validate_args[-1])
        self.assertNotIn("receipt_sha256", audit)
        for split, expected_status in zip(SPLITS, ("passed", "failed"), strict=True):
            with self.subTest(split=split):
                csv_path = self.out / f"{split}.csv"
                self.assertEqual(audit["validation"]["splits"][split]["worksheet_sha256"],
                                 sha256(csv_path.read_bytes()).hexdigest())
                review = self.out / f"{split}.review.manual.json"
                self.assertEqual(audit["outputs"][split]["sha256"], sha256(review.read_bytes()).hexdigest())
                output = self.root / f"{split}.score.json"
                scored = self.run_command("runner.py", "--split", split, "--dataset", self.dataset,
                                          "--predictions", self.root / f"{split}.predictions.json",
                                          "--quality-config", self.config, "--review", review,
                                          "--output", output, "--formal")
                self.assertEqual(scored.returncode, int(expected_status == "failed"), scored.stderr)
                score = json.loads(output.read_bytes())
                self.assertEqual(score["quality_gate"]["status"], expected_status)
                self.assertEqual(score["quality_gate"]["checks"]["citation_accuracy"]["status"], expected_status)
                self.assertEqual(score["metrics"]["human_support_review_coverage"], 1)
                self.assertEqual(score["metrics"]["citation_review_coverage"], 1)
        self.assertTrue(all(p.read_bytes() == raw for p, raw in originals.items()))
        self.assertEqual(json.loads(self.validate("--export").stdout)["reason"], "REVIEW_EXPORT_EXISTS")

    def test_blank_or_invalid_human_rows_are_not_exported(self):
        self.assertEqual(json.loads(self.validate("--export").stdout)["status"], "INCOMPLETE")
        self.fill("holdout")
        for changes in ({"reviewer": ""}, {"reviewer": " AGENT:fixture"}, {"review_citation": ""},
                        {"reviewed_at": "2026-11-08T12:00:00"}, {"claim": "篡改原始声明"}):
            with self.subTest(changes=changes):
                self.fill("development", **changes)
                result = self.validate("--export")
                self.assertEqual(result.returncode, 1)
                self.assertEqual(json.loads(result.stdout)["status"], "INCOMPLETE")
        self.assertFalse(list(self.out.glob("*.review.manual.json")))

    def test_manifest_and_input_tampering_are_blocked(self):
        for path, reason in (
            (self.out / "manifest.json", "REVIEW_MANIFEST_CHANGED"),
            (self.root / "development.original.json", "ORIGINAL_REVIEW_CHANGED"),
            (self.root / "holdout.predictions.json", "ORIGINAL_PREDICTIONS_CHANGED"),
        ):
            with self.subTest(path=path.name):
                raw = path.read_bytes()
                path.write_bytes(raw + b"\n")
                try:
                    result = self.validate("--export")
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(json.loads(result.stdout)["reason"], reason)
                finally:
                    path.write_bytes(raw)
        self.assertEqual(json.loads(self.validate(manual=False).stdout)["reason"], "REVIEW_MODE_MISMATCH")

    def test_prepare_and_validate_reject_wrong_candidate(self):
        wrong = "f" * 40
        alternate = self.root / "wrong-candidate"
        prepared = self.run_command("prepare-citation-review.py", "--out", alternate, *self.prepare_args,
                                    "--candidate-sha", wrong)
        self.assertEqual(json.loads(prepared.stdout)["reason"], "REVIEW_CANDIDATE_MISMATCH")
        self.assertFalse(alternate.exists())
        checked = self.validate("--candidate-sha", wrong)
        self.assertEqual(json.loads(checked.stdout)["reason"], "REVIEW_CANDIDATE_MISMATCH")

    def test_prepare_rejects_review_bound_to_another_prediction(self):
        alternate = self.root / "wrong-predictions"
        prepared = self.run_command("prepare-citation-review.py", "--out", alternate, *self.prepare_args,
                                    "--development-predictions", self.root / "holdout.predictions.json")
        self.assertEqual(prepared.returncode, 1)
        self.assertEqual(json.loads(prepared.stdout)["reason"], "REVIEW_PREDICTIONS_MISMATCH")
        self.assertFalse(alternate.exists())


if __name__ == "__main__":
    unittest.main()
