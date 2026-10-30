package com.knowflow.api.indexing;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Pattern;

import com.knowflow.api.auth.AuthService;
import com.knowflow.api.error.ApiError;
import com.knowflow.api.error.ApiFailure;
import com.knowflow.api.config.IndexingProperties;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
@Profile("database")
public class CompletionService {
    private static final Pattern SHA256 = Pattern.compile("[a-f0-9]{64}");
    private static final Pattern REQUEST_ID = Pattern.compile("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}");
    private static final Set<String> FAILURE_CODES = Set.of("UNSUPPORTED_CONTENT", "EMPTY_CONTENT",
            "RESOURCE_LIMIT", "MODEL_TIMEOUT", "MODEL_FAILURE", "INDEX_WRITE_FAILED",
            "EXECUTION_CANCELLED", "WORKER_LOST");
    private static final List<Integer> BACKOFF_SECONDS = List.of(5, 30);

    private final JdbcTemplate jdbc;
    private final TransactionTemplate transactions;
    private final LeaseAuthorizer leases;
    private final IndexingProperties properties;

    public CompletionService(JdbcTemplate jdbc, TransactionTemplate transactions,
                             LeaseAuthorizer leases, IndexingProperties properties) {
        this.jdbc = jdbc;
        this.transactions = transactions;
        this.leases = leases;
        this.properties = properties;
    }

    public CompletionReceipt complete(UUID routeTaskId, CompletionRequest request) {
        validateRequest(routeTaskId, request);
        String resultHash = completionHash(request);
        CompletionReceipt receipt = transactions.execute(status -> {
            LockedTask locked = lockTaskAndDocument(routeTaskId);
            if (locked == null) {
                throw ApiFailure.leaseRejected();
            }
            if (!"ACTIVE".equals(locked.documentStatus())
                    || !"ACTIVE".equals(locked.knowledgeBaseStatus())) {
                throw ApiFailure.documentUnavailable();
            }
            String suppliedTokenHash = AuthService.sha256(request.lease().executionToken());
            if (locked.acceptedLeaseId() != null) {
                if (sameAcceptedExecution(locked, request.lease(), suppliedTokenHash)) {
                    if (resultHash.equals(locked.acceptedCompletionSha256())) {
                        return response(request, locked.indexVersionId(), "ALREADY_ACCEPTED");
                    }
                    throw ApiFailure.completionConflict();
                }
                throw ApiFailure.leaseRejected();
            }

            LeaseAuthorizer.AuthorizedExecution execution =
                    leases.lockAndVerify(routeTaskId, request.lease());
            return "SUCCEEDED".equals(request.outcome())
                    ? completeSuccessfully(request, resultHash, execution)
                    : completeAsFailure(request, resultHash, execution);
        });
        if (receipt == null) {
            throw new IllegalStateException("Completion transaction did not return a receipt");
        }
        return receipt;
    }

