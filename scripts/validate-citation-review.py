"""Validate completed human citation-review worksheets.

Exits non-zero until every row is filled by a real reviewer. It does not edit
the worksheet or any evaluation artifact.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "eval-out" / "citation-review-20261108"
SUPPORT = {"supported", "not_supported", "uncertain", "refusal_correct", "refusal_incorrect"}
CITATION = {"correct", "incorrect", "uncertain", ""}


def main() -> int:
    files = [DIR / "development.csv", DIR / "holdout.csv"]
    if not all(path.exists() for path in files):
        print("worksheets missing; run scripts/prepare-citation-review.py", flush=True)
        return 2

    report = {}
    problems: list[str] = []
    for path in files:
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        total = len(rows)
        filled = 0
        for index, row in enumerate(rows, start=2):
            where = f"{path.name}:{index}"
            if not row.get("reviewer", "").strip() or row["reviewer"].lower().startswith("agent"):
                problems.append(f"{where}: reviewer missing or agent")
            if not row.get("reviewed_at", "").strip():
                problems.append(f"{where}: reviewed_at missing")
            if row.get("human_support", "") not in SUPPORT:
                problems.append(f"{where}: human_support invalid")
            if not row.get("human_notes", "").strip():
                problems.append(f"{where}: notes missing")
            if row.get("outcome") == "answered":
                if row.get("human_citation", "") not in CITATION:
                    problems.append(f"{where}: human_citation invalid")
            else:
                if row.get("human_citation", "").strip():
                    problems.append(f"{where}: refusal row must leave human_citation blank")
            if row.get("reviewer", "").strip() and row.get("reviewed_at", "").strip() and row.get("human_support", "") in SUPPORT:
                filled += 1
        report[path.stem] = {"rows": total, "filled": filled, "coverage": round(filled / total, 4) if total else 0}

    print(json.dumps({"splits": report, "problems": problems[:50], "problem_count": len(problems)}, ensure_ascii=False, indent=2), flush=True)
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
