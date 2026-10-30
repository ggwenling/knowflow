ALTER TABLE knowflow.indexing_tasks
    DROP CONSTRAINT indexing_tasks_failure_code_check;
ALTER TABLE knowflow.indexing_tasks
    ADD CONSTRAINT indexing_tasks_failure_code_check
        CHECK (failure_code IS NULL OR failure_code IN (
            'UNSUPPORTED_CONTENT', 'EMPTY_CONTENT', 'RESOURCE_LIMIT', 'MODEL_TIMEOUT',
            'MODEL_FAILURE', 'INDEX_WRITE_FAILED', 'EXECUTION_CANCELLED', 'WORKER_LOST'
        ));

ALTER TABLE knowflow.index_versions
    DROP CONSTRAINT index_versions_failure_code_check;
ALTER TABLE knowflow.index_versions
    ADD CONSTRAINT index_versions_failure_code_check
        CHECK (failure_code IS NULL OR failure_code IN (
            'UNSUPPORTED_CONTENT', 'EMPTY_CONTENT', 'RESOURCE_LIMIT', 'MODEL_TIMEOUT',
            'MODEL_FAILURE', 'INDEX_WRITE_FAILED', 'EXECUTION_CANCELLED', 'WORKER_LOST'
        ));

ALTER TABLE knowflow.indexing_tasks
    ADD COLUMN accepted_lease_id UUID,
    ADD COLUMN accepted_fencing BIGINT,
    ADD COLUMN accepted_execution_token_hash VARCHAR(64),
    ADD COLUMN accepted_completion_sha256 VARCHAR(64),
    ADD CONSTRAINT indexing_tasks_accepted_fencing_check
        CHECK (accepted_fencing IS NULL OR accepted_fencing > 0),
    ADD CONSTRAINT indexing_tasks_accepted_hash_check
        CHECK (accepted_execution_token_hash IS NULL
            OR accepted_execution_token_hash ~ '^[a-f0-9]{64}$'),
    ADD CONSTRAINT indexing_tasks_accepted_completion_hash_check
        CHECK (accepted_completion_sha256 IS NULL
            OR accepted_completion_sha256 ~ '^[a-f0-9]{64}$'),
    ADD CONSTRAINT indexing_tasks_accepted_completion_state_check
        CHECK (
            (accepted_lease_id IS NULL
                AND accepted_fencing IS NULL
                AND accepted_execution_token_hash IS NULL
                AND accepted_completion_sha256 IS NULL)
            OR
            (accepted_lease_id IS NOT NULL
                AND accepted_fencing IS NOT NULL
                AND accepted_execution_token_hash IS NOT NULL
                AND accepted_completion_sha256 IS NOT NULL)
        );

CREATE TABLE knowflow.index_batch_receipts (
    task_id UUID NOT NULL,
    index_version_id UUID NOT NULL,
    lease_id UUID NOT NULL,
    fencing BIGINT NOT NULL,
    batch_id UUID NOT NULL,
    batch_sequence INTEGER NOT NULL,
    batch_sha256 VARCHAR(64) NOT NULL,
    chunk_count SMALLINT NOT NULL,
    accepted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT index_batch_receipts_pk PRIMARY KEY (task_id, lease_id, fencing, batch_id),
    CONSTRAINT index_batch_receipts_task_fk
        FOREIGN KEY (task_id) REFERENCES knowflow.indexing_tasks (id) ON DELETE RESTRICT,
    CONSTRAINT index_batch_receipts_index_fk
        FOREIGN KEY (index_version_id) REFERENCES knowflow.index_versions (id) ON DELETE RESTRICT,
    CONSTRAINT index_batch_receipts_fencing_positive CHECK (fencing > 0),
    CONSTRAINT index_batch_receipts_sequence_positive CHECK (batch_sequence > 0),
    CONSTRAINT index_batch_receipts_hash_check CHECK (batch_sha256 ~ '^[a-f0-9]{64}$'),
    CONSTRAINT index_batch_receipts_chunk_count_check CHECK (chunk_count BETWEEN 1 AND 32),
    CONSTRAINT index_batch_receipts_index_sequence_uq UNIQUE (index_version_id, batch_sequence),
    CONSTRAINT index_batch_receipts_task_lease_sequence_uq
        UNIQUE (task_id, lease_id, fencing, batch_sequence)
);

CREATE INDEX index_batch_receipts_index_version_idx
    ON knowflow.index_batch_receipts (index_version_id, batch_sequence);

CREATE TABLE knowflow.storage_cleanup_queue (
    id UUID PRIMARY KEY,
    object_key TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_error_code VARCHAR(32),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT storage_cleanup_queue_object_key_not_blank CHECK (object_key <> ''),
    CONSTRAINT storage_cleanup_queue_attempts_nonnegative CHECK (attempt_count >= 0),
    CONSTRAINT storage_cleanup_queue_object_key_uq UNIQUE (object_key),
    CONSTRAINT storage_cleanup_queue_failure_code_check CHECK (
        last_error_code IS NULL OR last_error_code IN ('STORAGE_UNAVAILABLE', 'OBJECT_NOT_FOUND')
    )
);

CREATE INDEX storage_cleanup_queue_available_idx
    ON knowflow.storage_cleanup_queue (available_at, created_at);

GRANT SELECT, INSERT, UPDATE, DELETE ON
    knowflow.index_batch_receipts,
    knowflow.storage_cleanup_queue
TO knowflow_app;
