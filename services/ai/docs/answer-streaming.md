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
escaped content while buffering the answer. After the provider finishes, the
service validates the complete JSON object, source IDs, citations, snapshot
membership, and claim grounding. It then emits the validated answer as `delta`
before `sources`; an answer rejected by citation validation emits only the
canonical refusal text. Truncated or malformed provider streams have one
`error` terminal. The answer therefore appears after generation and citation
checking finish, rather than during generation.

## Bounded citation re-ask

When the model claims an answer but every claim fails citation validation, the
service spends at most one extra non-streaming provider call on the **same**
evidence before refusing (`KNOWFLOW_ANSWER_REPAIR`, default on; set
`off`/`0`/`false` to disable). The re-ask receives the previous answer text
(truncated to 4,000 code points), adds no evidence and no sources, and its
result passes through the identical JSON, ID, scope, and grounding checks. A
failed, malformed, budget-stopped, or still-ungrounded re-ask leaves the
canonical refusal in place; it never becomes an `error` terminal.

The re-ask is skipped when the model itself declines (`has_answer=false`), when
retrieval returned no evidence, and when fewer than 6 seconds remain of the
28-second request deadline. Both the streaming and the non-streaming routes use
the same finalize path, so a streamed request can never surface an answer the
non-streaming route would refuse.

Within one generation the verifier also performs deterministic claim-level
repair at no model cost: an uncited claim, or a claim whose stacked markers all
failed, is rebound to a source the model already declared **only** when that
source contains the complete claim verbatim. No coverage threshold is relaxed
and no undeclared source is introduced.

## Citation diagnostics

Each request logs one `ai_stage ... stage=citation_verification` line with
`decision`, `reason` (`grounded`, `empty_after_prune`, `no_cited_claims`,
`model_declined`), `claims`, `kept_claims`, `uncited_claims`, `dropped_claims`,
`repaired_claims`, `pruned_markers`, `repair_attempt`, and `repair_outcome`.
These are counts and enum codes only; answers, claims, quotes, and questions are
not logged.


The request has a 28-second end-to-end deadline, a 1 MiB provider body cap, a
64 Ki-codepoint JSON cap, and a 16,000-codepoint answer cap. Cancellation during
retrieval or generation propagates to that operation and closes the HTTP client
stream. An HTTP disconnect closes the event iterator and cancels its retrieval
or provider work. If the disconnect wins, the terminal event is not deliverable.
The route checks required model credentials before constructing the service;
missing credentials cause no provider network call.

Java and Python answer routes share a per-process in-flight limit. Set
`KNOWFLOW_QUESTION_MAX_CONCURRENT` from 1 to 32 on both services; the default is
4. Over-capacity requests fail immediately with the existing retryable
`AI_PROCESSING_FAILED` error and do not create question history. An admitted
stream holds its slot until its body and provider iterator are closed.

Stage logs use the trusted `request_id` and record durations, counts, outcomes,
and provider token usage only when the provider returns a valid usage object.
Missing usage is logged as `unknown`; prompts, answers, source text, and vectors
are not logged. A provider's terminal usage-only SSE chunk is accepted only
after a valid `stop` finish marker.
