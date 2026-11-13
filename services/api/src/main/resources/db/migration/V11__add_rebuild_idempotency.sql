CREATE TABLE knowflow.document_rebuild_requests (
    owner_user_id UUID NOT NULL REFERENCES knowflow.users (id),
    request_key UUID NOT NULL,
    document_id UUID NOT NULL REFERENCES knowflow.documents (id),
    task_id UUID NOT NULL REFERENCES knowflow.indexing_tasks (id),
    PRIMARY KEY (owner_user_id, request_key)
);

GRANT SELECT, INSERT ON knowflow.document_rebuild_requests TO knowflow_app;
