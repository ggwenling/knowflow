ALTER TABLE knowflow.users
    ADD COLUMN password_hash VARCHAR(255),
    ADD CONSTRAINT users_password_hash_length_check
        CHECK (password_hash IS NULL OR char_length(password_hash) >= 64);

CREATE TABLE knowflow.user_sessions (
    token_sha256 VARCHAR(64) PRIMARY KEY,
    user_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    CONSTRAINT user_sessions_token_hash_check CHECK (token_sha256 ~ '^[a-f0-9]{64}$'),
    CONSTRAINT user_sessions_expiry_check CHECK (expires_at > created_at),
    CONSTRAINT user_sessions_revocation_check
        CHECK (revoked_at IS NULL OR revoked_at >= created_at),
    CONSTRAINT user_sessions_user_fk
        FOREIGN KEY (user_id) REFERENCES knowflow.users (id) ON DELETE RESTRICT
);

CREATE INDEX user_sessions_user_active_expiry_idx
    ON knowflow.user_sessions (user_id, expires_at)
    WHERE revoked_at IS NULL;
