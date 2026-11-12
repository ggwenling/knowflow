"""Validate bounded provider wire responses before an SDK can discard metadata."""
import json
import re

from .adapters import ProcessingError


class _InvalidCompletion(ValueError):
    def __init__(self, reason):
        self.reason = reason


def _require(condition, reason="completion_validation"):
    if not condition:
        raise _InvalidCompletion(reason)


def _finish_reason(reason):
    if reason in ("length", "max_tokens", "max_output_tokens"):
        raise _InvalidCompletion("length_truncation")
    if reason in ("content_filter", "refusal"):
        raise _InvalidCompletion("content_filter")


class SSEFramer:
    """Incremental bounded framing, shared by observation and final validation."""
    def __init__(self):
        self.buffer = b""
        self.data = []
        self.size = 0

    def feed(self, chunk):
        self.size += len(chunk)
        _require(self.size <= 1024 * 1024)
        self.buffer += chunk
        events = []
        while True:
            match = re.search(rb"\r\n|\r(?!$)|\n", self.buffer)
            if match is None:
                break
            line = self.buffer[:match.start()].decode("utf-8")
            self.buffer = self.buffer[match.end():]
            if not line:
                if self.data:
                    events.append("\n".join(self.data))
                    self.data.clear()
            elif line.startswith("data:"):
                self.data.append(line[5:].removeprefix(" "))
            else:
                _require(line.startswith((":", "event:", "id:", "retry:")))
        return events

    def finish(self):
        # A final lone CR is also a line delimiter.
        events = self.feed(b"\n") if self.buffer.endswith(b"\r") else []
        _require(not self.buffer and not self.data)
        return events


def _events(body):
    framer = SSEFramer()
    yield from framer.feed(body)
    yield from framer.finish()


class CompletionObserver:
    def __init__(self, *, protocol, streaming, state):
        self.protocol, self.streaming, self.state = protocol, streaming, state
        self.framer = SSEFramer() if streaming else None
        state.first_token_observation = "content_event" if streaming else "body_byte"

    def feed(self, chunk):
        if not chunk:
            return
        if not self.streaming:
            self.state.observe_content()
            return
        try:
            self._observe_events(self.framer.feed(chunk))
        except (ValueError, TypeError, KeyError, AttributeError):
            raise ProcessingError("AI_PROCESSING_FAILED", 502, retryable=False) from None

    def _observe_events(self, events):
        for event in events:
            if event != "[DONE]" and self._has_content(json.loads(event)):
                self.state.observe_content()

    def finish(self):
        if self.framer is not None:
            try:
                self._observe_events(self.framer.finish())
            except (ValueError, TypeError, KeyError, AttributeError):
                raise ProcessingError("AI_PROCESSING_FAILED", 502, retryable=False) from None

    def _has_content(self, value):
        if self.protocol in ("deepseek", "chat_completions"):
            for choice in value.get("choices", []):
                delta = choice.get("delta", {})
                if delta.get("content") or delta.get("refusal"):
                    return True
                for call in delta.get("tool_calls", []):
                    function = call.get("function", {})
                    if function.get("name") or function.get("arguments"):
                        return True
            return False
        if self.protocol == "anthropic_messages":
            delta = value.get("delta", {})
            block = value.get("content_block", {})
            return bool(delta.get("text") or delta.get("partial_json") or delta.get("refusal")
                        or block.get("text") or block.get("name"))
        if self.protocol == "responses":
            return bool((value.get("type") in ("response.output_text.delta", "response.refusal.delta",
                                               "response.function_call_arguments.delta") and value.get("delta"))
                        or (value.get("type") == "response.output_item.added"
                            and value.get("item", {}).get("type") == "function_call"
                            and (value["item"].get("name") or value["item"].get("arguments"))))
        return False


def _chat_choice(body, model_id, allow_tools, *, streaming):
    _require(body.get("model") == model_id, "model_mismatch")
    choices = body.get("choices")
    if streaming and choices == []:
        _require(isinstance(body.get("usage"), dict))
        return None, False
    _require(isinstance(choices, list) and len(choices) == 1)
    choice = choices[0]
    _require(choice.get("index") == 0)
    message = choice["delta" if streaming else "message"]
    _require(isinstance(message, dict))
    _require(not message.get("refusal"), "content_filter")
    _require(allow_tools or not (message.get("tool_calls") or message.get("function_call")))
    reason = choice.get("finish_reason")
    _finish_reason(reason)
    _require(reason in (None, "stop") or (allow_tools and reason == "tool_calls"))
    return reason, bool(message.get("tool_calls"))


