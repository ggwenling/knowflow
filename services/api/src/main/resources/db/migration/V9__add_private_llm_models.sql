CREATE TABLE knowflow.llm_models (
    id UUID PRIMARY KEY,
    owner_user_id UUID NOT NULL REFERENCES knowflow.users (id),
    base_url VARCHAR(1024) NOT NULL,
    protocol VARCHAR(32) NOT NULL CHECK (protocol IN ('chat_completions', 'responses', 'anthropic_messages')),
    model_id VARCHAR(160) NOT NULL,
    encrypted_key BYTEA NOT NULL,
    supports_tools BOOLEAN NOT NULL,
    revision UUID NOT NULL,
    UNIQUE (owner_user_id, protocol, base_url, model_id)
);

CREATE TABLE knowflow.llm_model_probe_limits (
    owner_user_id UUID PRIMARY KEY REFERENCES knowflow.users (id),
    window_start TIMESTAMPTZ NOT NULL,
    attempts INTEGER NOT NULL
);

ALTER TABLE knowflow.questions ADD COLUMN selected_llm_model_id UUID;

GRANT SELECT, INSERT, UPDATE, DELETE ON knowflow.llm_models, knowflow.llm_model_probe_limits TO knowflow_app;