    private CompletionReceipt completeSuccessfully(CompletionRequest request, String resultHash,
            LeaseAuthorizer.AuthorizedExecution execution) {
        ActualCounts actual = jdbc.queryForObject("""
                SELECT COUNT(c.id)::integer AS chunk_count,
                       COUNT(e.chunk_id)::integer AS embedding_count,
                       COALESCE(MIN(c.sequence_no), 0)::integer AS minimum_sequence,
                       COALESCE(MAX(c.sequence_no), 0)::integer AS maximum_sequence,
                       COUNT(*) FILTER (WHERE e.chunk_id IS NULL)::integer AS missing_embeddings,
                       COUNT(*) FILTER (WHERE e.chunk_id IS NOT NULL
                           AND (vector_dims(e.embedding) <> 1024
                             OR e.embedding_model_profile_id <> ?))::integer AS invalid_embeddings
                  FROM knowflow.chunks c
                  LEFT JOIN knowflow.chunk_embeddings e ON e.chunk_id = c.id
                 WHERE c.index_version_id = ?
                """, (result, row) -> new ActualCounts(
                result.getInt("chunk_count"), result.getInt("embedding_count"),
                result.getInt("minimum_sequence"), result.getInt("maximum_sequence"),
                result.getInt("missing_embeddings"), result.getInt("invalid_embeddings")),
                execution.embeddingModelProfileId(), execution.indexVersionId());
        if (actual == null || actual.chunkCount() < 1
                || actual.embeddingCount() != actual.chunkCount()
                || actual.minimumSequence() != 1 || actual.maximumSequence() != actual.chunkCount()
                || actual.missingEmbeddings() != 0 || actual.invalidEmbeddings() != 0) {
            throw ApiFailure.invalidRequest();
        }

        List<IndexManifestDigest.BatchIdentity> batches = jdbc.query("""
                SELECT batch_sequence, batch_id, batch_sha256, chunk_count
                  FROM knowflow.index_batch_receipts
                 WHERE task_id = ? AND index_version_id = ? AND lease_id = ? AND fencing = ?
                 ORDER BY batch_sequence
                """, (result, row) -> new IndexManifestDigest.BatchIdentity(
                result.getInt("batch_sequence"), result.getObject("batch_id", UUID.class),
                result.getString("batch_sha256"), result.getInt("chunk_count")),
                execution.taskId(), execution.indexVersionId(), execution.leaseId(),
                execution.fencing());
        int receiptChunks = 0;
        for (int index = 0; index < batches.size(); index++) {
            IndexManifestDigest.BatchIdentity batch = batches.get(index);
            if (batch.sequence() != index + 1) {
                throw ApiFailure.invalidRequest();
            }
            receiptChunks += batch.chunkCount();
        }
        if (batches.isEmpty() || receiptChunks != actual.chunkCount()) {
            throw ApiFailure.invalidRequest();
        }

        CompletionRequest.Manifest manifest = request.manifest();
        String manifestHash = IndexManifestDigest.calculate(new IndexManifestDigest.ManifestIdentity(
                        execution.taskId(), execution.ownerId(), execution.knowledgeBaseId(),
                        execution.documentId(), execution.contentVersionId(),
                        execution.indexVersionId(), execution.pipelineProfileId(),
                        execution.embeddingModelProfileId(), 1024),
                actual.chunkCount(), actual.embeddingCount(), batches);
        if (manifest.chunkCount() != actual.chunkCount()
                || manifest.embeddingCount() != actual.embeddingCount()
                || manifest.embeddingDimensions() != 1024
                || !execution.embeddingModelProfileId().equals(manifest.embeddingModelProfileId())
                || !manifestHash.equals(manifest.manifestSha256())) {
            throw ApiFailure.invalidRequest();
        }

        int updatedIndex = jdbc.update("""
                UPDATE knowflow.index_versions
                   SET status = 'READY', chunk_count = ?, embedding_count = ?,
                       manifest_sha256 = ?, ready_at = CURRENT_TIMESTAMP, failure_code = NULL
                 WHERE id = ? AND status = 'BUILDING'
                """, actual.chunkCount(), actual.embeddingCount(), manifestHash,
                execution.indexVersionId());
        if (updatedIndex != 1) {
            throw ApiFailure.leaseRejected();
        }
        UUID previousActive = jdbc.queryForObject("""
                SELECT active_index_version_id FROM knowflow.documents WHERE id = ?
                """, UUID.class, execution.documentId());
        int updatedDocument = jdbc.update("""
                UPDATE knowflow.documents
                   SET active_index_version_id = ?, updated_at = CURRENT_TIMESTAMP
                 WHERE id = ? AND status = 'ACTIVE'
                   AND current_content_version_id = ?
                """, execution.indexVersionId(), execution.documentId(),
                execution.contentVersionId());
        if (updatedDocument != 1) {
            throw ApiFailure.documentUnavailable();
        }
        if (previousActive != null) {
            jdbc.update("""
                    UPDATE knowflow.index_versions SET status = 'RETIRED'
                     WHERE id = ? AND document_id = ? AND status = 'READY'
                    """, previousActive, execution.documentId());
        }
        acceptCompletion(request, execution, resultHash, "SUCCEEDED", null, false, 0);
        return response(request, execution.indexVersionId(), "ACCEPTED");
    }

