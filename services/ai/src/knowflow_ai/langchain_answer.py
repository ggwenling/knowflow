"""LangChain model execution inside the existing trusted answer boundary."""
import asyncio
from contextlib import aclosing
from functools import cached_property
import json
import logging
import os
import re
import time
from typing import Literal
from urllib.parse import urlsplit

import anthropic
import httpx
import httpx2
import openai
from langchain.agents import create_agent
from langchain.agents.middleware import wrap_model_call
from langchain.tools import tool
from langchain_anthropic import ChatAnthropic
from langchain_deepseek import ChatDeepSeek
from langchain_openai import ChatOpenAI
from langsmith import tracing_context
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, SecretStr, UUID4

from .adapters import ProcessingError
from .answering import LlmSettings, answer_messages
from .http_client import build_async_client
from .provider_budget import reserve_provider_call
from .provider_retry import ProviderRetryPolicy, retry_after_seconds, run_provider_with_retry
from .streaming import IncrementalAnswerParser

OUTPUT_TOKENS = 1024
MAX_BYTES = 1024 * 1024
MAX_ATTEMPTS = 3
DOMAIN = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{0,62}", re.ASCII)
_logger = logging.getLogger(__name__)


class CustomModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID4
    base_url: str = Field(max_length=1024)
    protocol: Literal["chat_completions", "responses", "anthropic_messages"]
    model_id: str = Field(min_length=1, max_length=160)
    api_key: SecretStr
    supports_tools: bool

    def validate_destination(self):
        try:
            parsed = urlsplit(self.base_url)
            if (parsed.scheme != "https" or not DOMAIN.fullmatch(parsed.hostname or "")
                    or parsed.port not in (443, None) or parsed.username is not None
                    or parsed.query or parsed.fragment or not re.fullmatch(r"[!-~]{1,2048}",
                                                                         self.api_key.get_secret_value())):
                raise ValueError
        except ValueError:
            raise ProcessingError("INVALID_REQUEST", 400, retryable=False) from None


class _BoundedResponse(httpx.AsyncByteStream, httpx2.AsyncByteStream):
    def __init__(self, stream):
        self.stream = stream

    async def __aiter__(self):
        size = 0
        async for chunk in self.stream:
            size += len(chunk)
            if size > MAX_BYTES:
                raise ProcessingError("AI_PROCESSING_FAILED", retryable=False)
            yield chunk

    async def aclose(self):
        await self.stream.aclose()


class _ProxiedAnthropic(ChatAnthropic):
    # The pinned integration constructs its own HTTP client by default.
    _http: httpx2.AsyncClient = PrivateAttr()

    @cached_property
    def _async_client(self):
        return anthropic.AsyncAnthropic(**self._client_params, http_client=self._http)