def _responses_complete(body, model_id, allow_tools):
    _require(body.get("model") == model_id, "model_mismatch")
    _finish_reason((body.get("incomplete_details") or {}).get("reason"))
    _require(body.get("status") == "completed")
    _require(not body.get("error") and not body.get("incomplete_details"))
    output = body["output"]
    _require(isinstance(output, list) and output)
    usable = False
    for item in output:
        _require(item.get("status", "completed") == "completed")
        kind = item["type"]
        if kind == "message":
            _require(item.get("role") == "assistant")
            content = item["content"]
            _require(isinstance(content, list) and content)
            for block in content:
                _require(block.get("type") != "refusal", "content_filter")
                _require(block.get("type") == "output_text")
                _require(isinstance(block.get("text"), str))
                usable |= bool(block["text"])
        elif kind == "function_call":
            _require(allow_tools)
            _require(item.get("name") and item.get("call_id")
                     and isinstance(item.get("arguments"), str))
            usable = True
        else:
            _require(kind == "reasoning")
    _require(usable)


def _validate_stream(body, protocol, model_id, allow_tools):
    finished = done = tools = started = False
    for raw in _events(body):
        _require(not done)
        if protocol in ("deepseek", "chat_completions") and raw == "[DONE]":
            _require(finished)
            done = True
            continue
        event = json.loads(raw)
        _require(isinstance(event, dict))
        if protocol in ("deepseek", "chat_completions"):
            reason, has_tools = _chat_choice(event, model_id, allow_tools, streaming=True)
            if event["choices"] == []:
                _require(finished)
                continue
            _require(not finished)
            tools |= has_tools
            if reason is not None:
                _require(reason != "tool_calls" or tools)
                finished = True
        elif protocol == "responses":
            kind = event["type"]
            if "response" in event:
                _finish_reason((event["response"].get("incomplete_details") or {}).get("reason"))
            _require(kind not in ("error", "response.failed", "response.incomplete"))
            _require(not kind.startswith("response.refusal."), "content_filter")
            _require(allow_tools or not kind.startswith("response.function_call_arguments."))
            if "item" in event:
                _require(event["item"].get("type") != "refusal", "content_filter")
                _require(allow_tools or event["item"].get("type") != "function_call")
                _require(all(block.get("type") != "refusal"
                             for block in event["item"].get("content", [])), "content_filter")
            if "part" in event:
                _require(event["part"].get("type") != "refusal", "content_filter")
            if "response" in event:
                _require(event["response"].get("model") == model_id, "model_mismatch")
                _require(event["response"].get("status") not in ("failed", "incomplete", "cancelled"))
                _require(not event["response"].get("error")
                         and not event["response"].get("incomplete_details"))
            if kind == "response.completed":
                _responses_complete(event["response"], model_id, allow_tools)
                done = True
        elif protocol == "anthropic_messages":
            kind = event["type"]
            _require(kind != "error")
            _require(not finished or kind == "message_stop")
            if kind == "message_start":
                _require(event["message"].get("model") == model_id, "model_mismatch")
                _require(not started)
                started = True
            else:
                _require(started)
            if kind == "content_block_start":
                block_type = event["content_block"].get("type")
                _require(block_type != "refusal", "content_filter")
                _require(allow_tools or block_type != "tool_use")
                tools |= block_type == "tool_use"
            if kind == "message_delta":
                reason = event["delta"].get("stop_reason")
                _finish_reason(reason)
                _require(reason == "end_turn" or (allow_tools and tools and reason == "tool_use"))
                _require(not finished)
                finished = True
            if kind == "message_stop":
                _require(finished)
                done = True
    _require(done)


def validate_completion(body, *, protocol, model_id, streaming, allow_tools):
    """Fail closed with a fixed error; never include provider text in the error."""
    try:
        _require(protocol in ("deepseek", "chat_completions", "responses", "anthropic_messages"))
        if streaming:
            _validate_stream(body, protocol, model_id, allow_tools)
        else:
            result = json.loads(body)
            if protocol in ("deepseek", "chat_completions"):
                reason, tools = _chat_choice(result, model_id, allow_tools, streaming=False)
                _require(reason == "stop" or (allow_tools and tools and reason == "tool_calls"))
            elif protocol == "responses":
                _responses_complete(result, model_id, allow_tools)
            elif protocol == "anthropic_messages":
                _require(result.get("model") == model_id, "model_mismatch")
                reason = result.get("stop_reason")
                _finish_reason(reason)
                _require(all(item.get("type") != "refusal" for item in result["content"]), "content_filter")
                tools = any(item.get("type") == "tool_use" for item in result["content"])
                _require(allow_tools or not tools)
                _require(reason == "end_turn" or (allow_tools and tools and reason == "tool_use"))
    except _InvalidCompletion as error:
        raise ProcessingError("AI_PROCESSING_FAILED", 502, retryable=False, retry_reason=error.reason) from None
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeDecodeError):
        raise ProcessingError("AI_PROCESSING_FAILED", 502, retryable=False, retry_reason="completion_validation") from None
