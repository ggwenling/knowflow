package com.knowflow.api.indexing;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.List;
import java.util.UUID;

import com.knowflow.api.auth.AuthService;
import com.knowflow.api.error.ApiFailure;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/** Locks resources in document-then-task order and validates the complete execution fence. */
@Component
@Profile("database")
public final class LeaseAuthorizer {
    private final JdbcTemplate jdbc;

    public LeaseAuthorizer(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public AuthorizedExecution lockAndVerify(UUID routeTaskId, LeaseContext supplied) {
        if (routeTaskId == null || supplied == null || supplied.executionToken() == null
                || supplied.executionToken().isBlank()) {
            throw ApiFailure.leaseRejected();
        }

        List<DocumentState> documents = jdbc.query("""
                SELECT d.id, d.owner_user_id, d.knowledge_base_id, d.status AS document_status,
                       d.current_content_version_id, kb.status AS knowledge_base_status,
                       cv.object_key, cv.byte_size, cv.source_sha256, cv.source_format
                  FROM knowflow.documents d
                  JOIN knowflow.indexing_tasks t ON t.document_id = d.id
                  JOIN knowflow.knowledge_bases kb
                    ON kb.id = d.knowledge_base_id AND kb.owner_user_id = d.owner_user_id
                  JOIN knowflow.content_versions cv
                    ON cv.id = t.content_version_id AND cv.document_id = d.id
                 WHERE t.id = ?
                 FOR UPDATE OF d
                """, (result, row) -> new DocumentState(
                result.getObject("id", UUID.class),
                result.getObject("owner_user_id", UUID.class),
                result.getObject("knowledge_base_id", UUID.class),
                result.getString("document_status"),
                result.getObject("current_content_version_id", UUID.class),
                result.getString("knowledge_base_status"),
                result.getString("object_key"),
                result.getLong("byte_size"),
                result.getString("source_sha256"),
                result.getString("source_format")), routeTaskId);
        if (documents.isEmpty()) {
            throw ApiFailure.leaseRejected();
        }
        DocumentState document = documents.getFirst();
        if (!"ACTIVE".equals(document.documentStatus())
                || !"ACTIVE".equals(document.knowledgeBaseStatus())) {
            throw ApiFailure.documentUnavailable();
        }

        List<TaskState> tasks = jdbc.query("""
                SELECT t.id, t.owner_user_id, t.knowledge_base_id, t.document_id,
                       t.content_version_id, t.index_version_id, t.status, t.lease_id,
                       t.fencing, t.execution_token_hash,
                       t.lease_expires_at > clock_timestamp() AS lease_active,
                       iv.pipeline_profile_id, iv.status AS index_status,
                       iv.embedding_model_profile_id
                  FROM knowflow.indexing_tasks t
                  JOIN knowflow.index_versions iv ON iv.id = t.index_version_id
                 WHERE t.id = ?
                 FOR UPDATE OF t
                """, (result, row) -> new TaskState(
                result.getObject("id", UUID.class),
                result.getObject("owner_user_id", UUID.class),
                result.getObject("knowledge_base_id", UUID.class),
                result.getObject("document_id", UUID.class),
                result.getObject("content_version_id", UUID.class),
                result.getObject("index_version_id", UUID.class),
                result.getString("status"),
                result.getObject("lease_id", UUID.class),
                result.getLong("fencing"),
                result.getString("execution_token_hash"),
                result.getBoolean("lease_active"),
                result.getString("pipeline_profile_id"),
                result.getString("index_status"),
                result.getString("embedding_model_profile_id")), routeTaskId);
        if (tasks.isEmpty()) {
            throw ApiFailure.leaseRejected();
        }
        TaskState task = tasks.getFirst();
        String suppliedTokenHash = AuthService.sha256(supplied.executionToken());
        boolean tokenMatches = task.executionTokenHash() != null
                && MessageDigest.isEqual(task.executionTokenHash().getBytes(StandardCharsets.US_ASCII),
                        suppliedTokenHash.getBytes(StandardCharsets.US_ASCII));
        if (!routeTaskId.equals(supplied.taskId())
                || !"RUNNING".equals(task.status()) || !task.leaseActive()
                || !"BUILDING".equals(task.indexStatus()) || !tokenMatches
                || !task.id().equals(supplied.taskId())
                || !task.ownerId().equals(supplied.ownerId())
                || !task.knowledgeBaseId().equals(supplied.knowledgeBaseId())
                || !task.documentId().equals(supplied.documentId())
                || !task.contentVersionId().equals(supplied.contentVersionId())
                || !task.indexVersionId().equals(supplied.indexVersionId())
                || !task.leaseId().equals(supplied.leaseId())
                || task.fencing() != supplied.fencing()
                || !task.pipelineProfileId().equals(supplied.pipelineProfileId())
                || !document.id().equals(task.documentId())
                || !document.ownerId().equals(task.ownerId())
                || !document.knowledgeBaseId().equals(task.knowledgeBaseId())
                || !task.contentVersionId().equals(document.currentContentVersionId())) {
            throw ApiFailure.leaseRejected();
        }
        return new AuthorizedExecution(task.id(), task.ownerId(), task.knowledgeBaseId(),
                task.documentId(), task.contentVersionId(), task.indexVersionId(),
                task.pipelineProfileId(), task.embeddingModelProfileId(), task.leaseId(),
                task.fencing(), document.objectKey(), document.byteSize(), document.sourceSha256(),
                document.sourceFormat());
    }

    public record AuthorizedExecution(UUID taskId, UUID ownerId, UUID knowledgeBaseId,
                                      UUID documentId, UUID contentVersionId,
                                      UUID indexVersionId, String pipelineProfileId,
                                      String embeddingModelProfileId, UUID leaseId, long fencing,
                                      String objectKey, long byteSize, String sourceSha256,
                                      String sourceFormat) {}

    private record DocumentState(UUID id, UUID ownerId, UUID knowledgeBaseId,
                                 String documentStatus, UUID currentContentVersionId,
                                 String knowledgeBaseStatus, String objectKey, long byteSize,
                                 String sourceSha256, String sourceFormat) {}

    private record TaskState(UUID id, UUID ownerId, UUID knowledgeBaseId, UUID documentId,
                             UUID contentVersionId, UUID indexVersionId, String status,
                             UUID leaseId, long fencing, String executionTokenHash,
                             boolean leaseActive, String pipelineProfileId, String indexStatus,
                             String embeddingModelProfileId) {}
}
