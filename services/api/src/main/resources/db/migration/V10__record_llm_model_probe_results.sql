ALTER TABLE knowflow.llm_models
    ADD COLUMN last_probe_at TIMESTAMPTZ NULL,
    ADD COLUMN last_probe_status VARCHAR(16) NULL,
    ADD CONSTRAINT llm_models_probe_result_check CHECK (
        (last_probe_at IS NULL AND last_probe_status IS NULL)
        OR (last_probe_at IS NOT NULL AND last_probe_status IS NOT NULL AND last_probe_status = 'success')
    );
