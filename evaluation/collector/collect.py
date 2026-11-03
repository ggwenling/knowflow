"""Collect one Java-authorized question and bind its Python trace to runner v2."""
import importlib.util
from pathlib import Path
import time
from uuid import uuid4

_spec = importlib.util.spec_from_file_location("collection_prediction", Path(__file__).with_name("prediction.py"))
prediction = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prediction)


async def collect_question(*, java, ai, knowledge_base_id, question, question_id,
                           mappings, lookup_question):
    """Clients own credentials; lookup uses the unique idempotency key to read Java's row."""
    key = str(uuid4())
    started = time.monotonic()
    response = await java.post(f"/api/v1/knowledge-bases/{knowledge_base_id}/questions",
                               headers={"Idempotency-Key": key}, json={"question": question})
    runtime = await lookup_question(key)
    if not runtime or not runtime.get("request_id") or not runtime.get("id"):
        raise ValueError("JAVA_QUESTION_RECORD_MISSING")
    request_id = runtime["request_id"]
    captured = await ai.post("/internal/evaluation/results/" + request_id)
    if captured.status_code != 200:
        raise ValueError("EVALUATION_CAPTURE_MISSING")
    payload = captured.json()
    if payload.get("request_id") != request_id or payload.get("trace") is None:
        raise ValueError("EVALUATION_TRACE_INCOMPLETE")
    latency_ms = (time.monotonic() - started) * 1000
    if response.status_code != 200:
        code = runtime.get("failure_code")
        return prediction.error_prediction(
            question_id=question_id, runtime_question_id=runtime["id"],
            trace=payload["trace"], mappings=mappings, error_code=code, latency_ms=latency_ms)
    internal = payload.get("response")
    if (payload.get("error_code") is not None or not isinstance(internal, dict)
            or internal.get("request_id") != request_id):
        raise ValueError("EVALUATION_RESPONSE_INCOMPLETE")
    row = prediction.answer_prediction(
        question_id=question_id, runtime_question_id=runtime["id"], trace=payload["trace"],
        mappings=mappings, response=internal, latency_ms=latency_ms)
    public = response.json()
    expected_ids = {cite["source_id"] for cite in row["citations"]}
    public_ids = [source["source_id"] for source in public.get("sources", [])]
    if (public.get("request_id") != request_id or public.get("answer") != row["answer"]
            or public.get("has_answer") != internal["has_answer"]
            or len(set(public_ids)) != len(public_ids) or set(public_ids) != expected_ids):
        raise ValueError("JAVA_PUBLIC_ANSWER_MISMATCH")
    return row
