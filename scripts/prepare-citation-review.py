"""Build human review worksheets from existing evaluation review snapshots.

Read-only with respect to eval-out/*/review.json. The generated CSV keeps the
agent judgement for comparison and leaves human fields blank for a real reviewer.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval-out" / "citation-review-20261108"
SOURCES = {
    "development": ROOT / "eval-out" / "seed-v2-dev-9907aca" / "review.json",
    "holdout": ROOT / "eval-out" / "seed-v2-holdout-9907aca" / "review.json",
}

HEADERS = [
    "split",
    "question_id",
    "question",
    "outcome",
    "answer",
    "answer_sha256",
    "agent_support",
    "citation_index",
    "citation_id",
    "claim",
    "source_document",
    "content_version_id",
    "locator_start",
    "locator_end",
    "source_text_sha256",
    "source_text",
    "human_support",
    "human_citation",
    "human_notes",
    "reviewer",
    "reviewed_at",
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    summary: dict[str, dict[str, int]] = {}
    for split, path in SOURCES.items():
        if not path.exists():
            print(f"missing {path}", flush=True)
            return 2
        data = json.loads(path.read_text(encoding="utf-8"))
        rows: list[dict[str, str]] = []
        answered = refused = citations = 0
        for entry in data.get("entries", []):
            outcome = entry.get("outcome", "")
            if outcome == "answered":
                answered += 1
                for index, citation in enumerate(entry.get("citations", [])):
                    citations += 1
                    evidence = citation.get("evidence") or {}
                    rows.append({
                        "split": split,
                        "question_id": entry.get("question_id", ""),
                        "question": entry.get("question", ""),
                        "outcome": outcome,
                        "answer": entry.get("answer") or "",
                        "answer_sha256": entry.get("answer_sha256", ""),
                        "agent_support": entry.get("support_judgement", ""),
                        "citation_index": str(index),
                        "citation_id": citation.get("id", ""),
                        "claim": citation.get("claim", ""),
                        "source_document": evidence.get("document_id", ""),
                        "content_version_id": evidence.get("content_version_id", ""),
                        "locator_start": str(evidence.get("start", "")),
                        "locator_end": str(evidence.get("end", "")),
                        "source_text_sha256": evidence.get("text_sha256", ""),
                        "source_text": citation.get("source_text", ""),
                        "human_support": "",
                        "human_citation": "",
                        "human_notes": "",
                        "reviewer": "",
                        "reviewed_at": "",
                    })
            else:
                refused += 1
                rows.append({
                    "split": split,
                    "question_id": entry.get("question_id", ""),
                    "question": entry.get("question", ""),
                    "outcome": outcome,
                    "answer": entry.get("answer") or "",
                    "answer_sha256": entry.get("answer_sha256", ""),
                    "agent_support": entry.get("support_judgement", ""),
                    "citation_index": "",
                    "citation_id": "",
                    "claim": "",
                    "source_document": "",
                    "content_version_id": "",
                    "locator_start": "",
                    "locator_end": "",
                    "source_text_sha256": "",
                    "source_text": "",
                    "human_support": "",
                    "human_citation": "",
                    "human_notes": "",
                    "reviewer": "",
                    "reviewed_at": "",
                })

        target = OUT / f"{split}.csv"
        with target.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=HEADERS)
            writer.writeheader()
            writer.writerows(rows)
        summary[split] = {
            "answers": len(data.get("entries", [])),
            "answered": answered,
            "refused": refused,
            "citations": citations,
            "rows": len(rows),
        }
        print(f"{split}: {summary[split]} -> {target}", flush=True)

    (OUT / "summary.json").write_text(
        json.dumps({"generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(), "splits": summary}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
