CREATE TABLE knowflow.users (
    id UUID PRIMARY KEY,
    email VARCHAR(320) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT users_email_not_blank CHECK (email <> '' AND email = btrim(email))
);

CREATE UNIQUE INDEX users_email_lower_uq ON knowflow.users (LOWER(email));

CREATE TABLE knowflow.knowledge_bases (
    id UUID PRIMARY KEY,
    owner_user_id UUID NOT NULL,
    name VARCHAR(200) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ,
    CONSTRAINT knowledge_bases_name_not_blank CHECK (name <> '' AND name = btrim(name)),
    CONSTRAINT knowledge_bases_status_check CHECK (status IN ('ACTIVE', 'DELETED')),
    CONSTRAINT knowledge_bases_deletion_check
        CHECK ((status = 'DELETED') = (deleted_at IS NOT NULL)),
    CONSTRAINT knowledge_bases_id_owner_uq UNIQUE (id, owner_user_id),
    CONSTRAINT knowledge_bases_owner_fk
        FOREIGN KEY (owner_user_id) REFERENCES knowflow.users (id) ON DELETE RESTRICT
);

CREATE TABLE knowflow.documents (
    id UUID PRIMARY KEY,
    knowledge_base_id UUID NOT NULL,
    owner_user_id UUID NOT NULL,
    original_name VARCHAR(512) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
    current_content_version_id UUID,
    active_index_version_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ,
    CONSTRAINT documents_name_not_blank CHECK (original_name <> ''),
    CONSTRAINT documents_status_check CHECK (status IN ('ACTIVE', 'DELETED')),
    CONSTRAINT documents_deletion_check CHECK ((status = 'DELETED') = (deleted_at IS NOT NULL)),
    CONSTRAINT documents_id_kb_owner_uq UNIQUE (id, knowledge_base_id, owner_user_id),
    CONSTRAINT documents_knowledge_base_fk
        FOREIGN KEY (knowledge_base_id, owner_user_id)
        REFERENCES knowflow.knowledge_bases (id, owner_user_id) ON DELETE RESTRICT
);

CREATE INDEX documents_kb_status_created_idx
    ON knowflow.documents (knowledge_base_id, status, created_at DESC);

CREATE TABLE knowflow.content_versions (
    id UUID PRIMARY KEY,
    document_id UUID NOT NULL,
    version_no INTEGER NOT NULL,
    source_sha256 VARCHAR(64) NOT NULL,
    source_format VARCHAR(8) NOT NULL,
    object_key TEXT NOT NULL,
    byte_size BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT content_versions_version_positive CHECK (version_no > 0),
    CONSTRAINT content_versions_sha256_check CHECK (source_sha256 ~ '^[a-f0-9]{64}$'),
    CONSTRAINT content_versions_format_check CHECK (source_format IN ('txt', 'md', 'pdf')),
    CONSTRAINT content_versions_byte_size_positive CHECK (byte_size > 0),
    CONSTRAINT content_versions_object_key_not_blank CHECK (object_key <> ''),
    CONSTRAINT content_versions_document_version_uq UNIQUE (document_id, version_no),
    CONSTRAINT content_versions_object_key_uq UNIQUE (object_key),
    CONSTRAINT content_versions_id_document_uq UNIQUE (id, document_id),
    CONSTRAINT content_versions_document_fk
        FOREIGN KEY (document_id) REFERENCES knowflow.documents (id) ON DELETE RESTRICT
);

