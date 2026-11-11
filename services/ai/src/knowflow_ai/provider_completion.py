"""Validate bounded provider wire responses before an SDK can discard metadata."""
import json

from .adapters import ProcessingError


def _require(condition):
    if not condition:
        raise ValueError


def _events(body):
    # Require a dispatched final event, including its blank-line delimiter.
    text = body.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    _require(not lines[-1])
    data = []
    for line in lines[:-1]:
        if not line:
            if data:
                yield "\n".join(data)
                data.clear()
        elif line.startswith("data:"):
            data.append(line[5:].removeprefix(" "))
        else:
            _require(line.startswith((":", "event:", "id:", "retry:")))
    _require(not data)


def _chat_choice(body, model_id, allow_tools, *, streaming):
    _require(body.get("model") == model_id)
    choices = body.get("choices")
    if streaming and choices == []:
        _require(isinstance(body.get("usage"), dict))
        return None, False
    _require(isinstance(choices, list) and len(choices) == 1)
    choice = choices[0]
    _require(choice.get("index") == 0)
    message = choice["delta" if streaming else "message"]
    _require(isinstance(message, dict))
    reason = choice.get("finish_reason")
    _require(reason in (None, "stop") or (allow_tools and reason == "tool_calls"))
    return reason, bool(message.get("tool_calls"))


def _responses_complete(body, model_id):
    _require(body.get("model") == model_id and body.get("status") == "completed")
    _require(not body.get("error") and not body.get("incomplete_details"))
    _require(all(item.get("status", "completed") == "completed" for item in body["output"]))


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
            _require(kind not in ("error", "response.failed", "response.incomplete"))
            if "response" in event:
                _require(event["response"].get("model") == model_id)
                _require(event["response"].get("status") not in ("failed", "incomplete", "cancelled"))
            if kind == "response.completed":
                _responses_complete(event["response"], model_id)
                done = True
        else:
            kind = event["type"]
            _require(kind != "error")
            _require(not finished or kind == "message_stop")
            if kind == "message_start":
                _require(not started and event["message"].get("model") == model_id)
                started = True
            else:
                _require(started)
            if kind == "content_block_start":
                tools |= event["content_block"].get("type") == "tool_use"
            if kind == "message_delta":
                reason = event["delta"].get("stop_reason")
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
        if streaming:
            _validate_stream(body, protocol, model_id, allow_tools)
        else:
            result = json.loads(body)
            if protocol in ("deepseek", "chat_completions"):
                reason, tools = _chat_choice(result, model_id, allow_tools, streaming=False)
                _require(reason == "stop" or (allow_tools and tools and reason == "tool_calls"))
            elif protocol == "responses":
                _responses_complete(result, model_id)
            else:
                _require(result.get("model") == model_id)
                reason = result.get("stop_reason")
                tools = any(item.get("type") == "tool_use" for item in result["content"])
                _require(reason == "end_turn" or (allow_tools and tools and reason == "tool_use"))
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeDecodeError):
        raise ProcessingError("AI_PROCESSING_FAILED", 502, retryable=False) from None
