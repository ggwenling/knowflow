import httpx
import pytest

from test_rag_collection import load, _prediction_fixture

collector = load("collect")
mapping = load("mapping")


@pytest.mark.asyncio
@pytest.mark.parametrize("tamper", [False, True])
async def test_collect_binds_java_public_answer_and_single_request_trace(tamper):
    runtime_id, rows, mappings, _scope = _prediction_fixture()
    source = rows[0]
    public_id = mapping.public_source_id(runtime_id, source["source_id"])
    internal = {"request_id": "request-1", "answer": "Fact [" + source["source_id"] + "]",
                "has_answer": True, "sources": [
                    {key: source[key] for key in ("source_id", "document_id", "content_version_id",
                                                 "index_version_id", "locator")}]}
    public = {"request_id": "request-1", "answer": "Fact [" + public_id + "]",
              "has_answer": True, "sources": [{"source_id": public_id}]}
    if tamper:
        public["answer"] = "mismatching public answer"
    keys = []
    async def java_transport(request):
        keys.append(request.headers["Idempotency-Key"])
        return httpx.Response(200, json=public)
    async def ai_transport(request):
        assert request.url.path == "/internal/evaluation/results/request-1"
        return httpx.Response(200, json={"request_id": "request-1", "response": internal,
                                        "error_code": None, "trace": rows})
    async def lookup(key):
        assert keys == [key]
        return {"request_id": "request-1", "id": runtime_id}
    async with httpx.AsyncClient(base_url="http://java.test", transport=httpx.MockTransport(java_transport)) as java:
        async with httpx.AsyncClient(base_url="http://ai.test", transport=httpx.MockTransport(ai_transport)) as ai:
            arguments = dict(java=java, ai=ai, knowledge_base_id="kb", question="synthetic",
                             question_id="fake-1", mappings=mappings, lookup_question=lookup)
            if tamper:
                with pytest.raises(ValueError, match="JAVA_PUBLIC_ANSWER_MISMATCH"):
                    await collector.collect_question(**arguments)
            else:
                row = await collector.collect_question(**arguments)
                assert row["question_id"] == "fake-1"
                assert row["answer"] == public["answer"]
                assert row["retrieved_evidence"][0]["source_id"] == public_id
