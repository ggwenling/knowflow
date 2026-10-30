"""Q acceptance checks; every provider request uses MockTransport."""
import argparse
import asyncio
import json
from pathlib import Path
import sys


async def verify(repo):
    import httpx
    from knowflow_ai.adapters import ProcessingError
    from knowflow_ai.embedding import EmbeddingSettings, SiliconFlowEmbeddingAdapter
    from knowflow_ai.protocol import ContractConsumer

    key = "synthetic-test-key-" + "x" * 40
    timeouts = []

    async def normal(request):
        timeouts.append(request.extensions["timeout"])
        return httpx.Response(200, json={
            "model": "BAAI/bge-m3", "object": "list",
            "data": [{"object": "embedding", "provider_extra": True,
                      "index": 0, "embedding": [1.0] * 1024}],
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(normal),
                                timeout=60, follow_redirects=True) as client:
        adapter = SiliconFlowEmbeddingAdapter(
            EmbeddingSettings(api_key=key, timeout_seconds=0.1), client)
        result = await adapter.embed(["original-synthetic-text"], request_id="q-recheck-schema")
        ContractConsumer(repo / "contracts/schemas/protocol.schema.json").validate(
            "EmbeddingResult", result)
        assert set(result["data"][0]) == {"index", "embedding"}
        assert all(value == 0.1 for value in timeouts[0].values())
        await adapter.aclose()
        assert not client.is_closed

    calls = []

    async def redirect(request):
        calls.append(request.url.host)
        return httpx.Response(307, headers={"Location": "https://outside.example/receiver"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(redirect),
                                timeout=None, follow_redirects=True) as client:
        adapter = SiliconFlowEmbeddingAdapter(EmbeddingSettings(api_key=key), client)
        try:
            await adapter.embed(["original-synthetic-text"], request_id="q-recheck-redirect")
        except ProcessingError as failure:
            assert failure.code == "MODEL_FAILURE" and not failure.retryable
        else:
            raise AssertionError("A redirect must be rejected")
        assert calls == ["api.siliconflow.cn"]
        await adapter.aclose()
        assert not client.is_closed

    return {"schema": "PASS", "row_keys": sorted(result["data"][0]),
            "effective_timeout": timeouts[0], "redirect": "REJECTED",
            "redirect_request_hosts": calls, "caller_client_ownership": "PASS",
            "external_provider_calls": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    sys.path.insert(0, str(repo / "services/ai/src"))
    print(json.dumps(asyncio.run(verify(repo)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
