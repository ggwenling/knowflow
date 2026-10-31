ALTER TABLE knowflow.documents
    ADD COLUMN pending_content_version_id UUID,
    ADD CONSTRAINT documents_pending_content_version_fk
        FOREIGN KEY (pending_content_version_id, id)
        REFERENCES knowflow.content_versions (id, document_id)
        DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE knowflow.content_versions ADD COLUMN original_name VARCHAR(512);
UPDATE knowflow.content_versions cv SET original_name = d.original_name
    FROM knowflow.documents d WHERE cv.document_id = d.id;
ALTER TABLE knowflow.content_versions ALTER COLUMN original_name SET NOT NULL;
ALTER TABLE knowflow.content_versions ADD COLUMN cleaned_at TIMESTAMPTZ;
ALTER TABLE knowflow.index_versions ADD COLUMN cleaned_at TIMESTAMPTZ;

CREATE INDEX question_scope_processing_index_idx
    ON knowflow.question_scope_indexes (index_version_id, question_id);
