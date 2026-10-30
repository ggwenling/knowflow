package com.knowflow.api.document;

import java.util.List;
import java.util.UUID;

import com.knowflow.api.error.ApiError;
import com.knowflow.api.indexing.AiExecutionCancellationClient;
import com.knowflow.api.indexing.CancelExecution;
import com.knowflow.api.storage.ObjectStoreException;
import com.knowflow.api.storage.S3ObjectStore;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Profile;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionTemplate;

@Component
@Profile("database & storage")
@ConditionalOnProperty(prefix = "knowflow.indexing", name = "scheduler-enabled",
        havingValue = "true")
public class DeletionOutboxScheduler {
    private static final Logger LOGGER = LoggerFactory.getLogger(DeletionOutboxScheduler.class);
    private static final List<Integer> RETRY_SECONDS = List.of(5, 30, 300, 1800);

    private final JdbcTemplate jdbc;
    private final TransactionTemplate transactions;
    private final S3ObjectStore objects;
    private final AiExecutionCancellationClient cancellationClient;

    public DeletionOutboxScheduler(JdbcTemplate jdbc, TransactionTemplate transactions,
                                   S3ObjectStore objects,
                                   AiExecutionCancellationClient cancellationClient) {
        this.jdbc = jdbc;
        this.transactions = transactions;
        this.objects = objects;
        this.cancellationClient = cancellationClient;
    }

    @Scheduled(fixedDelayString = "${knowflow.indexing.poll-delay-millis:1000}")
    public void processOneCancellation() {
        CancellationItem item = claimCancellation();
        if (item == null) {
            return;
        }
        try {
            cancellationClient.cancel(new CancelExecution(ApiError.CONTRACT_VERSION,
                    item.requestId(), item.taskId(), item.leaseId(), item.fencing()));
            jdbc.update("DELETE FROM knowflow.execution_cancellation_queue WHERE id = ?", item.id());
        } catch (RuntimeException unavailable) {
            rescheduleCancellation(item);
            LOGGER.warn("AI cancellation delivery failed; the outbox will retry");
        }
    }

    @Scheduled(fixedDelayString = "${knowflow.indexing.poll-delay-millis:1000}")
    public void processOneObjectCleanup() {
        ObjectCleanupItem item = claimObjectCleanup();
        if (item == null) {
            return;
        }
        try {
            objects.deleteObject(item.objectKey());
            jdbc.update("DELETE FROM knowflow.storage_cleanup_queue WHERE id = ?", item.id());
        } catch (ObjectStoreException unavailable) {
            rescheduleObjectCleanup(item);
            LOGGER.warn("Object cleanup failed; the object remains queued for retry");
        }
    }

    @Scheduled(fixedDelayString = "${knowflow.indexing.poll-delay-millis:1000}")
    public void processOneIndexCleanup() {
        IndexCleanupItem item = claimIndexCleanup();
        if (item == null) {
            return;
        }
        try {
            transactions.executeWithoutResult(status -> {
                jdbc.update("DELETE FROM knowflow.chunk_embeddings WHERE index_version_id = ?",
                        item.indexVersionId());
                jdbc.update("DELETE FROM knowflow.chunks WHERE index_version_id = ?",
                        item.indexVersionId());
                jdbc.update("DELETE FROM knowflow.index_cleanup_queue WHERE id = ?", item.id());
            });
        } catch (DataAccessException unavailable) {
            rescheduleIndexCleanup(item);
            LOGGER.warn("Index cleanup failed; the rows remain queued for retry");
        }
    }

    private CancellationItem claimCancellation() {
        return transactions.execute(status -> {
            List<CancellationItem> rows = jdbc.query("""
                    SELECT id, task_id, lease_id, fencing, request_id, attempt_count
                      FROM knowflow.execution_cancellation_queue
                     WHERE available_at <= clock_timestamp()
                     ORDER BY available_at, created_at
                     LIMIT 1 FOR UPDATE SKIP LOCKED
                    """, (result, row) -> new CancellationItem(
                    result.getObject("id", UUID.class), result.getObject("task_id", UUID.class),
                    result.getObject("lease_id", UUID.class), result.getLong("fencing"),
                    result.getString("request_id"), result.getInt("attempt_count") + 1));
            if (rows.isEmpty()) {
                return null;
            }
            CancellationItem item = rows.getFirst();
            jdbc.update("""
                    UPDATE knowflow.execution_cancellation_queue
                       SET attempt_count = ?, available_at = clock_timestamp() + INTERVAL '10 minutes',
                           updated_at = CURRENT_TIMESTAMP
                     WHERE id = ?
                    """, item.attemptCount(), item.id());
            return item;
        });
    }

