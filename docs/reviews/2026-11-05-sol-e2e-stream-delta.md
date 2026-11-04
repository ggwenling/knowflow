# Sol review: E2E stream delta expectations

Verdict: CHANGES_REQUESTED

Reviewed branch `grok`, commit `cea37f0b638ce0bb20bb92b59d70901bebb5831e` (`fix(web): e2e allow missing delta on failure stream terminals`).

## Findings

- **P1 — The mandatory capture validator still requires a delta on failures.** [contracts/validate_sse_capture.py:43](/workspace/knowflow/contracts/validate_sse_capture.py:43) unconditionally rejects captures without `delta`. [scripts/e2e-web.mjs:67](/workspace/knowflow/scripts/e2e-web.mjs:67) runs this validator after Playwright in the same isolated-full-stack CI step. Consequently, the error/cancelled/timeout captures accepted by the changed helper still fail the gate. Locally removing the delta from each existing failure fixture and resequencing its frames reproduced `SSE_LIFECYCLE_MISMATCH_error`, `SSE_LIFECYCLE_MISMATCH_cancelled`, and `SSE_LIFECYCLE_MISMATCH_timeout`, respectively. Update the validator and its failure fixtures/tests to accept the buffered failure lifecycle while retaining required deltas for successful and refusal captures.

- **P1 — Active-stop still waits for answer text that buffering withholds.** [apps/web/e2e/knowledge-desk.spec.ts:223](/workspace/knowflow/apps/web/e2e/knowledge-desk.spec.ts:223) waits for `合成中断片段` before clicking Stop. The synthetic slow provider yields that fragment during generation, but `answer_events` buffers it until provider completion and citation validation. The assertion therefore either fails because validation refuses the draft, or observes text only once generation has finished, too late to exercise active cancellation. Synchronize on an admitted/in-progress request without waiting for answer text, then stop during generation and preserve the cancellation/history/no-late-success checks. This existing expectation must also be updated for the CI fix to complete.

## Rationale

The changed helper itself matches the documented buffering contract for these synthetic failure scenarios: error, cancellation, and timeout emit no delta or sources; completed responses still require delta, including the refusal call at line 190. The ordinary answer retains its explicit delta assertion, and the capture validator retains delta requirements for text, PDF, and refusal success. The timeout loop maps timeout to `error`, verifies `PROCESSING_TIMEOUT`, and forbids sources consistently; there is no conflicting timeout sources expectation there. However, the two remaining expectations above prevent this commit from completing its stated CI repair. The commit modifies only the E2E spec and introduces no product-code regression risk beyond test expectations. Verification used local source inspection and synthetic capture validation only, with zero real provider calls or spend; the full-stack suite and the cited historical CI runs were not rerun or independently inspected.
