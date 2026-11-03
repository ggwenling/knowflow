"""The E2E gate must reject incomplete or mixed-request wire captures."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest


_path = Path(__file__).resolve().parents[3] / "contracts/validate_sse_capture.py"
_spec = importlib.util.spec_from_file_location("validate_sse_capture", _path)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)


def captures():
    result = {}
    for kind in ("text", "pdf", "error", "cancelled", "timeout", "refusal"):
        events = [("started", {}), ("delta", {"delta": "partial"})]
        if kind in {"text", "pdf", "refusal"}:
            events += [("sources", {"has_answer": False, "sources": []}), ("completed", {})]
        elif kind in {"error", "timeout"}:
            code = "PROCESSING_TIMEOUT" if kind == "timeout" else "AI_PROCESSING_FAILED"
            events += [("error", {"code": code, "message": code, "retryable": kind == "timeout"})]
        else:
            events += [("cancelled", {})]
        result[kind] = [{"name": name, "data": {
            "contract_version": "0.2.0-draft.10", "request_id": "request-" + kind,
            "sequence": index, "event": name, **fields,
        }} for index, (name, fields) in enumerate(events, 1)]
    return result


def validate(tmp_path, value):
    path = tmp_path / "capture.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return _module.validate(path)


def test_complete_and_failed_captures_pass(tmp_path):
    assert validate(tmp_path, captures()) == {"text": 4, "pdf": 4, "error": 3, "cancelled": 3, "timeout": 3, "refusal": 4}


@pytest.mark.parametrize("case", ["missing_path", "mixed_request", "sequence", "schema", "after_terminal", "wrong_terminal", "missing_delta", "missing_sources", "sources_before_delta", "timeout_code", "refusal_flag"])
def test_invalid_capture_is_rejected(tmp_path, case):
    value = deepcopy(captures())
    if case == "missing_path":
        del value["cancelled"]
    elif case == "timeout_code":
        value["timeout"][-1]["data"]["code"] = "AI_PROCESSING_FAILED"
    elif case == "refusal_flag":
        value["refusal"][-2]["data"]["has_answer"] = True
    elif case == "mixed_request":
        value["error"][1]["data"]["request_id"] = "other-request"
    elif case == "sequence":
        value["error"][1]["data"]["sequence"] = 3
    elif case == "schema":
        value["error"][-1]["data"]["retryable"] = "false"
    elif case == "after_terminal":
        late = deepcopy(value["error"][1])
        late["data"]["sequence"] = 4
        value["error"].append(late)
    elif case == "wrong_terminal":
        value["cancelled"][-1]["name"] = "completed"
        value["cancelled"][-1]["data"]["event"] = "completed"
    elif case == "sources_before_delta":
        value["text"][1:3] = reversed(value["text"][1:3])
        for sequence, frame in enumerate(value["text"], 1):
            frame["data"]["sequence"] = sequence
    else:
        kind, event = ("cancelled", "delta") if case == "missing_delta" else ("pdf", "sources")
        value[kind] = [frame for frame in value[kind] if frame["name"] != event]
        for sequence, frame in enumerate(value[kind], 1):
            frame["data"]["sequence"] = sequence
    with pytest.raises(ValueError):
        validate(tmp_path, value)