    private ObjectCleanupItem claimObjectCleanup() {
        return transactions.execute(status -> {
            List<ObjectCleanupItem> rows = jdbc.query("""
                    SELECT id, object_key, attempt_count FROM knowflow.storage_cleanup_queue
                     WHERE available_at <= clock_timestamp()
                     ORDER BY available_at, created_at
                     LIMIT 1 FOR UPDATE SKIP LOCKED
                    """, (result, row) -> new ObjectCleanupItem(
                    result.getObject("id", UUID.class), result.getString("object_key"),
                    result.getInt("attempt_count") + 1));
            if (rows.isEmpty()) {
                return null;
            }
            ObjectCleanupItem item = rows.getFirst();
            jdbc.update("""
                    UPDATE knowflow.storage_cleanup_queue
                       SET attempt_count = ?, available_at = clock_timestamp() + INTERVAL '10 minutes',
                           updated_at = CURRENT_TIMESTAMP
                     WHERE id = ?
                    """, item.attemptCount(), item.id());
            return item;
        });
    }

    private IndexCleanupItem claimIndexCleanup() {
        return transactions.execute(status -> {
            List<IndexCleanupItem> rows = jdbc.query("""
                    SELECT id, index_version_id, attempt_count FROM knowflow.index_cleanup_queue
                     WHERE available_at <= clock_timestamp()
                     ORDER BY available_at, created_at
                     LIMIT 1 FOR UPDATE SKIP LOCKED
                    """, (result, row) -> new IndexCleanupItem(
                    result.getObject("id", UUID.class),
                    result.getObject("index_version_id", UUID.class),
                    result.getInt("attempt_count") + 1));
            if (rows.isEmpty()) {
                return null;
            }
            IndexCleanupItem item = rows.getFirst();
            jdbc.update("""
                    UPDATE knowflow.index_cleanup_queue
                       SET attempt_count = ?, available_at = clock_timestamp() + INTERVAL '10 minutes',
                           updated_at = CURRENT_TIMESTAMP
                     WHERE id = ?
                    """, item.attemptCount(), item.id());
            return item;
        });
    }

    private void rescheduleCancellation(CancellationItem item) {
        jdbc.update("""
                UPDATE knowflow.execution_cancellation_queue
                   SET last_error_code = 'AI_UNAVAILABLE',
                       available_at = clock_timestamp() + (? * INTERVAL '1 second'),
                       updated_at = CURRENT_TIMESTAMP WHERE id = ?
                """, backoff(item.attemptCount()), item.id());
    }

    private void rescheduleObjectCleanup(ObjectCleanupItem item) {
        jdbc.update("""
                UPDATE knowflow.storage_cleanup_queue
                   SET last_error_code = 'STORAGE_UNAVAILABLE',
                       available_at = clock_timestamp() + (? * INTERVAL '1 second'),
                       updated_at = CURRENT_TIMESTAMP WHERE id = ?
                """, backoff(item.attemptCount()), item.id());
    }

    private void rescheduleIndexCleanup(IndexCleanupItem item) {
        jdbc.update("""
                UPDATE knowflow.index_cleanup_queue
                   SET last_error_code = 'DATABASE_UNAVAILABLE',
                       available_at = clock_timestamp() + (? * INTERVAL '1 second'),
                       updated_at = CURRENT_TIMESTAMP WHERE id = ?
                """, backoff(item.attemptCount()), item.id());
    }

    private static int backoff(int attemptCount) {
        return RETRY_SECONDS.get(Math.min(Math.max(attemptCount - 1, 0), RETRY_SECONDS.size() - 1));
    }

    private record CancellationItem(UUID id, UUID taskId, UUID leaseId, long fencing,
                                    String requestId, int attemptCount) {}
    private record ObjectCleanupItem(UUID id, String objectKey, int attemptCount) {}
    private record IndexCleanupItem(UUID id, UUID indexVersionId, int attemptCount) {}
}
