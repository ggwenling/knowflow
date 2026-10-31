package com.knowflow.api.document;

import java.util.List;
import java.util.UUID;

import com.knowflow.api.config.IndexingProperties;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

/** Retains the latest two successful publications, plus in-flight snapshot dependencies. */
@Service
@Profile("database")
public class VersionRetentionService {
    private final JdbcTemplate jdbc;
    private final TransactionTemplate transactions;
    private final IndexingProperties properties;

    public VersionRetentionService(JdbcTemplate jdbc, TransactionTemplate transactions,
                                   IndexingProperties properties) {
        this.jdbc = jdbc;
        this.transactions = transactions;
        this.properties = properties;
    }

    @Scheduled(fixedDelayString = "${knowflow.indexing.poll-delay-millis:1000}")
    public void cleanExpiredVersions() {
        if (!properties.isSchedulerEnabled()) {
            return;
        }
        List<UUID> documents = jdbc.query("""
                SELECT id FROM knowflow.documents WHERE status = 'ACTIVE'
                 ORDER BY updated_at
                """, (row, index) -> row.getObject(1, UUID.class));
        for (UUID document : documents) {
            cleanDocument(document);
        }
    }

    public void cleanDocument(UUID documentId) {
        transactions.executeWithoutResult(status -> {
            List<UUID> locked = jdbc.query("""
                    SELECT d.id FROM knowflow.documents d
                      JOIN knowflow.knowledge_bases kb ON kb.id = d.knowledge_base_id
                     WHERE d.id = ? AND d.status = 'ACTIVE' AND kb.status = 'ACTIVE'
                     FOR UPDATE OF d SKIP LOCKED
                    """, (row, index) -> row.getObject(1, UUID.class), documentId);
            if (locked.isEmpty()) {
                return;
            }
            List<UUID> expired = jdbc.query("""
                    SELECT iv.id FROM knowflow.index_versions iv
                      JOIN knowflow.documents d ON d.id = iv.document_id
                     WHERE iv.document_id = ? AND iv.cleaned_at IS NULL
                       AND iv.status IN ('RETIRED', 'FAILED')
                       AND iv.id IS DISTINCT FROM d.active_index_version_id
                       AND iv.id NOT IN (
                           SELECT kept.id FROM knowflow.index_versions kept
                            WHERE kept.document_id = d.id AND kept.ready_at IS NOT NULL
                            ORDER BY kept.ready_at DESC, kept.id DESC LIMIT 2)
                       AND NOT EXISTS (SELECT 1 FROM knowflow.indexing_tasks t
                            WHERE t.index_version_id = iv.id AND t.status IN ('QUEUED', 'RUNNING'))
                       AND NOT EXISTS (SELECT 1 FROM knowflow.question_scope_indexes s
                            JOIN knowflow.questions q ON q.id = s.question_id
                            WHERE s.index_version_id = iv.id AND q.status = 'PROCESSING')
                    """, (row, index) -> row.getObject(1, UUID.class), documentId);
            for (UUID index : expired) {
                jdbc.update("DELETE FROM knowflow.question_sources WHERE index_version_id = ?", index);
                jdbc.update("DELETE FROM knowflow.question_scope_indexes WHERE index_version_id = ?", index);
                jdbc.update("DELETE FROM knowflow.chunk_embeddings WHERE index_version_id = ?", index);
                jdbc.update("DELETE FROM knowflow.chunks WHERE index_version_id = ?", index);
                jdbc.update("UPDATE knowflow.index_versions SET cleaned_at = CURRENT_TIMESTAMP WHERE id = ?",
                        index);
            }
            List<ContentObject> contents = jdbc.query("""
                    SELECT cv.id, cv.object_key FROM knowflow.content_versions cv
                      JOIN knowflow.documents d ON d.id = cv.document_id
                     WHERE cv.document_id = ? AND cv.cleaned_at IS NULL
                       AND cv.id IS DISTINCT FROM d.current_content_version_id
                       AND cv.id IS DISTINCT FROM d.pending_content_version_id
                       AND NOT EXISTS (SELECT 1 FROM knowflow.index_versions iv
                           WHERE iv.content_version_id = cv.id AND iv.cleaned_at IS NULL)
                       AND NOT EXISTS (SELECT 1 FROM knowflow.indexing_tasks t
                           WHERE t.content_version_id = cv.id AND t.status IN ('QUEUED', 'RUNNING'))
                       AND NOT EXISTS (SELECT 1 FROM knowflow.question_scope_indexes s
                           JOIN knowflow.questions q ON q.id = s.question_id
                           WHERE s.content_version_id = cv.id AND q.status = 'PROCESSING')
                    """, (row, index) -> new ContentObject(row.getObject("id", UUID.class),
                    row.getString("object_key")), documentId);
            for (ContentObject content : contents) {
                jdbc.update("""
                        INSERT INTO knowflow.storage_cleanup_queue (id, object_key)
                        VALUES (?, ?) ON CONFLICT (object_key) DO NOTHING
                        """, UUID.randomUUID(), content.objectKey());
                jdbc.update("UPDATE knowflow.content_versions SET cleaned_at = CURRENT_TIMESTAMP WHERE id = ?",
                        content.id());
            }
        });
    }

    private record ContentObject(UUID id, String objectKey) {}
}
