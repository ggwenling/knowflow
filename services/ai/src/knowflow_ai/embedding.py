"""Bounded SiliconFlow BAAI/bge-m3 embedding adapter (KF2-018 B03)."""
import asyncio
from dataclasses import dataclass, field
import json
import math
import os
from urllib.parse import urlsplit
import re
from typing import Mapping

import httpx

from .adapters import ProcessingError, validate_provider_result
from .config import ConfigurationError


EXPECTED_MODEL = "BAAI/bge-m3"
EXPECTED_DIMENSIONS = 1024
EXPECTED_HOST = "api.siliconflow.cn"
DEFAULT_BASE_URL = "https://api.siliconflow.cn/v1"
_VARIABLE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z", re.ASCII)
_REQUEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z", re.ASCII)


def _json_object_without_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


@dataclass(frozen=True)
class EmbeddingSettings:
    base_url: str = DEFAULT_BASE_URL
    model: str = EXPECTED_MODEL
    dimensions: int = EXPECTED_DIMENSIONS
    key_environment_variable: str = "EMBEDING_KEY"
    api_key: str = field(default="", repr=False)
    timeout_seconds: float = 20.0
    max_batch_items: int = 32
    max_text_codepoints: int = 800
    max_response_bytes: int = 2 * 1024 * 1024

    def __post_init__(self) -> None:
        try:
            parsed = urlsplit(self.base_url)
            port = parsed.port
        except (TypeError, ValueError):
            raise ConfigurationError("EMBEDDING_BASE_URL_INVALID") from None
        if (parsed.scheme != "https" or parsed.hostname != EXPECTED_HOST
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment or port not in (None, 443)
                or parsed.path.rstrip("/") != "/v1"):
            raise ConfigurationError("EMBEDDING_BASE_URL_INVALID")
        if self.model != EXPECTED_MODEL or self.dimensions != EXPECTED_DIMENSIONS:
            raise ConfigurationError("EMBEDDING_PROFILE_UNSUPPORTED")
        if not _VARIABLE_NAME.fullmatch(self.key_environment_variable):
            raise ConfigurationError("EMBEDDING_KEY_SELECTOR_INVALID")
        if (not 32 <= len(self.api_key) <= 4096 or not self.api_key.isascii()
                or any(ord(ch) < 33 or ord(ch) > 126 for ch in self.api_key)):
            raise ConfigurationError("EMBEDDING_CREDENTIAL_UNAVAILABLE")
        if (not math.isfinite(self.timeout_seconds) or not 0 < self.timeout_seconds <= 30
                or type(self.max_batch_items) is not int or not 1 <= self.max_batch_items <= 32
                or type(self.max_text_codepoints) is not int or not 1 <= self.max_text_codepoints <= 800
                or type(self.max_response_bytes) is not int or not 1024 <= self.max_response_bytes <= 2 * 1024 * 1024):
            raise ConfigurationError("EMBEDDING_LIMIT_INVALID")

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> "EmbeddingSettings":
        env = os.environ if environ is None else environ
        selector = env.get("KNOWFLOW_EMBEDDING_KEY_ENV", "EMBEDING_KEY")
        if not _VARIABLE_NAME.fullmatch(selector):
            raise ConfigurationError("EMBEDDING_KEY_SELECTOR_INVALID")
        credential = env.get(selector, "")
        try:
            dimensions = int(env.get("KNOWFLOW_EMBEDDING_DIMENSIONS", str(EXPECTED_DIMENSIONS)))
            timeout = float(env.get("KNOWFLOW_EMBEDDING_TIMEOUT_SECONDS", "20"))
            max_batch = int(env.get("KNOWFLOW_EMBEDDING_MAX_BATCH_ITEMS", "32"))
            max_text = int(env.get("KNOWFLOW_EMBEDDING_MAX_TEXT_CODEPOINTS", "800"))
        except (TypeError, ValueError):
            raise ConfigurationError("EMBEDDING_CONFIGURATION_INVALID") from None
        return cls(
            base_url=env.get("KNOWFLOW_EMBEDDING_BASE_URL", DEFAULT_BASE_URL).strip(),
            model=env.get("KNOWFLOW_EMBEDDING_MODEL", EXPECTED_MODEL).strip(),
            dimensions=dimensions,
            key_environment_variable=selector,
            api_key=credential,
            timeout_seconds=timeout,
            max_batch_items=max_batch,
            max_text_codepoints=max_text,
        )


