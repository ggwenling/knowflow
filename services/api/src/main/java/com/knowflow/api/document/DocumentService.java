package com.knowflow.api.document;

import java.io.IOException;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import java.util.UUID;

import com.knowflow.api.error.ApiError;
import com.knowflow.api.error.ApiFailure;
import com.knowflow.api.security.AuthenticatedUser;
import com.knowflow.api.storage.ObjectStoreException;
import com.knowflow.api.storage.ObjectStore;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.multipart.MultipartFile;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@Service
@Profile("database & storage")
public class DocumentService {
    private static final Logger LOGGER = LoggerFactory.getLogger(DocumentService.class);
    private static final int MAX_LIMIT = 100;
    private static final int MAX_OFFSET = 1_000_000;
    private static final String PIPELINE_PROFILE = "knowflow-index-v1";
    private static final String EMBEDDING_PROFILE = "BAAI/bge-m3";

    private final JdbcTemplate jdbc;
    private final TransactionTemplate transactions;
    private final ObjectStore objectStore;
    private final DeletionCoordinator deletions;

    public DocumentService(JdbcTemplate jdbc, TransactionTemplate transactions,
                           ObjectStore objectStore, DeletionCoordinator deletions) {
        this.jdbc = jdbc;
        this.transactions = transactions;
        this.objectStore = objectStore;
        this.deletions = deletions;
    }

    public DocumentUploadAccepted upload(AuthenticatedUser user, UUID knowledgeBaseId,
                                         MultipartFile file) {
        if (file == null || file.isEmpty()) {
            throw ApiFailure.unsupportedContent();
        }
        if (file.getSize() > UploadLimits.MAX_FILE_BYTES) {
            throw ApiFailure.resourceLimit();
        }

        byte[] contents;
        try {
            contents = file.getBytes();
        } catch (IOException exception) {
            throw ApiFailure.unsupportedContent();
        }
        if (contents.length == 0) {
            throw ApiFailure.unsupportedContent();
        }
        if (contents.length > UploadLimits.MAX_FILE_BYTES) {
            throw ApiFailure.resourceLimit();
        }

        String originalName = safeOriginalName(file.getOriginalFilename());
        DocumentFormat format = DocumentFormat.fromNameAndBytes(originalName, contents);
        String sha256 = sha256(contents);

        requireOwnedKnowledgeBase(user.id(), knowledgeBaseId);

        UUID documentId = UUID.randomUUID();
        UUID contentVersionId = UUID.randomUUID();
        UUID indexVersionId = UUID.randomUUID();
        UUID taskId = UUID.randomUUID();
        String objectKey = "documents/" + documentId + "/" + contentVersionId;
        try {
            objectStore.putObject(objectKey, format.contentType(), contents);
        } catch (ObjectStoreException storageFailure) {
            String causeType = storageFailure.getCause() == null ? "none"
                    : storageFailure.getCause().getClass().getSimpleName();
            LOGGER.warn("Source upload failed: {} ({})", storageFailure.getMessage(), causeType);
            compensateUpload(objectKey);
            throw storageFailure;
        }

        try {
            return transactions.execute(status -> {
                lockOwnedKnowledgeBase(user.id(), knowledgeBaseId);
                jdbc.update("""
                        INSERT INTO knowflow.documents
                            (id, knowledge_base_id, owner_user_id, original_name)
                        VALUES (?, ?, ?, ?)
                        """, documentId, knowledgeBaseId, user.id(), originalName);
                jdbc.update("""
                        INSERT INTO knowflow.content_versions
                            (id, document_id, version_no, source_sha256, source_format,
                             object_key, byte_size)
                        VALUES (?, ?, 1, ?, ?, ?, ?)
                        """, contentVersionId, documentId, sha256, format.extension(),
                        objectKey, contents.length);
                jdbc.update("""
                        UPDATE knowflow.documents
                           SET current_content_version_id = ?, updated_at = CURRENT_TIMESTAMP
                         WHERE id = ?
                        """, contentVersionId, documentId);
                jdbc.update("""
                        INSERT INTO knowflow.index_versions
                            (id, document_id, content_version_id, pipeline_profile_id,
                             generation, embedding_model_profile_id)
                        VALUES (?, ?, ?, ?, 1, ?)
                        """, indexVersionId, documentId, contentVersionId,
                        PIPELINE_PROFILE, EMBEDDING_PROFILE);
                jdbc.update("""
                        INSERT INTO knowflow.indexing_tasks
                            (id, owner_user_id, knowledge_base_id, document_id,
                             content_version_id, index_version_id)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """, taskId, user.id(), knowledgeBaseId, documentId,
                        contentVersionId, indexVersionId);
                return new DocumentUploadAccepted(ApiError.CONTRACT_VERSION, documentId,
                        taskId, "QUEUED");
            });
        } catch (RuntimeException databaseFailure) {
            compensateUpload(objectKey);
            throw databaseFailure;
        }
    }

