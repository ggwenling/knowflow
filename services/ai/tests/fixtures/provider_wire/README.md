# Provider wire regression recordings

These are **synthetic recordings**, assembled from the installed SDK wire shapes,
not live captures. No provider, credentials, user data, or public network was used.
The checked-in bytes are the test inputs; tests must not regenerate them. Each
protocol has 14 recordings (56 total), covering all eight fixture IDs below.

Versions verified against `services/ai/requirements.lock`, `uv.lock`, and the
existing Python 3.12.16 venv:

| Package | Version |
| --- | --- |
| langchain | 1.4.10 |
| langchain-openai | 1.7.4 |
| langchain-anthropic | 1.7.10 |
| langchain-deepseek | 1.1.1 |
| openai | 3.49.0 |
| anthropic | 2.8.0 |
| httpx | 0.28.1 |
| httpx2 | 2.16.0 |

| Protocol | Expected wire model | POST endpoint |
| --- | --- | --- |
| deepseek (built-in) | deepseek-flash | /chat/completions |
| chat_completions (custom) | test-model | /prefix/chat/completions |
| anthropic_messages (custom) | test-model | /prefix/v1/messages |
| responses (custom) | test-model | /prefix/responses |

The custom URL is `https://provider.example.com/prefix`, intercepted by the
appropriate library's MockTransport. The built-in URL uses its configured path,
also intercepted. ASGI routes use ASGITransport. The new fixture suite forbids
unmocked HTTP transports and external socket connections, including tracing.

All wire HTTP statuses are 200, intentionally exercising the completion boundary
rather than HTTP status mapping. SSE uses `text/event-stream`; JSON uses
`application/json`. Garbage bodies deliberately violate the declared format and
include invalid UTF-8. Every abnormal case contains its own unique `WIRE_PRIVATE_`
sentinel, which must never appear in exceptions, HTTP/SSE bodies, or captured logs.

| Fixture ID | Expected category | allow_tools | Shapes |
| --- | --- | --- | --- |
| normal_stream | success (answer JSON and usage) | false | SSE |
| normal_non_stream | success (answer JSON and usage) | false | JSON |
| tool_call | tool_call (SDK name, call id, parsed args) | true | SSE, JSON |
| missing_terminator | invalid_completion | false | SSE, JSON |
| wrong_model_id | invalid_completion | false | SSE, JSON |
| length_truncation | invalid_completion | false | SSE, JSON |
| content_filter | invalid_completion | false | SSE, JSON |
| garbage_body | invalid_completion | false | invalid bytes for both modes |

Invalid completions map to fixed `AI_PROCESSING_FAILED`, status 502, non-retryable.
A non-stream missing terminator is a missing Chat finish reason, missing Anthropic
stop reason, or Responses status still `in_progress`; JSON has no SSE terminator.
Chat streams separate content, finish, usage, and `[DONE]`. Anthropic uses
`message_stop`; its final `message_delta` carries cumulative input/output usage
as consumed by the pinned SDK. Responses uses `response.completed`. The filter fixtures use
explicit Chat `content_filter`, Anthropic `refusal` stop reason, and Responses
refusal events/output; ordinary refusal-like natural-language text is not treated
as a protocol error. Responses truncation is `incomplete/max_output_tokens`.

`manifest.json` is the machine-readable case schema: stable id, fixture_id,
protocol, path, endpoint, expected model, streaming, allow_tools, wire HTTP status
and content type, expected category/status/result/usage, and optional sentinel.
The manifest's expected result is synthetic contract-compatible answer JSON or a
single `search_knowledge_base` call. Both tool shapes are inspected using SDK
`bind_tools` with a strict synthetic tool schema (required by OpenAI's non-stream
parse endpoint when JSON response format is active). Streaming tool recordings
are then replayed as tool → one search → normal final answer through the real
agent for all four protocols. Responses uses distinct response IDs for these
two turns. Tool-only output is never used as a successful answer JSON.

All 56 cases also pass through the actual SDK invocation boundary, with streaming
explicitly disabled for JSON cases. HTTP/SSE tests use the production streaming
SDK configuration, a synthetic retriever, and contract-compatible evidence. They
cover each abnormal streaming recording on both public response shapes: fixed
HTTP 502, or a single SSE error terminal with no answer delta. The test-only
budget spy checks that each built-in POST reserves once; durable budget behavior
remains covered by the existing tests.

When changing SDK versions, replay these fixtures explicitly and review wire
changes; do not silently rewrite fixtures to make a parser upgrade pass.
