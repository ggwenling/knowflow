# Sol re-review: E2E stream delta P1 fixes

Verdict: CHANGES_REQUESTED

Reviewed HEAD `cfdebe43e8dde536ff97e97523963875263b650e` against the prior review of `cea37f0b638ce0bb20bb92b59d70901bebb5831e`. Inspected `git show HEAD~1 --stat` and `git log -3 --oneline`: `a6039db` contains the validator, fixture, and active-stop fixes; the subsequent `cfdebe4` changes only the evaluation closeout document. Read [the prior review](/workspace/knowflow/docs/reviews/2026-11-05-sol-e2e-stream-delta.md).

## Remaining finding

- **P1 — Stop visibility does not establish request admission; active-stop can still fail before exercising streaming cancellation.** [knowledge-desk.spec.ts:224](/workspace/knowflow/apps/web/e2e/knowledge-desk.spec.ts:224) now waits only for the Stop button before clicking it. That button follows `busy`, which [workspace.tsx:298](/workspace/knowflow/apps/web/src/components/workspace.tsx:298) sets before awaiting the stream fetch. The answer object is created only after that fetch resolves at [workspace.tsx:308](/workspace/knowflow/apps/web/src/components/workspace.tsx:308). With a slower response, Stop can therefore abort the fetch while `answer` is still null; the catch handler preserves null, so the cancellation message required by the next E2E assertion never renders. Cancellation can also precede backend admission, leaving no question history to assert. I reproduced the UI failure locally with the real Workspace component and a mocked stream fetch held pending until AbortSignal cancellation: Stop was visible, the stream consumer had not run, clicking Stop aborted the request, and the required cancellation message remained absent after the UI became idle. Synchronize on the matching slow request's admitted/in-progress state before stopping—for example, register and await its stream response, then wait for its processing answer card—while preserving the existing cancellation/history/no-late-success checks and the unmodified reader cancellation path. Waiting for draft text is correctly removed, but the replacement still leaves the prior P1 unresolved.

## Resolved P1

The [capture validator](/workspace/knowflow/contracts/validate_sse_capture.py:43) now accepts exactly `started → error|cancelled` for these buffered failure scenarios, including timeout mapped to `error`. Success and refusal still require delta, sources, and completed in order. Schema, request identity, sequence, single terminal, timeout code, and refusal checks remain enforced. The [updated fixtures and tests](/workspace/knowflow/services/ai/tests/test_sse_capture.py:16) use two-frame failures and retain a missing-delta rejection on successful text captures. This addresses the first P1.

## Verification

- `services/ai/.venv/bin/python -m pytest services/ai/tests/test_sse_capture.py -q`: **12 passed**.
- Additional local validator checks: the six-scenario buffered baseline passed; removing delta from each of text/PDF/refusal and inserting delta or sources into each failure scenario produced the expected lifecycle rejection (**9 mutation checks passed**).
- Disposable Vitest reproduction using the existing Workspace test harness: **1 passed**, confirming the early-stop race described above. The temporary test was removed; no product or test source changes are included in this review.
- `git diff --check`: passed before adding this report. Full-stack Playwright was not rerun; Docker is unavailable in this environment.

All verification was local with synthetic data and mocks. **Zero real provider calls or spend.**
