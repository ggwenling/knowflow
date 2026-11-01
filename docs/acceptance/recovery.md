# KF2-036: worker and question recovery

## Scope

This acceptance record covers local recovery behavior for draft.10 using PostgreSQL/pgvector,
MinIO, Java and Python processes with deterministic synthetic model adapters. It verifies
lease expiry and fencing, the retry limit, persisted question recovery after a Java process
restart, and deletion while the worker is offline.

This is development evidence. It does not verify production uptime, provider behavior, answer
quality, cost, or independent Q/M acceptance.

## Run

From the repository root, with the KnowFlow development environment file available:

    uv run --project services/ai --frozen python services/ai/tools/recovery_e2e.py --env-file services/api/.env --output services/ai/docs/evidence/recovery-e2e-draft10.json

The runner uses an isolated knowflow_recovery_<run-id> database, applies migrations V1–V8
through the Java migration profile, and uses the local Compose PostgreSQL and MinIO services.
It starts those services only when they are not already healthy, and stops only services it
started. It never migrates or drops the existing knowflow database. On successful cleanup,
it drops only the isolated database created by that run; if cleanup fails, it preserves that
database for inspection. Temporary synthetic fixtures are removed.

The runner requires ports 8000 and 8080 to be free. Java uses a 5-second lease, 1-second
heartbeat, 3-attempt limit, 250-millisecond scheduler intervals, and a 3-second question
budget. It makes zero external model calls and checks process logs for configured secrets.

## Scenarios and acceptance

| Scenario | Required result |
|---|---|
| Kill Python after Java acknowledges the first batch; restart Python | Attempt 2 receives a higher fencing value and a separate candidate index. The document reaches READY. Replaying the old batch and a valid old success completion both return LEASE_REJECTED; the old candidate is not published. |
| Kill the worker on three successive attempts while rebuilding an indexed document | Task ends FAILED/WORKER_LOST at attempt 3. All three failed candidate IDs differ. The previous active index stays active and a synthetic answer still cites it. No fourth attempt is dispatched. |
| Kill Java while a synthetic SSE answer is gated in Python; restart Java | Recovery changes the persisted question from PROCESSING to FAILED/PROCESSING_TIMEOUT. No answer text or source rows are stored. |
| Stop Python after a rebuild batch is acknowledged, delete the document, then restart both services | The document remains deleted; document detail, source file, question retrieval, and internal source read are denied. Cleanup queues drain and no content, chunk, or embedding rows are restored. |

## Recorded result

On 2026-11-01, all four scenarios passed on branch local at the then-current draft.10
worktree. The isolated database was migrated through V8 and dropped after cleanup, ports
8000/8080 were released, process logs contained no configured secret, and external model
calls were 0. The machine-readable assertions and source hashes are in
[recovery-e2e-draft10.json](../../services/ai/docs/evidence/recovery-e2e-draft10.json).

## SSE lifecycle record

The Java SSE gateway emits one answer_stream_lifecycle log per stream with request ID,
first_delta_ms, total_ms, terminal status, and safe error code. first_delta_ms measures the
first nonempty delta successfully sent to the client; it is not provider-side token time.
An absent delta is recorded as null. The log excludes question text, answer text, citations,
and credentials.
