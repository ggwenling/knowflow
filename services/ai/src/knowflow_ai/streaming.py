"""Bounded provider SSE decoding and the internal answer event iterator."""
import asyncio
from contextlib import aclosing
import json
import time

import httpx

from .adapters import ProcessingError
from .config import ConfigurationError
from .protocol import CONTRACT_VERSION

MAX_ANSWER_CODEPOINTS = 16000
MAX_JSON_CODEPOINTS = 65536
REFUSAL = "没有足够的资料证据回答这个问题。"


def _model_failure():
    return ProcessingError("MODEL_FAILURE", 502, retryable=False)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


class IncrementalAnswerParser:
    """Decode only a top-level answer string; validate the whole JSON at EOF.

    A false/unknown has_answer never exposes the model's provisional refusal.
    The provider prompt asks for has_answer first; arbitrary JSON key order is
    supported by buffering the bounded answer until that decision is known.
    """

    def __init__(self):
        self.text = ""
        self.position = 0
        self.state = "start"
        self.key = None
        self.keys = set()
        self.answer = ""
        self.has_answer = None
        self.emitted = 0
        self.decoder = json.JSONDecoder(object_pairs_hook=_unique_object)

    def feed(self, content):
        self.text += content
        if len(self.text) > MAX_JSON_CODEPOINTS:
            raise _model_failure()
        try:
            self._parse()
        except (ValueError, TypeError, KeyError):
            raise _model_failure() from None
        if self.has_answer is True:
            delta = self.answer[self.emitted:]
            self.emitted = len(self.answer)
            return delta
        return ""

    def _parse(self):
        while self.position < len(self.text):
            char = self.text[self.position]
            if self.state == "answer":
                if char == '"':
                    self.position += 1
                    self.state = "separator"
                    continue
                if char == "\\":
                    if len(self.text) - self.position < 2:
                        return
                    escape = self.text[self.position + 1]
                    escapes = {'"': '"', "\\": "\\", "/": "/", "b": "\b",
                               "f": "\f", "n": "\n", "r": "\r", "t": "\t"}
                    width = 2
                    if escape == "u":
                        if len(self.text) - self.position < 6:
                            return
                        value = int(self.text[self.position + 2:self.position + 6], 16)
                        width = 6
                        if 0xD800 <= value <= 0xDBFF:
                            if len(self.text) - self.position < 12:
                                return
                            if self.text[self.position + 6:self.position + 8] != "\\u":
                                raise ValueError
                            low = int(self.text[self.position + 8:self.position + 12], 16)
                            if not 0xDC00 <= low <= 0xDFFF:
                                raise ValueError
                            value = 0x10000 + ((value - 0xD800) << 10) + low - 0xDC00
                            width = 12
                        elif 0xDC00 <= value <= 0xDFFF:
                            raise ValueError
                        decoded = chr(value)
                    else:
                        decoded = escapes[escape]
                    self.position += width
                else:
                    if ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF:
                        raise ValueError
                    decoded = char
                    self.position += 1
                self.answer += decoded
                if len(self.answer) > MAX_ANSWER_CODEPOINTS:
                    raise ValueError
                continue
            if char.isspace():
                self.position += 1
                continue
            if self.state == "start":
                if char != "{":
                    raise ValueError
                self.state = "key"
                self.position += 1
            elif self.state == "key":
                if char != '"':
                    raise ValueError
                try:
                    key, end = self.decoder.raw_decode(self.text, self.position)
                except json.JSONDecodeError:
                    return
                if key not in {"answer", "has_answer", "source_ids"} or key in self.keys:
                    raise ValueError
                self.keys.add(key)
                self.key = key
                self.position, self.state = end, "colon"
            elif self.state == "colon":
                if char != ":":
                    raise ValueError
                self.position += 1
                self.state = "value"
            elif self.state == "value":
                if self.key == "answer":
                    if char != '"':
                        raise ValueError
                    self.position += 1
                    self.state = "answer"
                    continue
                try:
                    value, end = self.decoder.raw_decode(self.text, self.position)
                except json.JSONDecodeError:
                    return
                # Wait for a delimiter so a partial number/literal cannot be accepted.
                if end == len(self.text):
                    return
                if self.key == "has_answer":
                    if type(value) is not bool:
                        raise ValueError
                    self.has_answer = value
                elif (not isinstance(value, list)
                      or len(value) > 5 or any(not isinstance(item, str) for item in value)):
                    raise ValueError
                self.position, self.state = end, "separator"
            elif self.state == "separator":
                if char == ",":
                    self.state = "key"
                elif char == "}":
                    self.state = "done"
                else:
                    raise ValueError
                self.position += 1
            else:
                raise ValueError

    def finish(self):
        try:
            result = json.loads(self.text, object_pairs_hook=_unique_object)
            if self.state != "done" or self.keys != {"answer", "has_answer", "source_ids"}:
                raise ValueError
            return result
        except (ValueError, TypeError):
            raise _model_failure() from None


