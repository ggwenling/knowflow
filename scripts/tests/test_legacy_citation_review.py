"""Regression coverage for the historical no-argument review commands."""
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).resolve().parents[1]


class LegacyCitationReviewTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        scripts = self.root / "scripts"
        scripts.mkdir()
        for name in ("prepare-citation-review.py", "validate-citation-review.py"):
            shutil.copyfile(SCRIPTS / name, scripts / name)
        self.out = self.root / "eval-out" / "citation-review-20261108"
        for name in ("dev", "holdout"):
            source = self.root / "eval-out" / f"seed-v2-{name}-9907aca"
            source.mkdir(parents=True)
            entries = [
                {"question_id": "q1", "outcome": "answered", "answer": "answer",
                 "support_judgement": "supported", "citations": [{"id": "c1", "claim": "claim",
                 "evidence": {"document_id": "doc"}, "source_text": "text"}]},
                {"question_id": "q2", "outcome": "refused", "citations": []},
            ]
            (source / "review.json").write_text(json.dumps({"entries": entries}), encoding="utf-8")

    def run_script(self, name):
        return subprocess.run([sys.executable, str(self.root / "scripts" / name)],
                              capture_output=True, encoding="utf-8", check=False)

    def test_no_argument_prepare_and_validate(self):
        self.assertEqual(self.run_script("prepare-citation-review.py").returncode, 0)
        self.assertEqual(self.run_script("validate-citation-review.py").returncode, 1)
        for split in ("development", "holdout"):
            path = self.out / f"{split}.csv"
            with path.open(encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                rows, headers = list(reader), reader.fieldnames
            self.assertIn("agent_support", headers)
            self.assertIn("human_support", headers)
            self.assertIn("human_citation", headers)
            self.assertIn("human_notes", headers)
            for row in rows:
                row.update(human_support="supported" if row["outcome"] == "answered" else "refusal_correct",
                           human_citation="correct" if row["outcome"] == "answered" else "",
                           human_notes="reviewed", reviewer="human", reviewed_at="2026-11-08")
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=headers)
                writer.writeheader()
                writer.writerows(rows)
        result = self.run_script("validate-citation-review.py")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(result.stdout)["problem_count"], 0)

    def test_either_existing_worksheet_blocks_all_writes(self):
        for split in ("development", "holdout"):
            with self.subTest(split=split):
                self.out.mkdir(parents=True, exist_ok=True)
                existing = self.out / f"{split}.csv"
                existing.write_text("existing human review", encoding="utf-8")
                result = self.run_script("prepare-citation-review.py")
                self.assertEqual(result.returncode, 2)
                self.assertEqual(existing.read_text(encoding="utf-8"), "existing human review")
                self.assertEqual({p.name for p in self.out.iterdir()}, {existing.name})
                existing.unlink()


if __name__ == "__main__":
    unittest.main()