    public DocumentListResponse list(AuthenticatedUser user, UUID knowledgeBaseId,
                                     int requestedLimit, int offset) {
        if (requestedLimit < 1 || requestedLimit > MAX_LIMIT || offset < 0 || offset > MAX_OFFSET) {
            throw ApiFailure.invalidRequest();
        }
        List<DocumentResponse> rows = jdbc.query("""
                SELECT d.id, d.knowledge_base_id, d.original_name, cv.source_format,
                       cv.byte_size, cv.source_sha256, d.active_index_version_id,
                       d.created_at, d.updated_at,
                       CASE
                         WHEN active.status = 'READY' THEN 'READY'
                         WHEN latest.status IN ('FAILED', 'CANCELLED') THEN 'FAILED'
                         ELSE 'PROCESSING'
                       END AS public_status
                  FROM knowflow.documents d
                  JOIN knowflow.knowledge_bases kb
                    ON kb.id = d.knowledge_base_id AND kb.owner_user_id = d.owner_user_id
                  JOIN knowflow.content_versions cv
                    ON cv.id = d.current_content_version_id AND cv.document_id = d.id
                  LEFT JOIN knowflow.index_versions active
                    ON active.id = d.active_index_version_id
                  LEFT JOIN LATERAL (
                      SELECT t.status
                        FROM knowflow.indexing_tasks t
                       WHERE t.document_id = d.id
                       ORDER BY t.created_at DESC, t.id DESC
                       LIMIT 1
                  ) latest ON TRUE
                 WHERE d.knowledge_base_id = ? AND d.owner_user_id = ?
                   AND d.status = 'ACTIVE' AND kb.status = 'ACTIVE'
                 ORDER BY d.created_at DESC, d.id DESC
                 LIMIT ? OFFSET ?
                """, DocumentService::mapDocument, knowledgeBaseId, user.id(),
                requestedLimit + 1, offset);
        boolean hasMore = rows.size() > requestedLimit;
        List<DocumentResponse> items = hasMore
                ? List.copyOf(rows.subList(0, requestedLimit)) : rows;
        return new DocumentListResponse(ApiError.CONTRACT_VERSION, items, requestedLimit,
                offset, hasMore);
    }

    public DocumentResponse get(AuthenticatedUser user, UUID documentId) {
        List<DocumentResponse> rows = jdbc.query("""
                SELECT d.id, d.knowledge_base_id, d.original_name, cv.source_format,
                       cv.byte_size, cv.source_sha256, d.active_index_version_id,
                       d.created_at, d.updated_at,
                       CASE
                         WHEN active.status = 'READY' THEN 'READY'
                         WHEN latest.status IN ('FAILED', 'CANCELLED') THEN 'FAILED'
                         ELSE 'PROCESSING'
                       END AS public_status
                  FROM knowflow.documents d
                  JOIN knowflow.knowledge_bases kb
                    ON kb.id = d.knowledge_base_id AND kb.owner_user_id = d.owner_user_id
                  JOIN knowflow.content_versions cv
                    ON cv.id = d.current_content_version_id AND cv.document_id = d.id
                  LEFT JOIN knowflow.index_versions active
                    ON active.id = d.active_index_version_id
                  LEFT JOIN LATERAL (
                      SELECT t.status
                        FROM knowflow.indexing_tasks t
                       WHERE t.document_id = d.id
                       ORDER BY t.created_at DESC, t.id DESC
                       LIMIT 1
                  ) latest ON TRUE
                 WHERE d.id = ? AND d.owner_user_id = ?
                   AND d.status = 'ACTIVE' AND kb.status = 'ACTIVE'
                """, DocumentService::mapDocument, documentId, user.id());
        if (rows.isEmpty()) {
            throw ApiFailure.resourceNotFound();
        }
        return rows.getFirst();
    }

    public TaskStatusResponse getTask(AuthenticatedUser user, UUID taskId) {
        List<TaskStatusResponse> rows = jdbc.query("""
                SELECT t.id, t.document_id, t.status, t.attempt_count, t.failure_code,
                       t.created_at, t.updated_at
                  FROM knowflow.indexing_tasks t
                  JOIN knowflow.documents d
                    ON d.id = t.document_id AND d.knowledge_base_id = t.knowledge_base_id
                   AND d.owner_user_id = t.owner_user_id
                  JOIN knowflow.knowledge_bases kb
                    ON kb.id = t.knowledge_base_id AND kb.owner_user_id = t.owner_user_id
                 WHERE t.id = ? AND t.owner_user_id = ?
                   AND d.status = 'ACTIVE' AND kb.status = 'ACTIVE'
                """, (result, row) -> new TaskStatusResponse(
                ApiError.CONTRACT_VERSION,
                result.getObject("id", UUID.class),
                result.getObject("document_id", UUID.class),
                result.getString("status"),
                result.getInt("attempt_count"),
                result.getString("failure_code"),
                result.getObject("created_at", java.time.OffsetDateTime.class),
                result.getObject("updated_at", java.time.OffsetDateTime.class)),
                taskId, user.id());
        if (rows.isEmpty()) {
            throw ApiFailure.resourceNotFound();
        }
        return rows.getFirst();
    }