class LangChainAnswerModel:
    def __init__(self, settings: LlmSettings | CustomModel, *, transport=None, probe=False):
        self.settings = settings
        self.default = isinstance(settings, LlmSettings)
        self.protocol = "deepseek" if self.default else settings.protocol
        self.model_id = settings.model if self.default else settings.model_id
        self.supports_tools = self.default or settings.supports_tools
        self.search = None
        self.last_usage = None
        self.attempts = 0
        self.request_id = "probe"
        self.retry_policy = ProviderRetryPolicy.from_environment() if self.default else None
        self.probe = probe
        timeout = 5 if probe else 25
        options = {"event_hooks": {"request": [self._before_request], "response": [self._on_response]},
                   "headers": {"Accept-Encoding": "identity"}}
        if self.default and transport is None:
            self.http = build_async_client(timeout, environment_proxy_fallback=True, **options)
        else:
            if not self.default:
                settings.validate_destination()
            proxy = os.environ.get("KNOWFLOW_CUSTOM_LLM_PROXY")
            if transport is None and not proxy:
                raise ProcessingError("AI_PROCESSING_FAILED", 503, retryable=False)
            http_client = httpx2.AsyncClient if self.protocol == "anthropic_messages" else httpx.AsyncClient
            self.http = http_client(timeout=timeout, trust_env=False, follow_redirects=False,
                                    proxy=proxy if transport is None else None, transport=transport, **options)
        key = settings.api_key if self.default else settings.api_key.get_secret_value()
        self.sync_http = None
        shared = dict(model=self.model_id, api_key=key, base_url=settings.base_url, max_retries=0,
                      streaming=True, timeout=timeout)
        if self.protocol == "anthropic_messages":
            self.model = _ProxiedAnthropic(**shared, max_tokens=64 if probe else OUTPUT_TOKENS)
            self.model._http = self.http
        else:
            self.sync_http = httpx.Client(trust_env=False)
            shared.update(http_client=self.sync_http, http_async_client=self.http,
                          max_tokens=64 if probe else OUTPUT_TOKENS)
            if self.default:
                # DeepSeek Chat Completions uses max_tokens for its output limit.
                shared.pop("max_tokens")
                self.model = ChatDeepSeek(**shared, temperature=0, stream_usage=True,
                                          extra_body={"thinking": {"type": "disabled"}, "max_tokens": OUTPUT_TOKENS},
                                          model_kwargs={"response_format": {"type": "json_object"}})
            elif self.protocol == "responses":
                self.model = ChatOpenAI(**shared, use_responses_api=True, store=False)
            else:
                self.model = ChatOpenAI(**shared, use_responses_api=False, stream_usage=False)

    async def _before_request(self, request):
        self.attempts += 1
        if self.attempts > MAX_ATTEMPTS or request.method != "POST":
            raise ProcessingError("AI_PROCESSING_FAILED", retryable=False)
        request.headers["Accept-Encoding"] = "identity"
        if self.protocol == "anthropic_messages":
            # Messages-compatible gateways commonly use the original API-key header.
            request.headers.pop("Authorization", None)
            request.headers["x-api-key"] = self.settings.api_key.get_secret_value()
        if self.default:
            payload = json.loads(request.content)
            if payload.get("max_tokens") != OUTPUT_TOKENS:
                raise ProcessingError("AI_PROCESSING_FAILED", retryable=False)
            await reserve_provider_call("deepseek", self.model_id, payload)

    async def _on_response(self, response):
        if response.is_redirect or response.headers.get("content-encoding", "identity").lower() != "identity":
            await response.aclose()
            raise ProcessingError("AI_PROCESSING_FAILED", retryable=False)
        response.stream = _BoundedResponse(response.stream)

    def set_search(self, search):
        self.search = search

    async def aclose(self):
        await self.http.aclose()
        if self.sync_http is not None:
            self.sync_http.close()

    async def _invoke(self, operation):
        async def run():
            try:
                with tracing_context(enabled=False):
                    return await operation()
            except (openai.APIError, anthropic.APIError, httpx.HTTPError, httpx2.HTTPError) as error:
                status = getattr(error, "status_code", None)
                response = getattr(error, "response", None)
                timed_out = isinstance(error, (openai.APITimeoutError, anthropic.APITimeoutError,
                                               httpx.TimeoutException, httpx2.TimeoutException))
                transient = status in (408, 429, 500, 502, 503, 504) or timed_out or isinstance(
                    error, (openai.APIConnectionError, anthropic.APIConnectionError, httpx.TransportError))
                raise ProcessingError("AI_PROCESSING_FAILED", 504 if timed_out else 502,
                                      retryable=self.default and transient, provider_status=status,
                                      retry_after=retry_after_seconds(response.headers.get("Retry-After"))
                                      if response is not None else None) from None

        if self.default:
            return await run_provider_with_retry(run, policy=self.retry_policy, request_id=self.request_id,
                                                 provider="deepseek")
        return await run()

    async def _agent(self, messages):
        used = False

        @tool
        async def search_knowledge_base(query: str) -> str:
            """Search the same knowledge base for additional evidence using a short query."""
            nonlocal used
            if used or not 1 <= len(query.strip()) <= 500:
                return "[]"
            used = True
            return json.dumps(await self.search(query.strip()), ensure_ascii=False)

        @wrap_model_call
        async def limit_model(request, handler):
            if any(message.type == "tool" for message in request.messages):
                request = request.override(tools=[], tool_choice=None)
            return await self._invoke(lambda: handler(request))

        agent = create_agent(self.model, tools=[search_knowledge_base], middleware=[limit_model])
        with tracing_context(enabled=False):
            result = await agent.ainvoke({"messages": messages}, {"recursion_limit": 8})
        return result["messages"][-1]

    async def _generate(self, question, evidence, request_id, previous_answer=None):
        self.request_id = request_id
        messages = answer_messages(question, evidence, previous_answer=previous_answer)
        started = time.monotonic()
        outcome = "failed"
        try:
            parser = IncrementalAnswerParser()
            if self.search is not None and self.supports_tools and previous_answer is None:
                result = await self._agent(messages)
                parser.feed(result.text)
                self.last_usage = result.usage_metadata
            else:
                async def read():
                    attempt_parser = IncrementalAnswerParser()
                    async with aclosing(self.model.astream(messages)) as stream:
                        async for chunk in stream:
                            attempt_parser.feed(chunk.text)
                            if chunk.usage_metadata:
                                self.last_usage = chunk.usage_metadata
                    return attempt_parser

                parser = await self._invoke(read)
            generated = parser.finish()
            outcome = "success"
            return generated
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        finally:
            _logger.info("llm_call protocol=%s duration_ms=%d outcome=%s", self.protocol,
                         round((time.monotonic() - started) * 1000), outcome)

    async def generate(self, question, evidence, *, request_id):
        return await self._generate(question, evidence, request_id)

    async def generate_repair(self, question, evidence, previous_answer, *, request_id):
        return await self._generate(question, evidence, request_id, previous_answer)

    async def stream_content(self, question, evidence, *, request_id):
        yield json.dumps(await self.generate(question, evidence, request_id=request_id), ensure_ascii=False)

    async def probe_capabilities(self):
        messages = [{"role": "user", "content": "Call report_ready if available, otherwise reply READY."}]

        @tool
        def report_ready() -> str:
            """Report that a connectivity test is ready."""
            return "READY"

        async def probe(model):
            return await self._invoke(lambda: model.ainvoke(messages))

        try:
            result = await probe(self.model.bind_tools([report_ready]))
        except ProcessingError as error:
            if error.provider_status not in (400, 422, 501):
                raise
            result = await probe(self.model)
        supports_tools = bool(result.tool_calls) and all(
            call["name"] == "report_ready" and not call["args"] and call["id"] for call in result.tool_calls)
        if supports_tools:
            messages.append(result)
            messages.extend({"role": "tool", "tool_call_id": call["id"], "content": "READY"}
                            for call in result.tool_calls)
            result = await probe(self.model)
        if not result.text.strip():
            raise ProcessingError("AI_PROCESSING_FAILED", retryable=False)
        return supports_tools