    private CompletionReceipt completeAsFailure(CompletionRequest request, String resultHash,
            LeaseAuthorizer.AuthorizedExecution execution) {
        CompletionRequest.Failure failure = request.failure();
        jdbc.update("""
                UPDATE knowflow.index_versions
                   SET status = 'FAILED', failure_code = ?
                 WHERE id = ? AND status = 'BUILDING'
                """, failure.code(), execution.indexVersionId());
        boolean retry = failure.retryable() && requestAttemptCount(execution.taskId())
                < properties.getMaxAttempts();
        int backoff = retry ? BACKOFF_SECONDS.get(Math.min(requestAttemptCount(execution.taskId()) - 1,
                BACKOFF_SECONDS.size() - 1)) : 0;
        acceptCompletion(request, execution, resultHash, retry ? "QUEUED" : "FAILED",
                retry ? null : failure.code(), retry, backoff);
        return response(request, execution.indexVersionId(), "ACCEPTED");
    }

    private void acceptCompletion(CompletionRequest request,
            LeaseAuthorizer.AuthorizedExecution execution, String resultHash,
            String taskStatus, String failureCode, boolean retry, int backoffSeconds) {
        int updatedTask = jdbc.update("""
                UPDATE knowflow.indexing_tasks
                   SET status = ?, failure_code = ?,
                       lease_id = NULL, lease_expires_at = NULL, execution_token_hash = NULL,
                       accepted_lease_id = ?, accepted_fencing = ?,
                       accepted_execution_token_hash = ?, accepted_completion_sha256 = ?,
                       available_at = CASE WHEN ? THEN
                           clock_timestamp() + (? * INTERVAL '1 second') ELSE available_at END,
                       finished_at = CASE WHEN ? THEN NULL ELSE CURRENT_TIMESTAMP END,
                       last_request_id = ?, updated_at = CURRENT_TIMESTAMP
                 WHERE id = ? AND status = 'RUNNING'
                """, taskStatus, failureCode, execution.leaseId(), execution.fencing(),
                AuthService.sha256(request.lease().executionToken()), resultHash, retry, backoffSeconds,
                retry, request.requestId(), execution.taskId());
        if (updatedTask != 1) {
            throw ApiFailure.leaseRejected();
        }
    }

    private int requestAttemptCount(UUID taskId) {
        Integer attempt = jdbc.queryForObject("""
                SELECT attempt_count FROM knowflow.indexing_tasks WHERE id = ?
                """, Integer.class, taskId);
        if (attempt == null || attempt < 1) {
            throw ApiFailure.leaseRejected();
        }
        return attempt;
    }

    private LockedTask lockTaskAndDocument(UUID taskId) {
        List<LockedTask> rows = jdbc.query("""
                SELECT d.status AS document_status, kb.status AS knowledge_base_status,
                       t.id, t.owner_user_id, t.knowledge_base_id, t.document_id,
                       t.content_version_id, t.index_version_id, t.accepted_lease_id,
                       t.accepted_fencing,
                       t.accepted_execution_token_hash, t.accepted_completion_sha256
                  FROM knowflow.documents d
                  JOIN knowflow.indexing_tasks t ON t.document_id = d.id
                  JOIN knowflow.knowledge_bases kb
                    ON kb.id = d.knowledge_base_id AND kb.owner_user_id = d.owner_user_id
                 WHERE t.id = ?
                 FOR UPDATE OF d
                """, (result, row) -> new LockedTask(
                result.getString("document_status"), result.getString("knowledge_base_status"),
                result.getObject("id", UUID.class),
                result.getObject("owner_user_id", UUID.class),
                result.getObject("knowledge_base_id", UUID.class),
                result.getObject("document_id", UUID.class),
                result.getObject("content_version_id", UUID.class),
                result.getObject("index_version_id", UUID.class),
                result.getObject("accepted_lease_id", UUID.class),
                result.getObject("accepted_fencing", Long.class),
                result.getString("accepted_execution_token_hash"),
                result.getString("accepted_completion_sha256")), taskId);
        if (rows.isEmpty()) {
            return null;
        }
        LockedTask row = rows.getFirst();
        List<LockedTask> taskRows = jdbc.query("""
                SELECT id FROM knowflow.indexing_tasks WHERE id = ? FOR UPDATE
                """, (result, index) -> row, taskId);
        return taskRows.isEmpty() ? null : row;
    }

