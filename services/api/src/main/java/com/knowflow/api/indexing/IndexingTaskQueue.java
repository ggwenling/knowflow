package com.knowflow.api.indexing;

import java.security.SecureRandom;
import java.util.Base64;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import com.knowflow.api.auth.AuthService;
import com.knowflow.api.config.IndexingProperties;
import com.knowflow.api.error.ApiError;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
@Profile("database")
public class IndexingTaskQueue {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final List<Integer> BACKOFF_SECONDS = List.of(5, 30);

    private final JdbcTemplate jdbc;
    private final TransactionTemplate transactions;
    private final IndexingProperties properties;

    public IndexingTaskQueue(JdbcTemplate jdbc, TransactionTemplate transactions,
                             IndexingProperties properties) {
        properties.requireValid();
        this.jdbc = jdbc;
        this.transactions = transactions;
        this.properties = properties;
    }

    public Optional<ClaimedIndexTask> claimNext() {
        ClaimedIndexTask claim = transactions.execute(status -> {
            List<UUID> candidates = jdbc.query("""
                    SELECT t.id
                      FROM knowflow.indexing_tasks t
                      JOIN knowflow.documents d ON d.id = t.document_id
                      JOIN knowflow.knowledge_bases kb
                        ON kb.id = t.knowledge_base_id AND kb.owner_user_id = t.owner_user_id
                     WHERE d.status = 'ACTIVE' AND kb.status = 'ACTIVE'
                       AND ((t.status = 'QUEUED' AND t.available_at <= clock_timestamp())
                         OR (t.status = 'RUNNING' AND t.lease_expires_at <= clock_timestamp()))
                     ORDER BY t.available_at, t.created_at, t.id
                     LIMIT 16
                    """, (result, row) -> result.getObject(1, UUID.class));

            for (UUID taskId : candidates) {
                DocumentLock document = lockDocument(taskId);
                if (document == null) {
                    continue;
                }
                TaskRow task = lockTask(taskId);
                if (task == null || !task.eligible()) {
                    continue;
                }
                if (!"ACTIVE".equals(document.status())
                        || !task.contentVersionId().equals(document.currentContentVersionId())) {
                    cancelObsoleteTask(task);
                    continue;
                }
                if (task.attemptCount() >= properties.getMaxAttempts()) {
                    failExhaustedTask(task, "RUNNING".equals(task.status())
                            ? "WORKER_LOST" : "MODEL_FAILURE");
                    continue;
                }

                boolean recovery = task.attemptCount() > 0 || "RUNNING".equals(task.status());
                UUID indexVersionId = task.indexVersionId();
                if (recovery) {
                    failCandidate(indexVersionId, "RUNNING".equals(task.status())
                            ? "WORKER_LOST" : "MODEL_FAILURE");
                    indexVersionId = createIsolatedCandidate(task);
                } else if (!isBuilding(indexVersionId)) {
                    failExhaustedTask(task, "INDEX_WRITE_FAILED");
                    continue;
                }

                int attempt = task.attemptCount() + 1;
                long fencing = task.fencing() + 1;
                if (fencing < 1) {
                    failExhaustedTask(task, "INDEX_WRITE_FAILED");
                    continue;
                }
                UUID leaseId = UUID.randomUUID();
                String token = executionToken();
                String tokenHash = AuthService.sha256(token);
                String requestId = UUID.randomUUID().toString();
                java.time.OffsetDateTime expiresAt = jdbc.queryForObject("""
                        UPDATE knowflow.indexing_tasks
                           SET status = 'RUNNING', attempt_count = ?, fencing = ?,
                               lease_id = ?, lease_expires_at = clock_timestamp()
                                   + (? * INTERVAL '1 second'),
                               execution_token_hash = ?, last_request_id = ?,
                               index_version_id = ?, failure_code = NULL,
                               accepted_lease_id = NULL, accepted_fencing = NULL,
                               accepted_execution_token_hash = NULL,
                               accepted_completion_sha256 = NULL,
                               finished_at = NULL, updated_at = CURRENT_TIMESTAMP
                         WHERE id = ?
                        RETURNING lease_expires_at
                        """, java.time.OffsetDateTime.class,
                        attempt, fencing, leaseId, properties.getLeaseSeconds(), tokenHash,
                        requestId, indexVersionId, task.id());

                LeaseContext lease = new LeaseContext(task.id(), task.ownerId(),
                        task.knowledgeBaseId(), task.documentId(), task.contentVersionId(),
                        indexVersionId, task.pipelineProfileId(), leaseId, fencing, token);
                IndexDispatch dispatch = new IndexDispatch(ApiError.CONTRACT_VERSION, requestId,
                        lease, expiresAt,
                        new IndexDispatch.SourceFile(task.contentVersionId(),
                                task.sourceSha256(), task.sourceFormat()),
                        properties.getRuntimeProfileId());
                return new ClaimedIndexTask(lease, dispatch);
            }
            return null;
        });
        return Optional.ofNullable(claim);
    }

