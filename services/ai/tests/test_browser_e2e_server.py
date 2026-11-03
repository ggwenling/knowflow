import asyncio
import json
import sys
from pathlib import Path

import pytest

from knowflow_ai.adapters import ProcessingError


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from browser_e2e_server import BrowserE2ELlm


def test_synthetic_llm_streams_incremental_cited_answer_without_provider():
    model = BrowserE2ELlm()
    async def collect():
        return [fragment async for fragment in model.stream_content(
            "问题内容", [{"source_id": "source-1"}], request_id="request-1")]

    fragments = asyncio.run(collect())

    result = json.loads("".join(fragments))
    assert len(fragments) > 1
    assert result == {
        "answer": "本地合成验证：问题内容 [source-1]",
        "has_answer": True,
        "source_ids": ["source-1"],
    }


@pytest.mark.parametrize("mode,failure", [("error", ProcessingError), ("cancelled", asyncio.CancelledError)])
def test_synthetic_failure_occurs_after_a_visible_delta(mode, failure):
    from knowflow_ai.streaming import IncrementalAnswerParser

    async def collect():
        stream = BrowserE2ELlm().stream_content(
            f"[e2e:{mode}]", [{"source_id": "source-1"}], request_id="request-1")
        parser = IncrementalAnswerParser()
        assert parser.feed(await anext(stream)) == "合成中断片段"
        with pytest.raises(failure):
            await anext(stream)

    asyncio.run(collect())


def test_synthetic_slow_stream_can_be_closed_after_first_delta():
    async def collect():
        stream = BrowserE2ELlm().stream_content(
            "[e2e:slow]", [{"source_id": "source-1"}], request_id="request-1")
        assert "合成中断片段" in await anext(stream)
        await stream.aclose()
        with pytest.raises(StopAsyncIteration):
            await anext(stream)

    asyncio.run(collect())


@pytest.mark.parametrize("mode", ["slow", "timeout"])
def test_synthetic_slow_stream_would_complete_with_valid_citations(monkeypatch, mode):
    from knowflow_ai.answering import AnswerService
    from knowflow_ai.streaming import IncrementalAnswerParser
    from test_answering import FakeRetriever, _contract, _evidence, _request

    async def no_delay(_seconds):
        pass

    monkeypatch.setattr(asyncio, "sleep", no_delay)
    evidence, request = _evidence(), _request()
    service = AnswerService("unused", _contract(), retriever=FakeRetriever(evidence))

    async def collect():
        parser = IncrementalAnswerParser()
        async for fragment in BrowserE2ELlm().stream_content(
                f"[e2e:{mode}]", evidence, request_id=request["request_id"]):
            parser.feed(fragment)
        return service._response_from_generated(request, evidence, parser.finish())

    response = asyncio.run(collect())
    assert response["has_answer"] is True
    assert response["sources"][0]["source_id"] == evidence[0]["source_id"]