class SiliconFlowEmbeddingAdapter:
    """One-request, no-retry adapter. The injected HTTP client remains caller-owned."""

    def __init__(self, settings: EmbeddingSettings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=settings.timeout_seconds,
                                                    follow_redirects=False, trust_env=True)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def embed(self, texts: list[str], *, request_id: str) -> dict:
        if not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id):
            raise ProcessingError("INVALID_REQUEST_ID", 400, retryable=False)
        if (not isinstance(texts, list) or not 1 <= len(texts) <= self.settings.max_batch_items
                or any(not isinstance(text, str) or not text
                       or len(text) > self.settings.max_text_codepoints for text in texts)):
            raise ProcessingError("INVALID_EMBEDDING_INPUT", 400, retryable=False)

        payload = {"model": self.settings.model, "input": texts, "encoding_format": "float"}
        try:
            async with self._client.stream(
                    "POST", self.settings.base_url.rstrip("/") + "/embeddings",
                    headers={"Authorization": "Bearer " + self.settings.api_key,
                             "Content-Type": "application/json",
                             "Accept": "application/json"},
                    json=payload,
                    timeout=self.settings.timeout_seconds,
                    follow_redirects=False) as response:
                if response.status_code == 429:
                    raise ProcessingError("MODEL_FAILURE", 502, retryable=True)
                if response.status_code != 200:
                    raise ProcessingError("MODEL_FAILURE", 502, retryable=response.status_code >= 500)
                body = bytearray()
                async for part in response.aiter_bytes():
                    body.extend(part)
                    if len(body) > self.settings.max_response_bytes:
                        raise ProcessingError("MODEL_FAILURE", 502, retryable=False)
        except ProcessingError:
            raise
        except httpx.TimeoutException:
            raise ProcessingError("MODEL_TIMEOUT", 504, retryable=True) from None
        except asyncio.CancelledError:
            raise
        except httpx.HTTPError:
            raise ProcessingError("MODEL_FAILURE", 502, retryable=True) from None
        except Exception:
            # Transport/plugin exceptions can include URL details or request headers.
            raise ProcessingError("MODEL_FAILURE", 502, retryable=False) from None

        try:
            provider_result = json.loads(body, object_pairs_hook=_json_object_without_duplicate_keys)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
            raise ProcessingError("MODEL_FAILURE", 502, retryable=False) from None
        if not isinstance(provider_result, dict):
            raise ProcessingError("MODEL_FAILURE", 502, retryable=False)
        try:
            validate_provider_result(provider_result, self.settings.model,
                                     count=len(texts), dimensions=self.settings.dimensions)
        except ProcessingError:
            raise ProcessingError("MODEL_FAILURE", 502, retryable=False) from None

        # Provider rows may contain fields such as `object` that are not part
        # of the shared internal EmbeddingResult schema. Normalize at this
        # boundary instead of passing provider objects through unchanged.
        rows = sorted(
            ({"index": row["index"], "embedding": row["embedding"]}
             for row in provider_result["data"]),
            key=lambda row: row["index"],
        )
        result = {"request_id": request_id, "model": self.settings.model,
                  "dimensions": self.settings.dimensions, "data": rows}
        usage = provider_result.get("usage")
        if isinstance(usage, dict):
            prompt = usage.get("prompt_tokens")
            total = usage.get("total_tokens")
            if (type(prompt) is int and prompt >= 0 and type(total) is int and total >= prompt):
                result["usage"] = {"prompt_tokens": prompt,
                                   "completion_tokens": total - prompt,
                                   "total_tokens": total}
        return result
