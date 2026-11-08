"""Preflight for a private blind evaluation set.

Run only by the dataset custodian. It does not print question text, answers, or
source documents. Output contains counts, short hashes, and pass/fail reasons.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def question_texts(payload: object) -> list[str]:
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("questions") or payload.get("items") or []
    else:
        items = []
    values = []
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("question"), str):
            values.append(item["question"].strip())
    return values


def normalized_hash(text: str) -> str:
    return hashlib.sha256(" ".join(text.split()).lower().encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--public-dataset", required=True, type=Path)
    parser.add_argument("--price", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    private_exists = args.dataset.exists()
    check("private_dataset_exists", private_exists, "present" if private_exists else "missing")
    if not private_exists:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({"checks": checks}, ensure_ascii=False, indent=2), encoding="utf-8")
        return 1

    actual = sha256(args.dataset)
    check("private_dataset_sha256", actual == args.expected_sha256, actual[:16])
    try:
        private_payload = json.loads(args.dataset.read_text(encoding="utf-8"))
        private_questions = question_texts(private_payload)
        check("private_dataset_parses", True, f"{len(private_questions)} questions")
    except (OSError, ValueError) as error:
        check("private_dataset_parses", False, type(error).__name__)
        private_questions = []

    public_hash = sha256(args.public_dataset) if args.public_dataset.exists() else ""
    check("public_dataset_exists", args.public_dataset.exists(), public_hash[:16] if public_hash else "missing")
    public_hashes = set()
    if args.public_dataset.exists():
        try:
            public_hashes = {normalized_hash(text) for text in question_texts(json.loads(args.public_dataset.read_text(encoding="utf-8")))}
        except (OSError, ValueError):
            public_hashes = set()
    overlap = sum(1 for text in private_questions if normalized_hash(text) in public_hashes)
    check("no_public_overlap", overlap == 0, f"overlap={overlap}")

    for label, path in (("price", args.price), ("policy", args.policy)):
        exists = path.exists()
        check(f"{label}_exists", exists, "present" if exists else "missing")
        if exists:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                verified = str(payload.get("verified_by", ""))
                pending = "pending" in verified.lower()
                check(f"{label}_human_signed", not pending, verified[:80] or "no verified_by")
            except (OSError, ValueError):
                check(f"{label}_parses", False, "invalid json")

    check("blindtest_not_in_repo", not (ROOT / ".blindtest").exists(), "absent" if not (ROOT / ".blindtest").exists() else "present")

    passed = all(item["ok"] for item in checks)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"passed": passed, "checks": checks}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": passed, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
