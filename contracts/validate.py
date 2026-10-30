"""Validate candidate schemas/fixtures; does not test authorization or task state."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


def main():
    root = Path(__file__).resolve().parent
    schema = json.loads((root / "schemas/protocol.schema.json").read_text())
    cases = json.loads((root / "examples/protocol-cases.json").read_text())
    Draft202012Validator.check_schema(schema)
    formats = FormatChecker()
    if "date-time" not in formats.checkers:
        raise SystemExit(
            "Missing RFC 3339 checker; install contracts/requirements-validation.txt"
        )
    names = set()
    failures = []
    for case in cases:
        name = case["name"]
        if name in names:
            raise ValueError(f"Duplicate case name: {name}")
        names.add(name)
        definition = case["definition"]
        if definition not in schema["$defs"]:
            raise ValueError(f"Unknown definition in {name}: {definition}")
        target = {**schema, "$ref": f"#/$defs/{definition}"}
        errors = list(
            Draft202012Validator(target, format_checker=formats).iter_errors(
                case["payload"]
            )
        )
        if (not errors) != case["structurally_valid"]:
            failures.append(name)
    if failures:
        raise SystemExit("FAIL: " + ", ".join(failures))
    print(f"PASS: schema and {len(cases)} structural cases")
    print("Authorization, lease validity and database transitions: NOT EXECUTED")


if __name__ == "__main__":
    main()