    public void delete(AuthenticatedUser user, UUID documentId) {
        deletions.deleteDocument(user, documentId);
    }

    public FileContent readFile(AuthenticatedUser user, UUID documentId, UUID contentVersionId) {
        FileReference file = findReadableFile(user.id(), documentId, contentVersionId);
        byte[] contents = objectStore.getObject(file.objectKey(),
                Math.toIntExact(UploadLimits.MAX_FILE_BYTES));
        if (contents.length != file.byteSize() || !sha256(contents).equals(file.sha256())) {
            throw new ObjectStoreException("Stored source failed integrity verification");
        }
        if (!file.equals(findReadableFile(user.id(), documentId, contentVersionId))) {
            throw ApiFailure.resourceNotFound();
        }
        return new FileContent(file.originalName(), file.format(), file.sha256(), contents);
    }

    private FileReference findReadableFile(UUID ownerId, UUID documentId,
                                           UUID contentVersionId) {
        List<FileReference> files = jdbc.query("""
                SELECT d.original_name, cv.object_key, cv.source_format, cv.source_sha256,
                       cv.byte_size
                  FROM knowflow.documents d
                  JOIN knowflow.knowledge_bases kb
                    ON kb.id = d.knowledge_base_id AND kb.owner_user_id = d.owner_user_id
                   AND kb.status = 'ACTIVE'
                  JOIN knowflow.content_versions cv
                    ON cv.document_id = d.id AND cv.id = ?
                 WHERE d.id = ? AND d.owner_user_id = ? AND d.status = 'ACTIVE'
                """, (row, index) -> new FileReference(row.getString("original_name"),
                row.getString("object_key"), row.getString("source_format"),
                row.getString("source_sha256"), row.getLong("byte_size")),
                contentVersionId, documentId, ownerId);
        if (files.isEmpty()) {
            throw ApiFailure.resourceNotFound();
        }
        return files.getFirst();
    }

    private void requireOwnedKnowledgeBase(UUID ownerId, UUID knowledgeBaseId) {
        Integer count = jdbc.queryForObject("""
                SELECT count(*) FROM knowflow.knowledge_bases
                 WHERE id = ? AND owner_user_id = ? AND status = 'ACTIVE'
                """, Integer.class, knowledgeBaseId, ownerId);
        if (count == null || count != 1) {
            throw ApiFailure.resourceNotFound();
        }
    }

    private void lockOwnedKnowledgeBase(UUID ownerId, UUID knowledgeBaseId) {
        List<UUID> rows = jdbc.query("""
                SELECT id FROM knowflow.knowledge_bases
                 WHERE id = ? AND owner_user_id = ? AND status = 'ACTIVE'
                 FOR UPDATE
                """, (result, row) -> result.getObject(1, UUID.class), knowledgeBaseId, ownerId);
        if (rows.isEmpty()) {
            throw ApiFailure.resourceNotFound();
        }
    }

    private void compensateUpload(String objectKey) {
        try {
            objectStore.deleteObject(objectKey);
        } catch (ObjectStoreException storageFailure) {
            try {
                transactions.executeWithoutResult(status -> jdbc.update("""
                        INSERT INTO knowflow.storage_cleanup_queue (id, object_key)
                        VALUES (?, ?)
                        ON CONFLICT (object_key) DO NOTHING
                        """, UUID.randomUUID(), objectKey));
            } catch (RuntimeException cleanupQueueFailure) {
                storageFailure.addSuppressed(cleanupQueueFailure);
                LOGGER.warn("Upload compensation failed and durable cleanup could not be queued");
            }
        }
    }

    private static String safeOriginalName(String originalName) {
        if (originalName == null || originalName.isBlank()) {
            throw ApiFailure.unsupportedContent();
        }
        String normalizedSeparators = originalName.replace('\\', '/');
        String name = normalizedSeparators.substring(normalizedSeparators.lastIndexOf('/') + 1).strip();
        int codePoints = name.codePointCount(0, name.length());
        if (name.isEmpty() || codePoints > 512
                || name.codePoints().anyMatch(Character::isISOControl)) {
            throw ApiFailure.unsupportedContent();
        }
        return name;
    }

    private static DocumentResponse mapDocument(java.sql.ResultSet result, int row)
            throws java.sql.SQLException {
        return new DocumentResponse(
                ApiError.CONTRACT_VERSION,
                result.getObject("id", UUID.class),
                result.getObject("knowledge_base_id", UUID.class),
                result.getString("original_name"),
                result.getString("public_status"),
                result.getString("source_format").toLowerCase(Locale.ROOT),
                result.getLong("byte_size"),
                result.getString("source_sha256"),
                result.getObject("active_index_version_id", UUID.class),
                result.getObject("created_at", java.time.OffsetDateTime.class),
                result.getObject("updated_at", java.time.OffsetDateTime.class));
    }

    private static String sha256(byte[] contents) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(contents));
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException("SHA-256 is unavailable", impossible);
        }
    }

    public record FileContent(String originalName, String format, String sha256, byte[] contents) {}

    private record FileReference(String originalName, String objectKey, String format,
                                 String sha256, long byteSize) {}
}
