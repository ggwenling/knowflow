import asyncio
import json
import sys
from pathlib import Path


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
