import json
import math

import httpx
import pytest

from knowflow_ai.adapters import ProcessingError
from knowflow_ai.config import ConfigurationError
from knowflow_ai.embedding import EmbeddingSettings, SiliconFlowEmbeddingAdapter


KEY = "synthetic-test-key-" + "x" * 40
REQUEST_ID = "embedding-test-01"


def settings(**overrides):
    values = {"api_key": KEY}
    values.update(overrides)
    return EmbeddingSettings(**values)


def provider_response(count=1, *, model="BAAI/bge-m3"):
    return {"model": model,
            "data": [{"index": index, "embedding": [0.25] + [0.5] * 1023}
                     for index in reversed(range(count))],
            "usage": {"prompt_tokens": count * 12, "total_tokens": count * 12}}


@pytest.mark.parametrize("environ,expected_selector", [
    ({"CUSTOM_EMBEDDING_TOKEN": KEY}, "CUSTOM_EMBEDDING_TOKEN"),
    ({"EMBEDING_KEY": KEY, "UNRELATED_API_KEY": "do-not-read"}, "EMBEDING_KEY"),
])
def test_settings_read_only_selected_credential(environ, expected_selector):
    env = {"KNOWFLOW_EMBEDDING_KEY_ENV": expected_selector, **environ}
    config = EmbeddingSettings.from_environment(env)
    assert config.key_environment_variable == expected_selector
    assert config.api_key == KEY
    assert KEY not in repr(config)


@pytest.mark.parametrize("env,code", [
    ({}, "EMBEDDING_CREDENTIAL_UNAVAILABLE"),
    ({"KNOWFLOW_EMBEDDING_KEY_ENV": "BAD-NAME", "BAD-NAME": KEY}, "EMBEDDING_KEY_SELECTOR_INVALID"),
    ({"KNOWFLOW_EMBEDDING_BASE_URL": "http://api.siliconflow.cn/v1", "EMBEDING_KEY": KEY},
     "EMBEDDING_BASE_URL_INVALID"),
    ({"KNOWFLOW_EMBEDDING_BASE_URL": "https://user@api.siliconflow.cn/v1", "EMBEDING_KEY": KEY},
     "EMBEDDING_BASE_URL_INVALID"),
    ({"KNOWFLOW_EMBEDDING_BASE_URL": "https://attacker.example/v1", "EMBEDING_KEY": KEY},
     "EMBEDDING_BASE_URL_INVALID"),
    ({"KNOWFLOW_EMBEDDING_MODEL": "BAAI/bge-reranker-v2-m3", "EMBEDING_KEY": KEY},
     "EMBEDDING_PROFILE_UNSUPPORTED"),
    ({"KNOWFLOW_EMBEDDING_DIMENSIONS": "768", "EMBEDING_KEY": KEY}, "EMBEDDING_PROFILE_UNSUPPORTED"),
])
def test_settings_fail_closed_without_disclosing_credentials(env, code):
    with pytest.raises(ConfigurationError) as exc:
        EmbeddingSettings.from_environment(env)
    assert str(exc.value) == code
    assert KEY not in str(exc.value)


