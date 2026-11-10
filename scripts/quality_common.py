"""Shared integrity checks for automated acceptance. No provider calls."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MODEL = "gpt-6.1-sol"
STATUSES = {"PASS", "FAIL", "BLOCKED", "INCOMPLETE"}


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def instant(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_TIMESTAMP")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("INVALID_TIMESTAMP")
    return parsed.astimezone(timezone.utc)


def now():
    return datetime.now(timezone.utc).isoformat()


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def safe_child(root, relative):
    root = Path(root).resolve()
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        raise ValueError("UNSAFE_ARTIFACT_PATH")
    result = (root / rel).resolve()
    if not result.is_relative_to(root) or result == root:
        raise ValueError("UNSAFE_ARTIFACT_PATH")
    return result


def private_root(path, repo=ROOT):
    original = Path(path).absolute()
    resolved = original.resolve()
    if original != resolved or resolved.is_relative_to(Path(repo).resolve()):
        raise ValueError("PRIVATE_ROOT_MUST_BE_EXTERNAL")
    if not resolved.is_dir():
        raise ValueError("PRIVATE_ROOT_MISSING")
    return resolved


def verify_receipt(path, *, role, run_id, candidate_sha, artifacts, artifact_root, now_at=None):
    """Verify an envelope issued by a trusted launcher, never a model's self-report.

    The issuer owns KNOWFLOW_QA_ATTESTATION_KEY. The acceptance scripts only
    verify envelopes; they do not issue them or infer identity from filenames.
    """
    key = os.environ.get("KNOWFLOW_QA_ATTESTATION_KEY", "")
    if len(key.encode("utf-8")) < 32:
        raise ValueError("TRUSTED_LAUNCHER_KEY_REQUIRED")
    receipt = read_json(path)
    required = {"version", "model", "role", "run_id", "candidate_sha", "execution_id",
                "session_id", "issued_at", "valid_until", "artifacts", "signature"}
    if not isinstance(receipt, dict) or set(receipt) != required:
        raise ValueError("INVALID_EXECUTION_RECEIPT")
    unsigned = {k: v for k, v in receipt.items() if k != "signature"}
    expected = hmac.new(key.encode("utf-8"), canonical(unsigned), "sha256").hexdigest()
    if not isinstance(receipt["signature"], str) or not hmac.compare_digest(receipt["signature"], expected):
        raise ValueError("UNTRUSTED_EXECUTION_RECEIPT")
    if (type(receipt["version"]) is not int or receipt["version"] != 1 or receipt["model"] != MODEL or receipt["role"] != role
            or receipt["run_id"] != run_id or receipt["candidate_sha"] != candidate_sha
            or not re.fullmatch(r"[0-9a-f]{40}", candidate_sha)
            or not all(isinstance(receipt[k], str) and receipt[k].strip() for k in ("session_id", "execution_id"))):
        raise ValueError("EXECUTION_IDENTITY_MISMATCH")
    current = now_at or datetime.now(timezone.utc)
    if not instant(receipt["issued_at"]) <= current <= instant(receipt["valid_until"]):
        raise ValueError("EXECUTION_RECEIPT_EXPIRED")
    if not isinstance(receipt["artifacts"], dict):
        raise ValueError("INVALID_RECEIPT_ARTIFACTS")
    for artifact in artifacts:
        target = safe_child(artifact_root, artifact)
        if receipt["artifacts"].get(artifact) != digest(target):
            raise ValueError("EXECUTION_ARTIFACT_MISMATCH")
    return receipt


def run_cli(main):
    try:
        return main()
    except (OSError, ValueError, KeyError, TypeError) as error:
        reason = str(error)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{2,100}", reason):
            reason = "INVALID_OR_UNAVAILABLE_INPUT"
        print(json.dumps({"status": "BLOCKED", "reason": reason}))
        return 1
