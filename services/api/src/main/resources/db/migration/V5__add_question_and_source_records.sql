CREATE TABLE knowflow.questions (
    id UUID PRIMARY KEY,
    owner_user_id UUID NOT NULL,
    knowledge_base_id UUID NOT NULL,
    request_id VARCHAR(128) NOT NULL,
    snapshot_id UUID NOT NULL,
    question_text TEXT NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'PROCESSING',
    answer_text TEXT,
    has_answer BOOLEAN,
    failure_code VARCHAR(32),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMPTZ,
    CONSTRAINT questions_status_check
        CHECK (status IN ('PROCESSING', 'SUCCEEDED', 'FAILED', 'CANCELLED')),
    CONSTRAINT questions_request_id_check
        CHECK (request_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'),
    CONSTRAINT questions_text_not_blank CHECK (question_text <> ''),
    CONSTRAINT questions_answer_length_check
        CHECK (answer_text IS NULL OR char_length(answer_text) <= 16000),
    CONSTRAINT questions_failure_code_check
        CHECK (failure_code IS NULL OR failure_code IN (
            'AI_PROCESSING_FAILED', 'PROCESSING_TIMEOUT', 'DOCUMENT_UNAVAILABLE'
        )),
    CONSTRAINT questions_finished_state_check CHECK (
        (status IN ('SUCCEEDED', 'FAILED', 'CANCELLED')) = (finished_at IS NOT NULL)
    ),
    CONSTRAINT questions_result_state_check CHECK (
        (status = 'SUCCEEDED' AND answer_text IS NOT NULL AND has_answer IS NOT NULL
            AND failure_code IS NULL)
        OR (status = 'FAILED' AND answer_text IS NULL AND has_answer IS NULL
            AND failure_code IS NOT NULL)
        OR (status IN ('PROCESSING', 'CANCELLED') AND answer_text IS NULL
            AND has_answer IS NULL AND failure_code IS NULL)
    ),
    CONSTRAINT questions_id_owner_kb_uq UNIQUE (id, owner_user_id, knowledge_base_id),
    CONSTRAINT questions_owner_kb_fk
        FOREIGN KEY (knowledge_base_id, owner_user_id)
        REFERENCES knowflow.knowledge_bases (id, owner_user_id) ON DELETE RESTRICT
);

CREATE INDEX questions_owner_created_idx ON knowflow.questions (owner_user_id, created_at DESC);

CREATE TABLE knowflow.question_scope_indexes (
    question_id UUID NOT NULL,
    owner_user_id UUID NOT NULL,
    knowledge_base_id UUID NOT NULL,
    document_id UUID NOT NULL,
    content_version_id UUID NOT NULL,
    index_version_id UUID NOT NULL,
    CONSTRAINT question_scope_indexes_pk PRIMARY KEY (question_id, index_version_id),
    CONSTRAINT question_scope_question_fk
        FOREIGN KEY (question_id, owner_user_id, knowledge_base_id)
        REFERENCES knowflow.questions (id, owner_user_id, knowledge_base_id) ON DELETE RESTRICT,
    CONSTRAINT question_scope_document_fk
        FOREIGN KEY (document_id, knowledge_base_id, owner_user_id)
        REFERENCES knowflow.documents (id, knowledge_base_id, owner_user_id) ON DELETE RESTRICT,
    CONSTRAINT question_scope_content_fk
        FOREIGN KEY (content_version_id, document_id)
        REFERENCES knowflow.content_versions (id, document_id) ON DELETE RESTRICT,
    CONSTRAINT question_scope_index_fk
        FOREIGN KEY (index_version_id, document_id, content_version_id)
        REFERENCES knowflow.index_versions (id, document_id, content_version_id) ON DELETE RESTRICT
);

CREATE TABLE knowflow.question_sources (
    source_id UUID PRIMARY KEY,
    question_id UUID NOT NULL,
    owner_user_id UUID NOT NULL,
    knowledge_base_id UUID NOT NULL,
    document_id UUID NOT NULL,
    content_version_id UUID NOT NULL,
    index_version_id UUID NOT NULL,
    chunk_id UUID NOT NULL,
    locator_kind VARCHAR(16) NOT NULL,
    source_page INTEGER,
    source_start INTEGER,
    source_end INTEGER,
    quote TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT question_sources_quote_not_blank CHECK (quote <> ''),
    CONSTRAINT question_sources_locator_kind_check
        CHECK (locator_kind IN ('pdf_page', 'text_range')),
    CONSTRAINT question_sources_locator_shape_check CHECK (
        (locator_kind = 'pdf_page'
            AND source_page IS NOT NULL AND source_page > 0
            AND source_start IS NULL AND source_end IS NULL)
        OR (locator_kind = 'text_range'
            AND source_page IS NULL AND source_start IS NOT NULL AND source_start >= 0
            AND source_end IS NOT NULL AND source_end > source_start)
    ),
    CONSTRAINT question_sources_question_fk
        FOREIGN KEY (question_id, owner_user_id, knowledge_base_id)
        REFERENCES knowflow.questions (id, owner_user_id, knowledge_base_id) ON DELETE RESTRICT,
    CONSTRAINT question_sources_document_fk
        FOREIGN KEY (document_id, knowledge_base_id, owner_user_id)
        REFERENCES knowflow.documents (id, knowledge_base_id, owner_user_id) ON DELETE RESTRICT,
    CONSTRAINT question_sources_content_fk
        FOREIGN KEY (content_version_id, document_id)
        REFERENCES knowflow.content_versions (id, document_id) ON DELETE RESTRICT,
    CONSTRAINT question_sources_index_fk
        FOREIGN KEY (index_version_id, document_id, content_version_id)
        REFERENCES knowflow.index_versions (id, document_id, content_version_id) ON DELETE RESTRICT
);

CREATE INDEX question_sources_question_idx ON knowflow.question_sources (question_id, created_at);
CREATE INDEX question_sources_owner_idx
    ON knowflow.question_sources (owner_user_id, source_id);

GRANT SELECT, INSERT, UPDATE, DELETE ON
    knowflow.questions,
    knowflow.question_scope_indexes,
    knowflow.question_sources
TO knowflow_app;