ALTER TABLE knowflow.documents
    ADD CONSTRAINT documents_current_content_version_fk
        FOREIGN KEY (current_content_version_id, id)
        REFERENCES knowflow.content_versions (id, document_id)
        DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE knowflow.index_versions (
    id UUID PRIMARY KEY,
    document_id UUID NOT NULL,
    content_version_id UUID NOT NULL,
    pipeline_profile_id VARCHAR(128) NOT NULL,
    generation INTEGER NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'BUILDING',
    embedding_model_profile_id VARCHAR(128) NOT NULL,
    embedding_dimensions SMALLINT NOT NULL DEFAULT 1024,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    embedding_count INTEGER NOT NULL DEFAULT 0,
    manifest_sha256 VARCHAR(64),
    failure_code VARCHAR(32),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ready_at TIMESTAMPTZ,
    CONSTRAINT index_versions_generation_positive CHECK (generation > 0),
    CONSTRAINT index_versions_status_check
        CHECK (status IN ('BUILDING', 'READY', 'FAILED', 'RETIRED')),
    CONSTRAINT index_versions_dimensions_check CHECK (embedding_dimensions = 1024),
    CONSTRAINT index_versions_chunk_count_nonnegative CHECK (chunk_count >= 0),
    CONSTRAINT index_versions_embedding_count_nonnegative CHECK (embedding_count >= 0),
    CONSTRAINT index_versions_profile_ids_not_blank
        CHECK (pipeline_profile_id <> '' AND embedding_model_profile_id <> ''),
    CONSTRAINT index_versions_manifest_check CHECK (
        manifest_sha256 IS NULL OR manifest_sha256 ~ '^[a-f0-9]{64}$'
    ),
    CONSTRAINT index_versions_failure_code_check CHECK (
        failure_code IS NULL OR failure_code IN (
            'UNSUPPORTED_CONTENT', 'EMPTY_CONTENT', 'RESOURCE_LIMIT', 'MODEL_TIMEOUT',
            'MODEL_FAILURE', 'INDEX_WRITE_FAILED', 'EXECUTION_CANCELLED'
        )
    ),
    CONSTRAINT index_versions_failed_state_check
        CHECK ((status = 'FAILED') = (failure_code IS NOT NULL)),
    CONSTRAINT index_versions_ready_state_check CHECK (
        (status IN ('READY', 'RETIRED') AND ready_at IS NOT NULL AND manifest_sha256 IS NOT NULL)
        OR (status IN ('BUILDING', 'FAILED') AND ready_at IS NULL)
    ),
    CONSTRAINT index_versions_document_version_pipeline_generation_uq
        UNIQUE (document_id, content_version_id, pipeline_profile_id, generation),
    CONSTRAINT index_versions_id_document_uq UNIQUE (id, document_id),
    CONSTRAINT index_versions_id_document_content_uq
        UNIQUE (id, document_id, content_version_id),
    CONSTRAINT index_versions_embedding_profile_uq
        UNIQUE (id, document_id, content_version_id, embedding_model_profile_id),
    CONSTRAINT index_versions_content_version_fk
        FOREIGN KEY (content_version_id, document_id)
        REFERENCES knowflow.content_versions (id, document_id) ON DELETE RESTRICT
);

ALTER TABLE knowflow.documents
    ADD CONSTRAINT documents_active_index_version_fk
        FOREIGN KEY (active_index_version_id, id)
        REFERENCES knowflow.index_versions (id, document_id)
        DEFERRABLE INITIALLY DEFERRED;

CREATE INDEX index_versions_document_state_idx
    ON knowflow.index_versions (document_id, status, created_at DESC);

