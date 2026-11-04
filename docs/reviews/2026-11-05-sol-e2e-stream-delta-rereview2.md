# Sol re-review 2: active-stop admission sync

Verdict: APPROVE

Reviewed HEAD `b48551c3301bf239778c332af8c124939dfd7291` (`fix(web): admit stream before e2e active-stop`), including `git show HEAD -- apps/web/e2e/knowledge-desk.spec.ts`, the original review of `cea37f0`, and the [prior re-review](2026-11-05-sol-e2e-stream-delta-rereview.md). No remaining blocking findings in this change.

The prior P1 is resolved. [knowledge-desk.spec.ts:221](/workspace/knowflow/apps/web/e2e/knowledge-desk.spec.ts:221) registers the stream response wait before submitting the slow question, awaits that response, and then requires `正在检索并生成回答…` before clicking Stop. Earlier stream responses have already been awaited in this sequential test, so the next matching response belongs to the slow submission. The processing card renders only once [Workspace has created its answer object after fetch resolves](/workspace/knowflow/apps/web/src/components/workspace.tsx:303). This removes the reviewed path where Stop was visible while fetch was pending and cancellation left `answer` null. On the normal backend path, the question snapshot is created before the initial `started` event is sent, supporting the admission synchronization.

The change retains cancellation UI and persisted `CANCELLED` history checks, null answer/has-answer and empty sources checks, the 4.5-second no-late-success observation, the single-request assertion, and reopening cancelled history. The slow stream remains excluded from response cloning, preserving the real consumer's reader cancellation path. No buffered draft text is required. The previously resolved capture-validator P1 is unchanged.

Verification:

- `npm run typecheck` in `apps/web`: passed.
- `npm test -- src/components/workspace.test.tsx`: **23 passed**.
- Disposable Vitest check using the real Workspace component with mocked fetch and stream consumer: **1 passed**. Holding fetch pending showed Stop without the processing card; resolving fetch, awaiting the card, and clicking Stop aborted the signal and rendered the cancelled state. The temporary test was removed. This checks the UI race; it does not verify backend persistence.
- `git diff --check`: passed.

Full-stack Playwright was not rerun because Docker is unavailable in this environment. All executed verification used local tooling and mocks. **Zero real provider calls or spend.**
