# Internal answer stream

`POST /internal/v1/answers/stream` accepts the existing `TrustedAnswerRequest`
and is an internal Python-to-Java interface. The response is `text/event-stream`;
each SSE data line contains one draft.9 `AnswerStreamEvent` JSON object:

```text
started -> delta* -> sources -> completed
```

An error or cancellation replaces the terminal success event. Every event has
`contract_version`, the trusted request's `request_id`, and a sequence starting
at 1. `delta` contains answer text only. `sources` contains validated
`has_answer` and source records from the scoped read-only retrieval result;
Java must still recheck current visibility before exposing them. `completed`
does not repeat the answer; concatenate deltas. A refusal emits the canonical
refusal text and an empty sources list after validating the provider result.

The provider request uses OpenAI-compatible `stream: true` and consumes only
SSE `choices[0].delta.content`. A bounded incremental JSON-string parser handles
escaped content and emits provisional deltas. It validates the complete final
JSON object, source IDs, citations, and snapshot membership before emitting
`sources`. Truncated or malformed provider streams have one `error` terminal.

The request has a 28-second end-to-end deadline, a 1 MiB provider body cap, a
64 Ki-codepoint JSON cap, and a 16,000-codepoint answer cap. Cancellation during
retrieval or generation propagates to that operation and closes the HTTP client
stream. An HTTP disconnect closes the event iterator and cancels its retrieval
or provider work. If the disconnect wins, the terminal event is not deliverable.
The route checks required model credentials before constructing the service;
missing credentials cause no provider network call.