CREATE TABLE knowflow.indexing_tasks (
    id UUID PRIMARY KEY,
    owner_user_id UUID NOT NULL,
    knowledge_base_id UUID NOT NULL,
    document_id UUID NOT NULL,
    content_version_id UUID NOT NULL,
    index_version_id UUID NOT NULL,
    task_type VARCHAR(16) NOT NULL DEFAULT 'INDEX',
    status VARCHAR(16) NOT NULL DEFAULT 'QUEUED',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    fencing BIGINT NOT NULL DEFAULT 0,
    lease_id UUID,
    lease_expires_at TIMESTAMPTZ,
    execution_token_hash VARCHAR(64),
    last_request_id VARCHAR(128),
    failure_code VARCHAR(32),
    available_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMPTZ,
    CONSTRAINT indexing_tasks_type_check CHECK (task_type = 'INDEX'),
    CONSTRAINT indexing_tasks_status_check
        CHECK (status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')),
    CONSTRAINT indexing_tasks_attempt_count_nonnegative CHECK (attempt_count >= 0),
    CONSTRAINT indexing_tasks_fencing_nonnegative CHECK (fencing >= 0),
    CONSTRAINT indexing_tasks_lease_state_check CHECK (
        (status = 'RUNNING'
            AND lease_id IS NOT NULL
            AND lease_expires_at IS NOT NULL
            AND execution_token_hash IS NOT NULL)
        OR (status <> 'RUNNING'
            AND lease_id IS NULL
            AND lease_expires_at IS NULL
            AND execution_token_hash IS NULL)
    ),
    CONSTRAINT indexing_tasks_token_hash_check CHECK (
        execution_token_hash IS NULL OR execution_token_hash ~ '^[a-f0-9]{64}$'
    ),
    CONSTRAINT indexing_tasks_request_id_check CHECK (
        last_request_id IS NULL OR last_request_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'
    ),
    CONSTRAINT indexing_tasks_failure_code_check CHECK (
        failure_code IS NULL OR failure_code IN (
            'UNSUPPORTED_CONTENT', 'EMPTY_CONTENT', 'RESOURCE_LIMIT', 'MODEL_TIMEOUT',
            'MODEL_FAILURE', 'INDEX_WRITE_FAILED', 'EXECUTION_CANCELLED'
        )
    ),
    CONSTRAINT indexing_tasks_failure_state_check
        CHECK ((status = 'FAILED') = (failure_code IS NOT NULL)),
    CONSTRAINT indexing_tasks_finished_state_check CHECK (
        (status IN ('SUCCEEDED', 'FAILED', 'CANCELLED')) = (finished_at IS NOT NULL)
    ),
    CONSTRAINT indexing_tasks_document_scope_fk
        FOREIGN KEY (document_id, knowledge_base_id, owner_user_id)
        REFERENCES knowflow.documents (id, knowledge_base_id, owner_user_id) ON DELETE RESTRICT,
    CONSTRAINT indexing_tasks_content_version_fk
        FOREIGN KEY (content_version_id, document_id)
        REFERENCES knowflow.content_versions (id, document_id) ON DELETE RESTRICT,
    CONSTRAINT indexing_tasks_index_version_fk
        FOREIGN KEY (index_version_id, document_id, content_version_id)
        REFERENCES knowflow.index_versions (id, document_id, content_version_id) ON DELETE RESTRICT
);

CREATE INDEX indexing_tasks_status_available_idx
    ON knowflow.indexing_tasks (status, available_at, created_at);
CREATE INDEX indexing_tasks_document_created_idx
    ON knowflow.indexing_tasks (document_id, created_at DESC);

CREATE TABLE knowflow.chunks (
    id UUID PRIMARY KEY,
    index_version_id UUID NOT NULL,
    document_id UUID NOT NULL,
    content_version_id UUID NOT NULL,
    sequence_no INTEGER NOT NULL,
    text_content TEXT NOT NULL,
    text_sha256 VARCHAR(64) NOT NULL,
    locator_kind VARCHAR(16) NOT NULL,
    source_page INTEGER,
    source_start INTEGER,
    source_end INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chunks_sequence_positive CHECK (sequence_no > 0),
    CONSTRAINT chunks_text_nonempty CHECK (text_content <> ''),
    CONSTRAINT chunks_sha256_check CHECK (text_sha256 ~ '^[a-f0-9]{64}$'),
    CONSTRAINT chunks_locator_kind_check CHECK (locator_kind IN ('pdf_page', 'text_range')),
    CONSTRAINT chunks_locator_shape_check CHECK (
        (locator_kind = 'pdf_page'
            AND source_page IS NOT NULL AND source_page > 0
            AND source_start IS NULL AND source_end IS NULL)
        OR (locator_kind = 'text_range'
            AND source_page IS NULL
            AND source_start IS NOT NULL AND source_start >= 0
            AND source_end IS NOT NULL AND source_end > source_start)
    ),
    CONSTRAINT chunks_index_sequence_uq UNIQUE (index_version_id, sequence_no),
    CONSTRAINT chunks_id_index_document_content_uq
        UNIQUE (id, index_version_id, document_id, content_version_id),
    CONSTRAINT chunks_index_scope_fk
        FOREIGN KEY (index_version_id, document_id, content_version_id)
        REFERENCES knowflow.index_versions (id, document_id, content_version_id) ON DELETE RESTRICT
);

CREATE TABLE knowflow.chunk_embeddings (
    chunk_id UUID PRIMARY KEY,
    index_version_id UUID NOT NULL,
    document_id UUID NOT NULL,
    content_version_id UUID NOT NULL,
    embedding_model_profile_id VARCHAR(128) NOT NULL,
    embedding public.vector(1024) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chunk_embeddings_profile_not_blank CHECK (embedding_model_profile_id <> ''),
    CONSTRAINT chunk_embeddings_chunk_scope_fk
        FOREIGN KEY (chunk_id, index_version_id, document_id, content_version_id)
        REFERENCES knowflow.chunks (id, index_version_id, document_id, content_version_id)
        ON DELETE RESTRICT,
    CONSTRAINT chunk_embeddings_index_profile_fk
        FOREIGN KEY (index_version_id, document_id, content_version_id, embedding_model_profile_id)
        REFERENCES knowflow.index_versions
            (id, document_id, content_version_id, embedding_model_profile_id)
        ON DELETE RESTRICT
);

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA knowflow TO knowflow_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA knowflow TO knowflow_app;
GRANT SELECT ON
    knowflow.knowledge_bases,
    knowflow.documents,
    knowflow.content_versions,
    knowflow.index_versions,
    knowflow.chunks,
    knowflow.chunk_embeddings
TO knowflow_ai;