@pytest.mark.asyncio
async def test_real_adapter_maps_request_and_reorders_validated_vectors():
    calls = []

    async def handler(request):
        calls.append(request)
        return httpx.Response(200, json=provider_response(2))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = SiliconFlowEmbeddingAdapter(settings(), client)
    result = await adapter.embed(["合成事实甲", "合成事实乙"], request_id=REQUEST_ID)

    assert len(calls) == 1
    request = calls[0]
    assert str(request.url) == "https://api.siliconflow.cn/v1/embeddings"
    assert request.headers["Authorization"] == "Bearer " + KEY
    assert json.loads(request.content) == {"model": "BAAI/bge-m3",
                                           "input": ["合成事实甲", "合成事实乙"],
                                           "encoding_format": "float"}
    assert result["request_id"] == REQUEST_ID
    assert result["model"] == "BAAI/bge-m3" and result["dimensions"] == 1024
    assert [row["index"] for row in result["data"]] == [0, 1]
    assert all(len(row["embedding"]) == 1024 for row in result["data"])
    assert result["usage"] == {"prompt_tokens": 24, "completion_tokens": 0, "total_tokens": 24}
    assert KEY not in repr(result)
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    {"model": "wrong", "data": [{"index": 0, "embedding": [1.0] * 1024}]},
    {"model": "BAAI/bge-m3", "data": [{"index": 1, "embedding": [1.0] * 1024}]},
    {"model": "BAAI/bge-m3", "data": [{"index": 0, "embedding": [1.0] * 1023}]},
    {"model": "BAAI/bge-m3", "data": [{"index": 0, "embedding": [0.0] * 1024}]},
    {"model": "BAAI/bge-m3", "data": [{"index": 0, "embedding": [math.inf] + [1.0] * 1023}]},
    {"model": "BAAI/bge-m3", "data": []},
])
async def test_adapter_rejects_wrong_model_index_or_vector(payload):
    async def handler(_request):
        return httpx.Response(200, json=payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = SiliconFlowEmbeddingAdapter(settings(), client)
    with pytest.raises(ProcessingError, match="MODEL_FAILURE"):
        await adapter.embed(["synthetic"], request_id=REQUEST_ID)
    await client.aclose()


@pytest.mark.asyncio
async def test_provider_failure_is_fixed_redacted_and_never_retried():
    attempts = 0

    async def handler(_request):
        nonlocal attempts
        attempts += 1
        return httpx.Response(429, text="PRIVATE provider response " + KEY)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = SiliconFlowEmbeddingAdapter(settings(), client)
    with pytest.raises(ProcessingError) as exc:
        await adapter.embed(["synthetic"], request_id=REQUEST_ID)
    assert attempts == 1
    assert exc.value.code == "MODEL_FAILURE" and exc.value.retryable
    assert KEY not in str(exc.value) and "PRIVATE" not in str(exc.value)
    await client.aclose()


@pytest.mark.asyncio
async def test_adapter_bounds_response_and_rejects_redirect_without_following():
    paths = []

    async def oversized(request):
        paths.append(request.url.path)
        return httpx.Response(200, content=b" " * 1025)

    client = httpx.AsyncClient(transport=httpx.MockTransport(oversized))
    adapter = SiliconFlowEmbeddingAdapter(settings(max_response_bytes=1024), client)
    with pytest.raises(ProcessingError, match="MODEL_FAILURE"):
        await adapter.embed(["synthetic"], request_id=REQUEST_ID)
    await client.aclose()

    async def redirect(request):
        paths.append(request.url.path)
        return httpx.Response(307, headers={"Location": "https://attacker.example/steal"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(redirect), follow_redirects=False)
    adapter = SiliconFlowEmbeddingAdapter(settings(), client)
    with pytest.raises(ProcessingError, match="MODEL_FAILURE"):
        await adapter.embed(["synthetic"], request_id=REQUEST_ID)
    assert paths == ["/v1/embeddings", "/v1/embeddings"]
    await client.aclose()


@pytest.mark.asyncio
async def test_provider_timeout_is_retryable_but_adapter_does_not_retry():
    attempts = 0

    async def handler(_request):
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("PRIVATE " + KEY)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = SiliconFlowEmbeddingAdapter(settings(), client)
    with pytest.raises(ProcessingError) as exc:
        await adapter.embed(["synthetic"], request_id=REQUEST_ID)
    assert attempts == 1
    assert exc.value.code == "MODEL_TIMEOUT" and exc.value.retryable
    assert KEY not in str(exc.value)
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("texts,request_id", [([], REQUEST_ID), ([""], REQUEST_ID), (["x" * 801], REQUEST_ID),
                                                (["valid"], "../../private"), (["x"] * 33, REQUEST_ID)])
async def test_invalid_input_fails_before_network(texts, request_id):
    attempts = 0

    async def handler(_request):
        nonlocal attempts
        attempts += 1
        return httpx.Response(200, json=provider_response())

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = SiliconFlowEmbeddingAdapter(settings(), client)
    with pytest.raises(ProcessingError, match="INVALID_"):
        await adapter.embed(texts, request_id=request_id)
    assert attempts == 0
    await client.aclose()
