"""Bind one captured retrieval trace to one service answer as a runner-v2 row."""
from hashlib import sha256
import importlib.util
import math
from pathlib import Path
import re


def _local(name):
    spec = importlib.util.spec_from_file_location(
        "knowflow_eval_" + name, Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_mapping = _local("mapping")
_MARKER = re.compile(r"\[([A-Za-z0-9][A-Za-z0-9._:-]{0,127})\]", re.ASCII)
_ERROR_CODE = re.compile(r"[A-Z0-9_]{1,80}\Z", re.ASCII)


def _latency(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("INVALID_LATENCY")


def _mapped_trace(runtime_question_id, trace, mappings, latency_ms):
    _latency(latency_ms)
    if not isinstance(trace, list):
        raise ValueError("TRACE_NOT_AVAILABLE")
    runtime_question_id = _mapping.normalize_question_id(runtime_question_id)
    evidence = _mapping.map_retrieval(runtime_question_id, trace, mappings)
    runtime_to_public = {
        row["source_id"]: _mapping.public_source_id(runtime_question_id, row["source_id"])
        for row in trace
    }
    return evidence, runtime_to_public


def _claim(answer, start, end):
    before = max((answer.rfind(mark, 0, start) for mark in "。！？.!?；;\n"), default=-1)
    following = [answer.find(mark, end) for mark in "。！？.!?；;\n"]
    following = [position for position in following if position >= 0]
    stop = min(following) + 1 if following else len(answer)
    result = answer[before + 1:stop].strip()
    return result or answer[start:end]


def answer_prediction(*, question_id, runtime_question_id, trace, mappings, response, latency_ms):
    """Build a dataset-keyed row from one runtime question and its captured trace."""
    evidence, runtime_to_public = _mapped_trace(
        runtime_question_id, trace, mappings, latency_ms)
    required = {"request_id", "answer", "has_answer", "sources"}
    if (not isinstance(response, dict) or not required <= response.keys()
            or not isinstance(response["request_id"], str)
            or not isinstance(response["answer"], str)
            or type(response["has_answer"]) is not bool
            or not isinstance(response["sources"], list)):
        raise ValueError("INVALID_SERVICE_RESPONSE")
    answer = response["answer"]
    # Match AnswerService citation syntax; other brackets are literal answer text.
    markers = list(_MARKER.finditer(answer))
    source_rows = {}
    for source in response["sources"]:
        if not isinstance(source, dict) or not isinstance(source.get("source_id"), str):
            raise ValueError("INVALID_SERVICE_SOURCES")
        source_id = source["source_id"]
        if source_id in source_rows:
            raise ValueError("INVALID_SERVICE_SOURCES")
        source_rows[source_id] = source
    marker_ids = {marker.group(1) for marker in markers}
    if response["has_answer"]:
        if not answer.strip() or not markers or marker_ids != set(source_rows):
            raise ValueError("INVALID_SERVICE_CITATIONS")
    elif not answer.strip() or markers or source_rows:
        raise ValueError("INVALID_SERVICE_REFUSAL")

    trace_by_id = {row["source_id"]: row for row in trace}
    for source_id, source in source_rows.items():
        runtime = trace_by_id.get(source_id)
        if (runtime is None
                or any(source.get(field) != runtime[field] for field in
                       ("document_id", "content_version_id", "index_version_id"))
                or source.get("locator") != runtime["locator"]):
            raise ValueError("SERVICE_SOURCE_TRACE_MISMATCH")

    citations = []
    remapped_answer = answer
    if response["has_answer"]:
        replacements = {}
        for marker_index, marker in enumerate(markers):
            runtime_id = marker.group(1)
            public_id = runtime_to_public.get(runtime_id)
            evidence_index = next(
                (index for index, row in enumerate(evidence[:5])
                 if row["source_id"] == public_id), None)
            if public_id is None or evidence_index is None:
                raise ValueError("CITATION_OUTSIDE_TOP5")
            replacements[runtime_id] = public_id
            citations.append({
                "id": f"cite-{marker_index}",
                "source_id": public_id,
                "marker_index": marker_index,
                "evidence_index": evidence_index,
            })
        remapped_answer = _MARKER.sub(
            lambda match: "[" + replacements[match.group(1)] + "]", answer)
        for citation, marker in zip(citations, _MARKER.finditer(remapped_answer), strict=True):
            citation["claim"] = _claim(remapped_answer, marker.start(), marker.end())

    return {
        "question_id": question_id,
        "outcome": "answered" if response["has_answer"] else "refused",
        "answer": remapped_answer,
        "answer_sha256": sha256(remapped_answer.encode("utf-8")).hexdigest(),
        "retrieved_evidence": evidence,
        "citations": citations,
        "latency_ms": latency_ms,
        "error_code": None,
    }


def error_prediction(*, question_id, runtime_question_id, trace, mappings,
                     error_code, latency_ms):
    """Build an error row; callers must still supply the captured request trace."""
    evidence, _ = _mapped_trace(runtime_question_id, trace, mappings, latency_ms)
    if not isinstance(error_code, str) or not _ERROR_CODE.fullmatch(error_code):
        raise ValueError("INVALID_ERROR_CODE")
    return {
        "question_id": question_id,
        "outcome": "error",
        "answer": "",
        "answer_sha256": sha256(b"").hexdigest(),
        "retrieved_evidence": evidence,
        "citations": [],
        "latency_ms": latency_ms,
        "error_code": error_code,
    }


async def bind_response(*, trace_store, request_id, question_id, runtime_question_id,
                        mappings, response, latency_ms):
    """Consume the request's single-use trace and build its response row."""
    if not isinstance(response, dict) or response.get("request_id") != request_id:
        raise ValueError("ANSWER_TRACE_REQUEST_MISMATCH")
    trace = await trace_store.take(request_id)
    return answer_prediction(question_id=question_id, runtime_question_id=runtime_question_id,
                             trace=trace, mappings=mappings, response=response,
                             latency_ms=latency_ms)


async def bind_error(*, trace_store, request_id, question_id, runtime_question_id,
                     mappings, error_code, latency_ms):
    """Consume the request's single-use trace and build its error row."""
    trace = await trace_store.take(request_id)
    return error_prediction(question_id=question_id, runtime_question_id=runtime_question_id,
                            trace=trace, mappings=mappings, error_code=error_code,
                            latency_ms=latency_ms)
