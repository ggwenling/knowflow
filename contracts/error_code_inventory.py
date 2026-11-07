"""Extract public error codes emitted by Java and Python, then compare them with the schema.

The frozen 0.2.0 contract must enumerate every code a public boundary can return.
The inventories are read from source so adding a code on one side without updating
the shared schema fails contract validation instead of silently drifting.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "contracts" / "schemas" / "protocol.schema.json"
JAVA_FAILURE_PATH = (
    REPO_ROOT
    / "services"
    / "api"
    / "src"
    / "main"
    / "java"
    / "com"
    / "knowflow"
    / "api"
    / "error"
    / "ApiFailure.java"
)
PYTHON_APP_PATH = REPO_ROOT / "services" / "ai" / "src" / "knowflow_ai" / "app.py"

_JAVA_CODE = re.compile(r'new ApiFailure\([^,]+,\s*"([A-Z][A-Z0-9_]+)"')


def java_error_codes(source: str | None = None) -> set[str]:
    text = JAVA_FAILURE_PATH.read_text(encoding="utf-8") if source is None else source
    return set(_JAVA_CODE.findall(text))


def _literal_strings(node: ast.AST) -> set[str]:
    return {
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    }


def python_error_codes(source: str | None = None) -> set[str]:
    text = PYTHON_APP_PATH.read_text(encoding="utf-8") if source is None else source
    tree = ast.parse(text)
    codes: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id == "failure" and len(node.args) >= 3:
            code = node.args[2]
            if isinstance(code, ast.Constant) and isinstance(code.value, str):
                codes.add(code.value)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "code" for t in node.targets):
            continue
        if isinstance(node.value, ast.Call):
            for arg in node.value.args:
                if isinstance(arg, ast.Dict):
                    codes.update(_literal_strings(arg))
    return codes


def schema_error_codes(
    schema: dict | None = None,
) -> tuple[set[str], set[str]]:
    data = (
        json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        if schema is None
        else schema
    )
    error_enum = set(data["$defs"]["Error"]["properties"]["code"]["enum"])
    for branch in data["$defs"]["AnswerStreamEvent"]["oneOf"]:
        properties = branch.get("properties", {})
        if properties.get("event", {}).get("const") == "error":
            return error_enum, set(properties["code"]["enum"])
    raise KeyError("AnswerStreamEvent error branch not found")


def check(schema: dict | None = None) -> list[str]:
    java = java_error_codes()
    python = python_error_codes()
    error_enum, stream_enum = schema_error_codes(schema)
    problems: list[str] = []
    for side, emitted in (("Java", java), ("Python", python)):
        missing = sorted(emitted - error_enum)
        if missing:
            problems.append(f"{side} codes missing from Error.code: {', '.join(missing)}")
        missing_stream = sorted(emitted - stream_enum)
        if missing_stream:
            problems.append(
                f"{side} codes missing from AnswerStreamEvent error.code: "
                f"{', '.join(missing_stream)}"
            )
    if error_enum != stream_enum:
        only_error = sorted(error_enum - stream_enum)
        only_stream = sorted(stream_enum - error_enum)
        problems.append(
            "Error.code and AnswerStreamEvent error.code differ: "
            f"only Error={only_error}, only stream={only_stream}"
        )
    return problems
