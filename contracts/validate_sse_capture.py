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
    if not isinstance(captures, dict) or set(captures) != {"text", "pdf"}:
        raise ValueError("INVALID_SSE_CAPTURE")
    counts = {}
    for kind, frames in captures.items():
        if not isinstance(frames, list) or not frames:
            raise ValueError("MISSING_SSE_FRAMES")
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
        counts[kind] = len(frames)
    return counts


if __name__ == "__main__":
    try:
        result = validate(sys.argv[1])
    except (IndexError, OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"FAIL: {error}") from None
    print("PASS: shared AnswerStreamEvent schema; "
          f"TXT={result['text']} frames, PDF={result['pdf']} frames")
