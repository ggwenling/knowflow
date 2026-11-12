"""LangChain model execution inside the existing trusted answer boundary."""
import asyncio
from contextlib import aclosing
from contextvars import ContextVar
from dataclasses import replace
from functools import cached_property
import json
import os
import re
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
from .provider_completion import validate_completion, CompletionObserver
from .provider_observability import (emit_call, failure_category, install_safe_logging,
                                     new_call_id, normalize_usage)
from .provider_runtime import run_attempt
from .provider_retry import (
    ProviderRetryPolicy, classify_provider_failure, transport_failure_kind,
    retry_after_seconds, run_provider_with_retry,
)
from .streaming import IncrementalAnswerParser

OUTPUT_TOKENS = 1024
MAX_BYTES = 1024 * 1024
DOMAIN = re.compile(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{0,62}", re.ASCII)


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
    def __init__(self, stream, observer=None):
        self.stream = stream
        self.observer = observer

    async def __aiter__(self):
        size = 0
        async for chunk in self.stream:
            size += len(chunk)
            if size > MAX_BYTES:
                raise ProcessingError("AI_PROCESSING_FAILED", retryable=False, retry_reason="response_too_large")
            if self.observer is not None:
                self.observer.feed(chunk)
            yield chunk
        if self.observer is not None:
            self.observer.finish()

    async def aclose(self):
        await self.stream.aclose()


class _ProxiedAnthropic(ChatAnthropic):
    # The pinned integration constructs its own HTTP client by default.
    _http: httpx2.AsyncClient = PrivateAttr()

    @cached_property
    def _async_client(self):
        return anthropic.AsyncAnthropic(**{**self._client_params, "timeout": self._http.timeout}, http_client=self._http)


class LangChainAnswerModel:
    def __init__(self, settings: LlmSettings | CustomModel, *, runtime, call_context, transport=None, probe=False):
        install_safe_logging()
        try:
            self._initialize(settings, runtime=runtime, call_context=call_context, transport=transport, probe=probe)
        except Exception:
            emit_call(context=call_context, protocol="deepseek" if isinstance(settings, LlmSettings) else settings.protocol,
                      model_id=settings.model if isinstance(settings, LlmSettings) else settings.model_id,
                      key=settings.api_key if isinstance(settings, LlmSettings) else settings.api_key.get_secret_value(),
                      call_id=new_call_id(), category="configuration")
            raise

    def _initialize(self, settings, *, runtime, call_context, transport, probe):
        self.runtime, self.call_context = runtime, call_context
        if (call_context.custom_id is None) != isinstance(settings, LlmSettings):
            raise ValueError("INVALID_MODEL_CALL_CONTEXT")
        if call_context.custom_id is not None and call_context.custom_id != settings.id:
            raise ValueError("INVALID_MODEL_CALL_CONTEXT")
        self._attempt = ContextVar("provider_attempt")
        self._running = False
        self.settings = settings
        self.default = isinstance(settings, LlmSettings)
        self.protocol = "deepseek" if self.default else settings.protocol
        self.model_id = settings.model if self.default else settings.model_id
        self.supports_tools = self.default or settings.supports_tools
        self.search = None
        self.last_usage = None
        self.retry_policy = ProviderRetryPolicy.from_environment() if self.default else None
        self.probe = probe
        self.profile = runtime.limits.timeout_profile(custom=not self.default, probe=probe)
        self.model_key = runtime.model_key(call_context, protocol=self.protocol, endpoint=settings.base_url,
                                           model=self.model_id, key=settings.api_key if self.default
                                           else settings.api_key.get_secret_value())
        library = httpx2 if self.protocol == "anthropic_messages" else httpx
        timeout = library.Timeout(self.profile.total, connect=self.profile.connect)
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
                      streaming=True, timeout=self.profile.total if self.protocol == "anthropic_messages" else timeout)
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
        self._attempt.get().dispatch()
        if request.method != "POST":
            raise ProcessingError("AI_PROCESSING_FAILED", retryable=False, retry_reason="local_input")
        request.headers["Accept-Encoding"] = "identity"
        if self.protocol == "anthropic_messages":
            # Messages-compatible gateways commonly use the original API-key header.
            request.headers.pop("Authorization", None)
            request.headers["x-api-key"] = self.settings.api_key.get_secret_value()
        if self.default:
            payload = json.loads(request.content)
            if payload.get("max_tokens") != OUTPUT_TOKENS:
                raise ProcessingError("AI_PROCESSING_FAILED", retryable=False, retry_reason="local_input")
            try:
                await reserve_provider_call("deepseek", self.model_id, payload)
            except ProcessingError as error:
                error.retry_reason = "local_budget"
                raise

        self._attempt.get().provider_called = True

    async def _on_response(self, response):
        if response.is_redirect or response.headers.get("content-encoding", "identity").lower() != "identity":
            await response.aclose()
            raise ProcessingError("AI_PROCESSING_FAILED", retryable=False,
                                  retry_reason="redirect" if response.is_redirect else "encoding")
        if response.is_stream_consumed and len(response.content) > MAX_BYTES:
            await response.aclose()
            raise ProcessingError("AI_PROCESSING_FAILED", 502, retryable=False, retry_reason="response_too_large")
        payload = json.loads(response.request.content)
        observer = CompletionObserver(protocol=self.protocol, streaming=payload.get("stream", False),
                                      state=self._attempt.get()) if response.is_success else None
        if observer is not None and response.is_stream_consumed:
            try:
                observer.feed(response.content)
                observer.finish()
            except BaseException:
                await response.aclose()
                raise
        response.stream = _BoundedResponse(response.stream, observer)
        if response.is_success:
            # SDKs may stop reading at a terminator and discard the rest. Read
            # within MAX_BYTES first so missing terminators and trailing junk
            # cannot escape validation, including on the agent's ainvoke path.
            try:
                body = await response.aread()
                if len(body) > MAX_BYTES:
                    raise ProcessingError("AI_PROCESSING_FAILED", 502, retryable=False, retry_reason="response_too_large")
                payload = json.loads(response.request.content)
                streaming = payload.get("stream", False)
                content_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
                if streaming and content_type != "text/event-stream":
                    raise ProcessingError("AI_PROCESSING_FAILED", 502, retryable=False)
                validate_completion(body, protocol=self.protocol, model_id=self.model_id,
                                    streaming=streaming,
                                    allow_tools=bool(payload.get("tools")) and payload.get("tool_choice") != "none")
            finally:
                await response.aclose()
        else:
            try:
                await response.aread()
            finally:
                await response.aclose()

    def set_search(self, search):
        self.search = search

    async def aclose(self):
        await self.http.aclose()
        if self.sync_http is not None:
            self.sync_http.close()

    async def _invoke(self, operation):
        if self._running:
            raise RuntimeError("MODEL_TURN_ALREADY_RUNNING")
        self._running = True
        call_id, attempt = new_call_id(), 0
        self.last_usage = None
        try:
            async with self.runtime.turn(self.call_context, self.model_key, self.profile) as turn:
                state = None

                async def run():
                    nonlocal state, attempt
                    attempt += 1
                    state = turn.new_attempt()
                    token = self._attempt.set(state)
                    self.last_usage = None
                    category = "unknown"
                    try:
                        with tracing_context(enabled=False):
                            result = await run_attempt(operation, state)
                            state.observe_usage(getattr(result, "usage_metadata", None))
                            for message in getattr(result, "result", []):
                                state.observe_usage(getattr(message, "usage_metadata", None))
                            if state.usage:
                                self.last_usage = state.usage
                            state.mark_client_output_started()
                            category = None
                            return result
                    except ProcessingError as error:
                        category = failure_category(error, kind=error.retry_reason or "completion_validation")
                        decision = classify_provider_failure(
                            status=error.provider_status,
                            failure_kind=error.retry_reason or "completion_validation",
                            output_started=state.output_started,
                            client_output_started=state.client_output_started)
                        state.failure_category = decision.reason
                        # Never upgrade a controlled non-retryable completion or budget failure.
                        error.retryable = error.retryable and self.default and decision.retryable
                        raise
                    except (openai.APIError, anthropic.APIError, httpx.HTTPError, httpx2.HTTPError,
                            httpx.InvalidURL, httpx2.InvalidURL) as error:
                        response = getattr(error, "response", None)
                        status = getattr(error, "status_code", None)
                        if status is None and response is not None:
                            status = response.status_code
                        timed_out = isinstance(error, (openai.APITimeoutError, anthropic.APITimeoutError,
                                                       httpx.TimeoutException, httpx2.TimeoutException))
                        kind = transport_failure_kind(error)
                        if kind == "unknown" and error.__cause__ is None:
                            if isinstance(error, (openai.APITimeoutError, anthropic.APITimeoutError)):
                                kind = "read_timeout"
                            elif isinstance(error, (openai.APIConnectionError, anthropic.APIConnectionError)):
                                kind = "connect_failure"
                        decision = classify_provider_failure(
                            status=status, failure_kind=kind,
                            output_started=state.output_started,
                            client_output_started=state.client_output_started)
                        state.failure_category = decision.reason
                        category = failure_category(error, kind=kind)
                        if status is not None:
                            category = failure_category(ProcessingError("AI_PROCESSING_FAILED", provider_status=status))
                        raise ProcessingError(
                            "PROCESSING_TIMEOUT" if timed_out else "AI_PROCESSING_FAILED",
                            504 if timed_out else 502,
                            retryable=self.default and decision.retryable, provider_status=status,
                            retry_reason=kind if timed_out else decision.reason,
                            retry_after=retry_after_seconds(response.headers.get("Retry-After"))
                            if status == 429 and response is not None else None) from None
                    except asyncio.CancelledError:
                        category = "total_timeout" if self.runtime.clock() >= turn.deadline else "cancelled"
                        raise
                    except (openai.OpenAIError, anthropic.AnthropicError, ValueError) as error:
                        category = ("length_truncation" if isinstance(error, openai.LengthFinishReasonError)
                                    else "content_filter" if isinstance(error, openai.ContentFilterFinishReasonError)
                                    else "invalid_completion")
                        state.failure_category = "sdk_parse"
                        raise ProcessingError("AI_PROCESSING_FAILED", 502, retryable=False) from None
                    finally:
                        self.last_usage = normalize_usage(state.usage)
                        emit_call(context=self.call_context, protocol=self.protocol, model_id=self.model_id,
                                  key=self.settings.api_key if self.default else self.settings.api_key.get_secret_value(),
                                  call_id=call_id, attempt=attempt, state=state,
                                  duration_ms=(self.runtime.clock() - state.started) * 1000, category=category)
                        self._attempt.reset(token)

                async def execute():
                    if self.default:
                        policy = replace(self.retry_policy, max_attempts=1) if turn.token.half_open else self.retry_policy
                        return await run_provider_with_retry(
                            run, policy=policy, request_id=self.call_context.request_id, provider="deepseek",
                            clock=self.runtime.clock, outer_deadline=turn.deadline,
                            output_started=lambda: state is not None and state.output_started,
                            client_output_started=lambda: state is not None and state.client_output_started)
                    return await run()

                return await self.runtime.deadline_runner.run(execute, deadline=turn.deadline,
                                                              timeout_kind="total_timeout")
        except BaseException as error:
            if attempt == 0:
                emit_call(context=self.call_context, protocol=self.protocol, model_id=self.model_id,
                          key=self.settings.api_key if self.default else self.settings.api_key.get_secret_value(),
                          call_id=call_id, category=failure_category(error))
            raise
        finally:
            self._running = False

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
        self.call_context = replace(self.call_context, purpose="repair" if previous_answer is not None else "answer")
        messages = answer_messages(question, evidence, previous_answer=previous_answer)
        parser = IncrementalAnswerParser()
        if self.search is not None and self.supports_tools and previous_answer is None:
            result = await self._agent(messages)
            parser.feed(result.text)
            self.last_usage = normalize_usage(result.usage_metadata)
        else:
            async def read():
                attempt_parser = IncrementalAnswerParser()
                async with aclosing(self.model.astream(messages)) as stream:
                    async for chunk in stream:
                        attempt_parser.feed(chunk.text)
                        self._attempt.get().observe_usage(chunk.usage_metadata)
                        if chunk.usage_metadata:
                            self.last_usage = normalize_usage(chunk.usage_metadata)
                return attempt_parser

            parser = await self._invoke(read)
        return parser.finish()

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