    public void rejectDispatch(ClaimedIndexTask claim) {
        transactions.executeWithoutResult(status -> {
            LeaseContext lease = claim.lease();
            DocumentLock document = lockDocument(lease.taskId());
            if (document == null) {
                return;
            }
            TaskRow task = lockTask(lease.taskId());
            if (!matchesCurrentLease(task, lease)) {
                return;
            }
            failCandidate(task.indexVersionId(), "MODEL_FAILURE");
            if (task.attemptCount() >= properties.getMaxAttempts()) {
                jdbc.update("""
                        UPDATE knowflow.indexing_tasks
                           SET status = 'FAILED', failure_code = 'MODEL_FAILURE',
                               lease_id = NULL, lease_expires_at = NULL,
                               execution_token_hash = NULL, finished_at = CURRENT_TIMESTAMP,
                               updated_at = CURRENT_TIMESTAMP
                         WHERE id = ?
                        """, task.id());
            } else {
                int backoff = BACKOFF_SECONDS.get(Math.min(task.attemptCount() - 1,
                        BACKOFF_SECONDS.size() - 1));
                jdbc.update("""
                        UPDATE knowflow.indexing_tasks
                           SET status = 'QUEUED', failure_code = NULL,
                               lease_id = NULL, lease_expires_at = NULL,
                               execution_token_hash = NULL,
                               available_at = clock_timestamp() + (? * INTERVAL '1 second'),
                               finished_at = NULL, updated_at = CURRENT_TIMESTAMP
                         WHERE id = ?
                        """, backoff, task.id());
            }
        });
    }

    private DocumentLock lockDocument(UUID taskId) {
        List<DocumentLock> rows = jdbc.query("""
                SELECT d.id, d.status, d.current_content_version_id
                  FROM knowflow.documents d
                  JOIN knowflow.indexing_tasks t ON t.document_id = d.id
                 WHERE t.id = ?
                 FOR UPDATE OF d SKIP LOCKED
                """, (result, row) -> new DocumentLock(
                result.getObject("id", UUID.class), result.getString("status"),
                result.getObject("current_content_version_id", UUID.class)), taskId);
        return rows.isEmpty() ? null : rows.getFirst();
    }

    private TaskRow lockTask(UUID taskId) {
        List<TaskRow> rows = jdbc.query("""
                SELECT t.id, t.owner_user_id, t.knowledge_base_id, t.document_id,
                       t.content_version_id, t.index_version_id, t.status,
                       t.attempt_count, t.fencing, t.lease_id, t.lease_expires_at,
                       t.execution_token_hash, iv.pipeline_profile_id,
                       cv.source_sha256, cv.source_format,
                       CASE
                         WHEN t.status = 'QUEUED' THEN t.available_at <= clock_timestamp()
                         WHEN t.status = 'RUNNING' THEN t.lease_expires_at <= clock_timestamp()
                         ELSE FALSE
                       END AS eligible
                  FROM knowflow.indexing_tasks t
                  JOIN knowflow.index_versions iv ON iv.id = t.index_version_id
                  JOIN knowflow.content_versions cv
                    ON cv.id = t.content_version_id AND cv.document_id = t.document_id
                 WHERE t.id = ?
                 FOR UPDATE OF t SKIP LOCKED
                """, (result, row) -> new TaskRow(
                result.getObject("id", UUID.class),
                result.getObject("owner_user_id", UUID.class),
                result.getObject("knowledge_base_id", UUID.class),
                result.getObject("document_id", UUID.class),
                result.getObject("content_version_id", UUID.class),
                result.getObject("index_version_id", UUID.class),
                result.getString("status"), result.getInt("attempt_count"),
                result.getLong("fencing"), result.getObject("lease_id", UUID.class),
                result.getObject("lease_expires_at", java.time.OffsetDateTime.class),
                result.getString("execution_token_hash"), result.getString("pipeline_profile_id"),
                result.getString("source_sha256"), result.getString("source_format"),
                result.getBoolean("eligible")), taskId);
        return rows.isEmpty() ? null : rows.getFirst();
    }

