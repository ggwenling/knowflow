ALTER TABLE knowflow.questions
    ADD COLUMN idempotency_key UUID,
    ADD COLUMN deadline_at TIMESTAMPTZ,
    ADD COLUMN embedding_model_profile_id VARCHAR(128),
    ADD COLUMN llm_model_profile_id VARCHAR(128);

UPDATE knowflow.questions
   SET deadline_at = created_at + INTERVAL '30 seconds'
 WHERE deadline_at IS NULL;

ALTER TABLE knowflow.questions
    ALTER COLUMN deadline_at SET NOT NULL;

CREATE UNIQUE INDEX questions_owner_idempotency_key_uq
    ON knowflow.questions (owner_user_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE INDEX questions_processing_deadline_idx
    ON knowflow.questions (deadline_at)
    WHERE status = 'PROCESSING';

ALTER TABLE knowflow.question_sources
    ALTER COLUMN quote DROP NOT NULL,
    ALTER COLUMN locator_kind DROP NOT NULL;

ALTER TABLE knowflow.question_sources
    DROP CONSTRAINT question_sources_quote_not_blank,
    DROP CONSTRAINT question_sources_locator_shape_check;

ALTER TABLE knowflow.question_sources
    ADD CONSTRAINT question_sources_retention_shape_check CHECK (
        (quote IS NULL AND locator_kind IS NULL
            AND source_page IS NULL AND source_start IS NULL AND source_end IS NULL)
        OR (quote IS NOT NULL AND quote <> '' AND (
            (locator_kind = 'pdf_page' AND source_page > 0
                AND source_start IS NULL AND source_end IS NULL)
            OR (locator_kind = 'text_range' AND source_page IS NULL
                AND source_start >= 0 AND source_end > source_start)
        ))
    );
