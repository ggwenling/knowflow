CREATE TABLE knowflow.index_cleanup_queue (
    id UUID PRIMARY KEY,
    index_version_id UUID NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_error_code VARCHAR(32),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT index_cleanup_queue_index_uq UNIQUE (index_version_id),
    CONSTRAINT index_cleanup_queue_index_fk
        FOREIGN KEY (index_version_id) REFERENCES knowflow.index_versions (id) ON DELETE RESTRICT,
    CONSTRAINT index_cleanup_queue_attempts_nonnegative CHECK (attempt_count >= 0),
    CONSTRAINT index_cleanup_queue_error_check CHECK (
        last_error_code IS NULL OR last_error_code IN ('DATABASE_UNAVAILABLE')
    )
);

CREATE INDEX index_cleanup_queue_available_idx
    ON knowflow.index_cleanup_queue (available_at, created_at);

CREATE TABLE knowflow.execution_cancellation_queue (
    id UUID PRIMARY KEY,
    task_id UUID NOT NULL,
    lease_id UUID NOT NULL,
    fencing BIGINT NOT NULL,
    request_id VARCHAR(128) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_error_code VARCHAR(32),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT execution_cancellation_task_lease_uq UNIQUE (task_id, lease_id, fencing),
    CONSTRAINT execution_cancellation_task_fk
        FOREIGN KEY (task_id) REFERENCES knowflow.indexing_tasks (id) ON DELETE RESTRICT,
    CONSTRAINT execution_cancellation_fencing_positive CHECK (fencing > 0),
    CONSTRAINT execution_cancellation_request_id_check
        CHECK (request_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'),
    CONSTRAINT execution_cancellation_attempts_nonnegative CHECK (attempt_count >= 0),
    CONSTRAINT execution_cancellation_error_check CHECK (
        last_error_code IS NULL OR last_error_code IN ('AI_UNAVAILABLE')
    )
);

CREATE INDEX execution_cancellation_available_idx
    ON knowflow.execution_cancellation_queue (available_at, created_at);

GRANT SELECT, INSERT, UPDATE, DELETE ON
    knowflow.index_cleanup_queue,
    knowflow.execution_cancellation_queue
TO knowflow_app;
