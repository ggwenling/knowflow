package com.knowflow.api.document;

import java.util.List;
import java.util.UUID;

import com.knowflow.api.error.ApiFailure;
import com.knowflow.api.security.AuthenticatedUser;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
@Profile("database")
public class DeletionCoordinator {
    private final JdbcTemplate jdbc;
    private final TransactionTemplate transactions;

    public DeletionCoordinator(JdbcTemplate jdbc, TransactionTemplate transactions) {
        this.jdbc = jdbc;
        this.transactions = transactions;
    }

    public void deleteDocument(AuthenticatedUser user, UUID documentId) {
        transactions.executeWithoutResult(status -> {
            List<UUID> documents = jdbc.query("""
                    SELECT id FROM knowflow.documents
                     WHERE id = ? AND owner_user_id = ? AND status = 'ACTIVE'
                     FOR UPDATE
                    """, (result, row) -> result.getObject(1, UUID.class), documentId, user.id());
            if (documents.isEmpty()) {
                throw ApiFailure.resourceNotFound();
            }
            deleteLockedDocument(documentId);
        });
    }

    public void deleteKnowledgeBase(AuthenticatedUser user, UUID knowledgeBaseId) {
        transactions.executeWithoutResult(status -> {
            List<UUID> knowledgeBases = jdbc.query("""
                    SELECT id FROM knowflow.knowledge_bases
                     WHERE id = ? AND owner_user_id = ? AND status = 'ACTIVE'
                     FOR UPDATE
                    """, (result, row) -> result.getObject(1, UUID.class),
                    knowledgeBaseId, user.id());
            if (knowledgeBases.isEmpty()) {
                throw ApiFailure.resourceNotFound();
            }
            List<UUID> documents = jdbc.query("""
                    SELECT id FROM knowflow.documents
                     WHERE knowledge_base_id = ? AND owner_user_id = ? AND status = 'ACTIVE'
                     ORDER BY id
                     FOR UPDATE
                    """, (result, row) -> result.getObject(1, UUID.class),
                    knowledgeBaseId, user.id());
            for (UUID documentId : documents) {
                deleteLockedDocument(documentId);
            }
            jdbc.update("""
                    UPDATE knowflow.knowledge_bases
                       SET status = 'DELETED', deleted_at = CURRENT_TIMESTAMP,
                           updated_at = CURRENT_TIMESTAMP
                     WHERE id = ? AND owner_user_id = ? AND status = 'ACTIVE'
                    """, knowledgeBaseId, user.id());
        });
    }

    private void deleteLockedDocument(UUID documentId) {
        List<RunningExecution> executions = jdbc.query("""
                SELECT id, lease_id, fencing FROM knowflow.indexing_tasks
                 WHERE document_id = ? AND status = 'RUNNING'
                 ORDER BY id
                 FOR UPDATE
                """, (result, row) -> new RunningExecution(
                result.getObject("id", UUID.class), result.getObject("lease_id", UUID.class),
                result.getLong("fencing")), documentId);
        for (RunningExecution execution : executions) {
            jdbc.update("""
                    INSERT INTO knowflow.execution_cancellation_queue
                        (id, task_id, lease_id, fencing, request_id)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT (task_id, lease_id, fencing) DO NOTHING
                    """, UUID.randomUUID(), execution.taskId(), execution.leaseId(),
                    execution.fencing(), UUID.randomUUID().toString());
        }

        List<String> objectKeys = jdbc.query("""
                SELECT object_key FROM knowflow.content_versions
                 WHERE document_id = ? ORDER BY version_no
                """, (result, row) -> result.getString(1), documentId);
        for (String objectKey : objectKeys) {
            jdbc.update("""
                    INSERT INTO knowflow.storage_cleanup_queue (id, object_key)
                    VALUES (?, ?) ON CONFLICT (object_key) DO NOTHING
                    """, UUID.randomUUID(), objectKey);
        }

        List<UUID> indexVersions = jdbc.query("""
                SELECT id FROM knowflow.index_versions WHERE document_id = ? ORDER BY generation, id
                """, (result, row) -> result.getObject(1, UUID.class), documentId);
        for (UUID indexVersionId : indexVersions) {
            jdbc.update("""
                    INSERT INTO knowflow.index_cleanup_queue (id, index_version_id)
                    VALUES (?, ?) ON CONFLICT (index_version_id) DO NOTHING
                    """, UUID.randomUUID(), indexVersionId);
        }

        jdbc.update("""
                UPDATE knowflow.index_versions
                   SET status = CASE WHEN status = 'BUILDING' THEN 'FAILED'
                                     WHEN status = 'READY' THEN 'RETIRED' ELSE status END,
                       failure_code = CASE WHEN status = 'BUILDING'
                                           THEN 'EXECUTION_CANCELLED' ELSE failure_code END
                 WHERE document_id = ? AND status IN ('BUILDING', 'READY')
                """, documentId);
        jdbc.update("""
                UPDATE knowflow.indexing_tasks
                   SET status = 'CANCELLED', lease_id = NULL, lease_expires_at = NULL,
                       execution_token_hash = NULL, failure_code = NULL,
                       finished_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                 WHERE document_id = ? AND status IN ('QUEUED', 'RUNNING')
                """, documentId);
        jdbc.update("""
                UPDATE knowflow.documents
                   SET status = 'DELETED', deleted_at = CURRENT_TIMESTAMP,
                       active_index_version_id = NULL, updated_at = CURRENT_TIMESTAMP
                 WHERE id = ? AND status = 'ACTIVE'
                """, documentId);
    }

    private record RunningExecution(UUID taskId, UUID leaseId, long fencing) {}
}
