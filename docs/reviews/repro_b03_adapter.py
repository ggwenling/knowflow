"""Offline B03 review reproductions: all HTTP uses httpx.MockTransport.

Run inside the reviewed project's uv environment:
  python /path/to/repro_b03_adapter.py --repo /path/to/reviewed/repository
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys


async def reproduce(repo):
    import httpx
    from knowflow_ai.embedding import EmbeddingSettings, SiliconFlowEmbeddingAdapter
    from knowflow_ai.protocol import ContractConsumer, InvalidMessage

    key = "synthetic-test-key-" + "x" * 40
    observed = []

    async def valid_provider(request):
        observed.append(request.extensions.get("timeout"))
        return httpx.Response(200, json={
            "model": "BAAI/bge-m3",
            "data": [{"object": "embedding", "index": 0, "embedding": [1.0] * 1024}],
            "usage": {"prompt_tokens": 2, "total_tokens": 2},
        })

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(valid_provider), timeout=60, follow_redirects=True
    ) as client:
        adapter = SiliconFlowEmbeddingAdapter(
            EmbeddingSettings(api_key=key, timeout_seconds=0.1), client
        )
        result = await adapter.embed(["original-synthetic-text"], request_id="q-b03-schema")
        consumer = ContractConsumer(repo / "contracts/schemas/protocol.schema.json")
        try:
            consumer.validate("EmbeddingResult", result)
            schema_result = "ACCEPTED"
        except InvalidMessage as error:
            schema_result = str(error)
        schema_observation = {
            "returned_row_keys": list(result["data"][0]),
            "shared_schema_result": schema_result,
            "configured_timeout_seconds": 0.1,
            "effective_request_timeouts": observed,
        }

    calls = []

    async def redirected_provider(request):
        calls.append({
            "host": request.url.host,
            "original_input_forwarded": json.loads(request.content)["input"]
            == ["original-synthetic-text"],
            "authorization_present": "authorization" in request.headers,
        })
        if len(calls) == 1:
            return httpx.Response(307, headers={"Location": "https://outside.example/receiver"})
        return httpx.Response(200, json={
            "model": "BAAI/bge-m3",
            "data": [{"index": 0, "embedding": [1.0] * 1024}],
        })

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(redirected_provider), follow_redirects=True
    ) as client:
        adapter = SiliconFlowEmbeddingAdapter(EmbeddingSettings(api_key=key), client)
        await adapter.embed(["original-synthetic-text"], request_id="q-b03-redirect")

    return {
        "all_http_mocked": True,
        "external_provider_calls": 0,
        "schema_and_timeout": schema_observation,
        "redirect": {"adapter_returned_success": True, "calls": calls},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    sys.path.insert(0, str(repo / "services/ai/src"))
    print(json.dumps(asyncio.run(reproduce(repo)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