    private UUID createIsolatedCandidate(TaskRow task) {
        Integer generation = jdbc.queryForObject("""
                SELECT COALESCE(MAX(generation), 0) + 1
                  FROM knowflow.index_versions
                 WHERE document_id = ? AND content_version_id = ?
                   AND pipeline_profile_id = ?
                """, Integer.class, task.documentId(), task.contentVersionId(),
                task.pipelineProfileId());
        UUID id = UUID.randomUUID();
        String modelProfile = jdbc.queryForObject("""
                SELECT embedding_model_profile_id FROM knowflow.index_versions WHERE id = ?
                """, String.class, task.indexVersionId());
        jdbc.update("""
                INSERT INTO knowflow.index_versions
                    (id, document_id, content_version_id, pipeline_profile_id, generation,
                     embedding_model_profile_id, embedding_dimensions)
                VALUES (?, ?, ?, ?, ?, ?, 1024)
                """, id, task.documentId(), task.contentVersionId(), task.pipelineProfileId(),
                generation, modelProfile);
        return id;
    }

    private boolean isBuilding(UUID indexVersionId) {
        Integer count = jdbc.queryForObject("""
                SELECT count(*) FROM knowflow.index_versions
                 WHERE id = ? AND status = 'BUILDING'
                """, Integer.class, indexVersionId);
        return count != null && count == 1;
    }

    private void cancelObsoleteTask(TaskRow task) {
        failCandidate(task.indexVersionId(), "EXECUTION_CANCELLED");
        jdbc.update("""
                UPDATE knowflow.indexing_tasks
                   SET status = 'CANCELLED', failure_code = NULL,
                       lease_id = NULL, lease_expires_at = NULL, execution_token_hash = NULL,
                       finished_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                 WHERE id = ? AND status IN ('QUEUED', 'RUNNING')
                """, task.id());
    }

    private void failExhaustedTask(TaskRow task, String failureCode) {
        failCandidate(task.indexVersionId(), failureCode);
        jdbc.update("""
                UPDATE knowflow.indexing_tasks
                   SET status = 'FAILED', failure_code = ?, lease_id = NULL,
                       lease_expires_at = NULL, execution_token_hash = NULL,
                       finished_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                 WHERE id = ? AND status IN ('QUEUED', 'RUNNING')
                """, failureCode, task.id());
    }

    private void failCandidate(UUID indexVersionId, String failureCode) {
        jdbc.update("""
                UPDATE knowflow.index_versions
                   SET status = 'FAILED', failure_code = ?
                 WHERE id = ? AND status = 'BUILDING'
                """, failureCode, indexVersionId);
    }

    private static boolean matchesCurrentLease(TaskRow task, LeaseContext lease) {
        return task != null && "RUNNING".equals(task.status())
                && task.id().equals(lease.taskId())
                && task.documentId().equals(lease.documentId())
                && task.contentVersionId().equals(lease.contentVersionId())
                && task.indexVersionId().equals(lease.indexVersionId())
                && lease.leaseId().equals(task.leaseId())
                && lease.fencing() == task.fencing()
                && AuthService.sha256(lease.executionToken()).equals(task.executionTokenHash());
    }

    private static String executionToken() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    private record DocumentLock(UUID id, String status, UUID currentContentVersionId) {}

    private record TaskRow(UUID id, UUID ownerId, UUID knowledgeBaseId, UUID documentId,
                           UUID contentVersionId, UUID indexVersionId, String status,
                           int attemptCount, long fencing, UUID leaseId,
                           java.time.OffsetDateTime leaseExpiresAt, String executionTokenHash,
                           String pipelineProfileId, String sourceSha256, String sourceFormat,
                           boolean eligible) {}
}
