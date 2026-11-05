"""Shared public synthetic answer-repair fixtures for sync and SSE tests."""

import json

from knowflow_ai.protocol import CONTRACT_VERSION


_BASE_REQUEST = {
    "contract_version": CONTRACT_VERSION,
    "request_id": "repair-matrix-test",
    "question": "索引何时可检索？",
    "scope": {
        "owner_id": "user-example-a",
        "knowledge_base_id": "kb-example-a",
        "snapshot_id": "snapshot-example-1",
        "indexes": [{
            "document_id": "doc-example-1",
            "content_version_id": "content-example-1",
            "index_version_id": "index-example-1",
        }],
    },
}

_FIRST = {
    "answer": "索引 READY 后才可检索，缓存默认关闭[src-evidence-1][src-evidence-2]。",
    "has_answer": True,
    "source_ids": ["src-evidence-1", "src-evidence-2"],
}

_SCENARIOS = {
    "N0": (
        "公司 2027 年净利润是多少？",
        "原始资料说明索引 READY 后才可检索。",
        "原始资料说明缓存默认关闭。",
        "原始资料说明缓存默认关闭[src-evidence-2]。",
        ["src-evidence-2"],
    ),
    "N1": (
        "公司 2027 年净利润是多少？",
        "原始资料说明索引 READY 后才可检索。",
        "原始资料说明公司缓存默认关闭。",
        "公司缓存默认关闭[src-evidence-2]。",
        ["src-evidence-2"],
    ),
    "N2": (
        "缓存默认关闭时，公司 2027 年净利润是多少？",
        "原始资料说明索引 READY 后才可检索。",
        "原始资料说明缓存默认关闭。",
        "缓存默认关闭[src-evidence-2]。",
        ["src-evidence-2"],
    ),
    "N3": (
        "缓存默认关闭时，公司 2027 年净利润是多少？",
        "原始资料说明索引 READY 后才可检索。",
        "原始资料说明公司 2027 年缓存默认关闭。",
        "公司 2027 年缓存默认关闭[src-evidence-2]。",
        ["src-evidence-2"],
    ),
    "N4": (
        "缓存默认关闭时，公司 2027 年净利润有多高？",
        "原始资料说明索引 READY 后才可检索。",
        "原始资料说明公司 2027 年缓存默认关闭。",
        "公司 2027 年缓存默认关闭[src-evidence-2]。",
        ["src-evidence-2"],
    ),
    "P0": (
        "2027 年索引何时可检索？",
        "原始资料说明 2027 年索引 READY 后才可检索。",
        "原始资料说明缓存默认关闭。",
        "原始资料说明 2027 年索引 READY 后才可检索[src-evidence-1]。",
        ["src-evidence-1"],
    ),
    "P1": (
        "2027 年缓存默认关闭吗？",
        "原始资料说明索引 READY 后才可检索。",
        "原始资料说明 2027 年缓存默认关闭。",
        "原始资料说明 2027 年缓存默认关闭[src-evidence-2]。",
        ["src-evidence-2"],
    ),
}


def repair_scenario(name):
    question, first_text, second_text, repaired_text, repaired_ids = _SCENARIOS[name]
    request = {**_BASE_REQUEST, "scope": {**_BASE_REQUEST["scope"],
                                            "indexes": [dict(_BASE_REQUEST["scope"]["indexes"][0])]}}
    request["question"] = question
    evidence = [
        {"source_id": "src-evidence-1", "document_id": "doc-example-1",
         "content_version_id": "content-example-1", "index_version_id": "index-example-1",
         "chunk_id": "chunk-example-1", "text_content": first_text,
         "locator": {"kind": "text_range", "start": 0, "end": len(first_text),
                     "unit": "unicode_code_point"}},
        {"source_id": "src-evidence-2", "document_id": "doc-example-1",
         "content_version_id": "content-example-1", "index_version_id": "index-example-1",
         "chunk_id": "chunk-example-2", "text_content": second_text,
         "locator": {"kind": "text_range", "start": 0, "end": len(second_text),
                     "unit": "unicode_code_point"}},
    ]
    repaired = {"answer": repaired_text, "has_answer": True,
                "source_ids": list(repaired_ids)}
    return request, evidence, dict(_FIRST), repaired


class MatrixRepairModel:
    """Deterministic first generation and one re-ask for both route tests."""

    def __init__(self, first, repaired):
        self.first = first
        self.repaired = repaired
        self.generate_calls = 0
        self.repair_calls = 0
        self.previous_answers = []

    async def generate(self, question, evidence, *, request_id):
        self.generate_calls += 1
        return self.first

    async def stream_content(self, question, evidence, *, request_id):
        self.generate_calls += 1
        yield json.dumps(self.first, ensure_ascii=False)

    async def generate_repair(self, question, evidence, previous_answer, *, request_id):
        self.repair_calls += 1
        self.previous_answers.append(previous_answer)
        return self.repaired

    async def aclose(self):
        return None