async def provider_content(adapter, question, evidence, *, request_id):
    """Yield real OpenAI-compatible SSE delta.content, never completed JSON."""
    payload = adapter._payload(question, evidence)
    payload["stream"] = True
    payload["messages"][0]["content"] += "先输出 has_answer，再输出 answer，最后输出 source_ids。"
    finished = done = False
    total_bytes = 0
    pending = bytearray()
    data_lines = []
    try:
        async with adapter._client.stream(
                "POST", adapter.settings.base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": "Bearer " + adapter.settings.api_key,
                         "Content-Type": "application/json", "Accept": "text/event-stream",
                         "X-Request-ID": request_id},
                json=payload, timeout=adapter.settings.timeout_seconds,
                follow_redirects=False) as response:
            if response.status_code != 200:
                raise ProcessingError("MODEL_FAILURE", 502,
                                      retryable=response.status_code == 429 or response.status_code >= 500)
            if response.headers.get("content-type", "").split(";", 1)[0].strip() != "text/event-stream":
                raise _model_failure()
            async for part in response.aiter_bytes():
                total_bytes += len(part)
                if total_bytes > adapter.settings.max_response_bytes:
                    raise _model_failure()
                pending.extend(part)
                while b"\n" in pending:
                    line, _, remainder = pending.partition(b"\n")
                    pending = bytearray(remainder)
                    line = line.rstrip(b"\r")
                    if line:
                        if line.startswith(b"data:"):
                            data_lines.append(line[5:].lstrip(b" "))
                        elif not line.startswith((b":", b"event:", b"id:", b"retry:")):
                            raise _model_failure()
                        continue
                    if not data_lines:
                        continue
                    raw = b"\n".join(data_lines)
                    data_lines.clear()
                    if done:
                        raise _model_failure()
                    if raw == b"[DONE]":
                        if not finished:
                            raise _model_failure()
                        done = True
                        continue
                    chunk = json.loads(raw, object_pairs_hook=_unique_object)
                    if not isinstance(chunk, dict) or chunk.get("model") != adapter.settings.model:
                        raise _model_failure()
                    choices = chunk.get("choices")
                    if not isinstance(choices, list) or len(choices) != 1 or finished:
                        raise _model_failure()
                    choice = choices[0]
                    if not isinstance(choice, dict) or choice.get("index") != 0:
                        raise _model_failure()
                    delta = choice.get("delta")
                    if not isinstance(delta, dict):
                        raise _model_failure()
                    content = delta.get("content")
                    if content is not None:
                        if not isinstance(content, str):
                            raise _model_failure()
                        if content:
                            yield content
                    reason = choice.get("finish_reason")
                    if reason is not None:
                        if reason != "stop":
                            raise _model_failure()
                        finished = True
            if pending or data_lines or not done:
                raise _model_failure()
    except ProcessingError:
        raise
    except httpx.TimeoutException:
        raise ProcessingError("MODEL_TIMEOUT", 504, retryable=True) from None
    except httpx.HTTPError:
        raise ProcessingError("MODEL_FAILURE", 502, retryable=True) from None
    except (ValueError, TypeError, KeyError, UnicodeDecodeError):
        raise _model_failure() from None


async def answer_events(service, request):
    """One event iterator, sequence 1..N and one terminal on exhaustion.

    Deltas are provisional until sources/completed. Cancellation of an active
    anext closes provider/retrieval first, then yields cancelled once. Closing an
    iterator or an HTTP disconnect closes resources without a deliverable event.
    """
    from .answering import ANSWER_DEADLINE_SECONDS
    service._contract.validate("TrustedAnswerRequest", request)
    sequence = 0

    def event(kind, **fields):
        nonlocal sequence
        sequence += 1
        value = {"contract_version": CONTRACT_VERSION, "request_id": request["request_id"],
                 "sequence": sequence, "event": kind, **fields}
        service._contract.validate("AnswerStreamEvent", value)
        return value

    yield event("started")
    try:
        deadline = time.monotonic() + ANSWER_DEADLINE_SECONDS
        async with asyncio.timeout(ANSWER_DEADLINE_SECONDS):
            evidence = await service._retrieve_evidence(request, deadline)
        if evidence:
            model = service._llm_factory()
            parser = IncrementalAnswerParser()
            try:
                async with aclosing(model.stream_content(
                        request["question"], evidence, request_id=request["request_id"])) as content:
                    while True:
                        try:
                            async with asyncio.timeout(max(0, deadline - time.monotonic())):
                                fragment = await anext(content)
                        except StopAsyncIteration:
                            break
                        delta = parser.feed(fragment)
                        if delta:
                            yield event("delta", delta=delta)
            finally:
                await model.aclose()
            generated = parser.finish()
        else:
            generated = {"answer": REFUSAL, "has_answer": False, "source_ids": []}
        if time.monotonic() >= deadline:
            raise TimeoutError
        response = service._response_from_generated(request, evidence, generated)
        if not response["has_answer"]:
            yield event("delta", delta=response["answer"])
        yield event("sources", has_answer=response["has_answer"], sources=response["sources"])
        terminal = event("completed")
    except asyncio.CancelledError:
        terminal = event("cancelled")
    except (TimeoutError, ProcessingError, ConfigurationError) as exc:
        timeout = isinstance(exc, TimeoutError) or getattr(exc, "status", None) == 504
        code = "PROCESSING_TIMEOUT" if timeout else "AI_PROCESSING_FAILED"
        terminal = event("error", code=code, message=code,
                         retryable=timeout or getattr(exc, "retryable", False))
    except Exception:
        terminal = event("error", code="AI_PROCESSING_FAILED", message="AI_PROCESSING_FAILED", retryable=False)
    yield terminal
