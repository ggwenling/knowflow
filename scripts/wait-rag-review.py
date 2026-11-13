"""Expand a current, independent GitHub approval into the runner review format."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


def wait_for_review(template, deadline):
    repo = os.environ["GITHUB_REPOSITORY"]
    number = os.environ["PR_NUMBER"]
    endpoint = f"repos/{repo}/pulls/{number}/reviews?per_page=100"
    while time.monotonic() < deadline:
        pages = json.loads(subprocess.check_output(["gh", "api", "--paginate", "--slurp", endpoint]))
        reviews = [review for page in pages for review in page]
        latest = {}
        for review in reviews:
            if review["state"] in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}:
                latest[review["user"]["login"]] = review
        for login, review in latest.items():
            if (login == os.environ["PR_AUTHOR"] or review["state"] != "APPROVED"
                    or review["commit_id"] != os.environ["PR_HEAD"]
                    or review["author_association"] not in {"OWNER", "MEMBER", "COLLABORATOR"}):
                continue
            match = re.search(r"```knowflow-rag-review\s*\n(.*?)\n```", review["body"] or "", re.S)
            if match is None:
                continue
            try:
                payload = json.loads(match[1])
            except ValueError:
                continue
            if payload.get("predictions_sha256") != template["predictions_sha256"]:
                continue
            rows = payload.get("judgements", {})
            answered = [entry for entry in template["entries"] if entry["outcome"] == "answered"]
            if not isinstance(rows, dict) or set(rows) != {entry["question_id"] for entry in answered}:
                continue
            if any(not isinstance(row := rows[entry["question_id"]], list)
                   or len(row) != 1 + len(entry["citations"])
                   or any(value not in ("supported", "unsupported") for value in row)
                   for entry in answered):
                continue
            for entry in answered:
                answer, *citations = rows[entry["question_id"]]
                entry.update(support_judgement=answer, reviewed_by=login, reviewed_at=review["submitted_at"])
                for citation, judgement in zip(entry["citations"], citations, strict=True):
                    citation["judgement"] = judgement
            return template
        time.sleep(20)
    raise SystemExit("RAG_REVIEW_REQUIRED")


if __name__ == "__main__":
    source, destination = map(Path, sys.argv[1:])
    review = wait_for_review(json.loads(source.read_bytes()), time.monotonic() + 30 * 60)
    destination.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