    private static boolean sameAcceptedExecution(LockedTask task, LeaseContext lease,
                                                 String tokenHash) {
        return task.id().equals(lease.taskId()) && task.ownerId().equals(lease.ownerId())
                && task.knowledgeBaseId().equals(lease.knowledgeBaseId())
                && task.documentId().equals(lease.documentId())
                && task.contentVersionId().equals(lease.contentVersionId())
                && task.indexVersionId().equals(lease.indexVersionId())
                && task.acceptedLeaseId().equals(lease.leaseId())
                && task.acceptedFencing() != null && task.acceptedFencing() == lease.fencing()
                && MessageDigest.isEqual(task.acceptedExecutionTokenHash()
                        .getBytes(StandardCharsets.US_ASCII), tokenHash.getBytes(StandardCharsets.US_ASCII));
    }

    private static void validateRequest(UUID routeTaskId, CompletionRequest request) {
        if (request == null || routeTaskId == null
                || !ApiError.CONTRACT_VERSION.equals(request.contractVersion())
                || request.requestId() == null || !REQUEST_ID.matcher(request.requestId()).matches()
                || request.lease() == null || !routeTaskId.equals(request.lease().taskId())
                || request.lease().executionToken() == null
                || request.outcome() == null
                || !Set.of("SUCCEEDED", "FAILED").contains(request.outcome())) {
            throw ApiFailure.invalidRequest();
        }
        if ("SUCCEEDED".equals(request.outcome())) {
            CompletionRequest.Manifest manifest = request.manifest();
            if (manifest == null || request.failure() != null || manifest.chunkCount() == null
                    || manifest.chunkCount() < 1 || manifest.embeddingCount() == null
                    || manifest.embeddingCount() < 1 || manifest.embeddingDimensions() == null
                    || manifest.embeddingDimensions() != 1024
                    || manifest.embeddingModelProfileId() == null
                    || manifest.embeddingModelProfileId().isBlank()
                    || manifest.manifestSha256() == null
                    || !SHA256.matcher(manifest.manifestSha256()).matches()) {
                throw ApiFailure.invalidRequest();
            }
        } else {
            CompletionRequest.Failure failure = request.failure();
            if (failure == null || request.manifest() != null || failure.code() == null
                    || !FAILURE_CODES.contains(failure.code()) || failure.message() == null
                    || failure.message().isBlank() || failure.message().length() > 512
                    || failure.retryable() == null) {
                throw ApiFailure.invalidRequest();
            }
        }
    }

    private static String completionHash(CompletionRequest request) {
        List<String> fields = new ArrayList<>();
        fields.add(request.outcome());
        if ("SUCCEEDED".equals(request.outcome())) {
            CompletionRequest.Manifest manifest = request.manifest();
            fields.add(manifest.chunkCount().toString());
            fields.add(manifest.embeddingCount().toString());
            fields.add(manifest.embeddingDimensions().toString());
            fields.add(manifest.embeddingModelProfileId());
            fields.add(manifest.manifestSha256());
        } else {
            CompletionRequest.Failure failure = request.failure();
            fields.add(failure.code());
            fields.add(failure.message());
            fields.add(failure.retryable().toString());
        }
        var output = new java.io.ByteArrayOutputStream();
        output.writeBytes("knowflow-completion-v1\n".getBytes(StandardCharsets.UTF_8));
        for (String field : fields) {
            byte[] bytes = field.getBytes(StandardCharsets.UTF_8);
            output.writeBytes(Integer.toString(bytes.length).getBytes(StandardCharsets.US_ASCII));
            output.write(':');
            output.writeBytes(bytes);
            output.write('\n');
        }
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(output.toByteArray()));
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException("SHA-256 is unavailable", impossible);
        }
    }

    private static CompletionReceipt response(CompletionRequest request, UUID indexVersionId,
                                              String result) {
        return new CompletionReceipt(ApiError.CONTRACT_VERSION, request.requestId(),
                request.lease().taskId(), indexVersionId, result);
    }

    private record LockedTask(String documentStatus, String knowledgeBaseStatus, UUID id,
                              UUID ownerId, UUID knowledgeBaseId, UUID documentId,
                              UUID contentVersionId, UUID indexVersionId, UUID acceptedLeaseId,
                              Long acceptedFencing,
                              String acceptedExecutionTokenHash, String acceptedCompletionSha256) {}

    private record ActualCounts(int chunkCount, int embeddingCount, int minimumSequence,
                                int maximumSequence, int missingEmbeddings,
                                int invalidEmbeddings) {}
}
