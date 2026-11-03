"""Convert a local private pack into a local runner dataset without printing its content."""
import argparse
from hashlib import sha256
import json
import re
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory


def convert(pack, source_root):
    pack, source_root = Path(pack).resolve(), Path(source_root).resolve()
    commitment = (pack / "COMMITMENT.txt").read_text(encoding="utf-8")
    for name in ("questions.json", "corpus.json"):
        match = re.search(re.escape(name) + r" sha256: ([0-9a-f]{64})", commitment)
        if match is None or sha256((pack / name).read_bytes()).hexdigest() != match.group(1):
            raise ValueError("COMMITMENT_MISMATCH")
    data = json.loads((pack / "questions.json").read_text(encoding="utf-8"))
    corpus = json.loads((pack / "corpus.json").read_text(encoding="utf-8"))
    questions = data["questions"]
    if len(questions) != 20 or sum(q["answerable"] is True for q in questions) != 15:
        raise ValueError("INVALID_PRIVATE_COUNTS")
    documents, sources, by_path = [], {}, {}
    for entry in corpus["documents"]:
        relative = entry["path"]
        path = (source_root / relative).resolve()
        if not path.is_relative_to(source_root) or relative in by_path:
            raise ValueError("INVALID_SOURCE_PATH")
        raw = path.read_bytes()
        digest = sha256(raw).hexdigest()
        if digest != entry["sha256"]:
            raise ValueError("SOURCE_HASH_MISMATCH")
        text = raw.decode("utf-8")
        document_id = "doc-" + sha256(relative.encode("utf-8")).hexdigest()
        document = {"id": document_id, "content_version_id": "content-" + digest,
                    "path": "documents/" + document_id + ".txt", "sha256": digest,
                    "bytes": len(raw), "characters": len(text),
                    "license": entry.get("license", "UNSPECIFIED")}
        documents.append(document)
        by_path[relative] = document
        sources[document_id] = raw
    converted, seen = [], set()
    for question in questions:
        if (not isinstance(question["id"], str) or not question["id"].strip()
                or question["id"] in seen or type(question["answerable"]) is not bool):
            raise ValueError("INVALID_QUESTION")
        seen.add(question["id"])
        evidence = []
        for span in question.get("evidence", []):
            document = by_path[span["path"]]
            text = sources[document["id"]].decode("utf-8")
            start, end = span["char_start"], span["char_end"]
            if (type(start) is not int or type(end) is not int
                    or not 0 <= start < end <= len(text) or text[start:end] != span["quote"]):
                raise ValueError("INVALID_UNICODE_RANGE")
            evidence.append({"document_id": document["id"],
                             "content_version_id": document["content_version_id"],
                             "start": start, "end": end, "unit": "unicode_code_point",
                             "quote": span["quote"], "line_start": text.count("\n", 0, start) + 1,
                             "line_end": text.count("\n", 0, end) + 1})
        if bool(evidence) != question["answerable"]:
            raise ValueError("INVALID_QUESTION_EVIDENCE")
        reference = question.get("reference_answer", question.get("answer"))
        if (not isinstance(reference, str) or not reference.strip()
                or not isinstance(question["question"], str) or not question["question"].strip()):
            raise ValueError("MISSING_QUESTION_FIELDS")
        converted.append({"id": question["id"], "question": question["question"],
                          "answerable": question["answerable"], "reference_answer": reference,
                          "evidence": evidence, "split": "holdout",
                          "leakage_group": question["id"], "annotation_status": "reviewed"})
    manifest = {"dataset_id": "private-" + sha256((pack / "questions.json").read_bytes()).hexdigest(),
                "private_pack_version": 1, "privacy": "local_only", "synthetic": False,
                "documents": documents}
    parent = pack / "out"
    if parent.is_symlink() or parent.resolve() != parent:
        raise ValueError("UNSAFE_OUTPUT_PATH")
    parent.mkdir(exist_ok=True)
    output = parent / "runner"
    if output.exists() or output.is_symlink():
        raise ValueError("OUTPUT_EXISTS")
    with TemporaryDirectory(prefix=".converting-", dir=parent) as temp:
        staging = Path(temp) / "runner"
        (staging / "documents").mkdir(parents=True)
        for document in documents:
            (staging / document["path"]).write_bytes(sources[document["id"]])
        for name, value in (("manifest.json", manifest), ("questions.json", converted)):
            (staging / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        staging.rename(output)
    return {"questions": len(converted), "documents": len(documents),
            "dataset_sha256": sha256((output / "manifest.json").read_bytes() + b"\0"
                                     + (output / "questions.json").read_bytes()).hexdigest()}


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=root)
    args = parser.parse_args()
    pack = root / ".blindtest"
    if pack.is_symlink():
        print("UNSAFE_PRIVATE_PACK_PATH")
        return 1
    ignored = subprocess.run(["git", "check-ignore", "--quiet", str(pack / "out" / "runner")], cwd=root)
    if ignored.returncode:
        print("PRIVATE_OUTPUT_NOT_IGNORED")
        return 1
    try:
        print(json.dumps(convert(pack, args.source_root)))
    except (OSError, ValueError, KeyError, TypeError, UnicodeError):
        print("PRIVATE_PACK_CONVERSION_FAILED")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
