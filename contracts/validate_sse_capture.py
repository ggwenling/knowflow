"""Validate captured Java SSE frames against the draft.10 shared schema."""
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]


def validate(path):
    schema = json.loads((ROOT / "contracts/schemas/protocol.schema.json").read_text(
        encoding="utf-8"))
    target = {**schema, "$ref": "#/$defs/AnswerStreamEvent"}
    validator = Draft202012Validator(target, format_checker=FormatChecker())
    captures = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(captures, dict) or set(captures) != {"text", "pdf", "error", "cancelled", "timeout", "refusal"}:
        raise ValueError("INVALID_SSE_CAPTURE")
    counts = {}
    for kind, frames in captures.items():
        if not isinstance(frames, list) or not frames:
            raise ValueError("MISSING_SSE_FRAMES")
        request_id = None
        for sequence, frame in enumerate(frames, 1):
            if (not isinstance(frame, dict) or set(frame) != {"name", "data"}
                    or not isinstance(frame["name"], str)
                    or not isinstance(frame["data"], dict)
                    or frame["name"] != frame["data"].get("event")
                    or frame["data"].get("sequence") != sequence):
                raise ValueError(f"INVALID_SSE_FRAME_{kind}_{sequence}")
            errors = list(validator.iter_errors(frame["data"]))
            if errors:
                error = errors[0]
                location = ".".join(str(part) for part in error.absolute_path)
                raise ValueError(f"SSE_SCHEMA_MISMATCH_{kind}_{sequence}_{location}")
            if sequence == 1:
                request_id = frame["data"]["request_id"]
            if frame["data"]["request_id"] != request_id:
                raise ValueError(f"SSE_REQUEST_MISMATCH_{kind}_{sequence}")
        names = [frame["name"] for frame in frames]
        terminal = "error" if kind == "timeout" else kind if kind in {"error", "cancelled"} else "completed"
        # Completed/refusal: started → delta+ → sources → completed (delta required).
        # Failure terminals: started → error|cancelled only — answer text is buffered until
        # citation validation, so aborted/failed streams emit no delta (answer-streaming.md).
        if (names[0] != "started" or names.count("started") != 1
                or names[-1] != terminal
                or sum(name in {"completed", "error", "cancelled"} for name in names) != 1
                or (terminal == "completed" and ("delta" not in names or names[-2] != "sources"
                    or any(name != "delta" for name in names[1:-2])))
                or (terminal != "completed" and (len(names) != 2 or "delta" in names or "sources" in names))):
            raise ValueError(f"SSE_LIFECYCLE_MISMATCH_{kind}")
        if kind == "timeout" and frames[-1]["data"]["code"] != "PROCESSING_TIMEOUT":
            raise ValueError("SSE_TIMEOUT_CODE_MISMATCH")
        if kind == "refusal" and (frames[-2]["data"]["has_answer"] or frames[-2]["data"]["sources"]):
            raise ValueError("SSE_REFUSAL_MISMATCH")
        counts[kind] = len(frames)
    return counts


if __name__ == "__main__":
    try:
        result = validate(sys.argv[1])
    except (IndexError, OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"FAIL: {error}") from None
    print("PASS: shared AnswerStreamEvent schema and lifecycle; "
          + ", ".join(f"{kind}={count} frames" for kind, count in result.items()))
