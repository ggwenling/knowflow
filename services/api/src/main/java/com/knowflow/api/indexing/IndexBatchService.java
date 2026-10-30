package com.knowflow.api.indexing;

import java.math.BigDecimal;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;

import com.knowflow.api.error.ApiError;
import com.knowflow.api.error.ApiFailure;
import org.springframework.context.annotation.Profile;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
@Profile("database")
public class IndexBatchService {
    private final JdbcTemplate jdbc;
    private final TransactionTemplate transactions;
    private final LeaseAuthorizer leases;

    public IndexBatchService(JdbcTemplate jdbc, TransactionTemplate transactions,
                             LeaseAuthorizer leases) {
        this.jdbc = jdbc;
        this.transactions = transactions;
        this.leases = leases;
    }

    public IndexBatchReceipt write(UUID routeTaskId, IndexBatchRequest request) {
        if (request == null || !ApiError.CONTRACT_VERSION.equals(request.contractVersion())
                || request.requestId() == null || !isIdentifier(request.requestId())
                || request.lease() == null || !routeTaskId.equals(request.lease().taskId())) {
            throw ApiFailure.invalidRequest();
        }
        IndexBatchDigest.ValidatedBatch validated = IndexBatchDigest.validateAndDigest(request);
        try {
            IndexBatchReceipt receipt = transactions.execute(status -> {
                LeaseAuthorizer.AuthorizedExecution execution =
                        leases.lockAndVerify(routeTaskId, request.lease());
                List<StoredReceipt> existing = jdbc.query("""
                        SELECT index_version_id, batch_sequence, batch_sha256, chunk_count
                          FROM knowflow.index_batch_receipts
                         WHERE task_id = ? AND lease_id = ? AND fencing = ? AND batch_id = ?
                        """, (result, row) -> new StoredReceipt(
                        result.getObject("index_version_id", UUID.class),
                        result.getInt("batch_sequence"), result.getString("batch_sha256"),
                        result.getInt("chunk_count")), execution.taskId(), execution.leaseId(),
                        execution.fencing(), request.batchId());
                if (!existing.isEmpty()) {
                    StoredReceipt prior = existing.getFirst();
                    if (prior.indexVersionId().equals(execution.indexVersionId())
                            && prior.batchSequence() == request.batchSequence()
                            && prior.batchSha256().equals(validated.sha256())
                            && prior.chunkCount() == request.chunks().size()) {
                        return response(request, execution, "ALREADY_ACCEPTED");
                    }
                    throw ApiFailure.batchConflict();
                }

                Integer nextBatchSequence = jdbc.queryForObject("""
                        SELECT COALESCE(MAX(batch_sequence), 0) + 1
                          FROM knowflow.index_batch_receipts WHERE index_version_id = ?
                        """, Integer.class, execution.indexVersionId());
                Integer lastChunkSequence = jdbc.queryForObject("""
                        SELECT COALESCE(MAX(sequence_no), 0)
                          FROM knowflow.chunks WHERE index_version_id = ?
                        """, Integer.class, execution.indexVersionId());
                if (nextBatchSequence == null || nextBatchSequence != request.batchSequence()
                        || lastChunkSequence == null
                        || request.chunks().getFirst().sequenceNo() != lastChunkSequence + 1) {
                    throw ApiFailure.batchConflict();
                }

                Set<UUID> chunkIds = new HashSet<>();
                for (int index = 0; index < request.chunks().size(); index++) {
                    IndexBatchRequest.Chunk chunk = request.chunks().get(index);
                    if (!chunkIds.add(chunk.chunkId())
                            || chunk.sequenceNo() != lastChunkSequence + index + 1) {
                        throw ApiFailure.batchConflict();
                    }
                    insertChunk(execution, chunk,
                            validated.normalizedEmbeddings().get(index));
                }
                jdbc.update("""
                        INSERT INTO knowflow.index_batch_receipts
                            (task_id, index_version_id, lease_id, fencing, batch_id,
                             batch_sequence, batch_sha256, chunk_count)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, execution.taskId(), execution.indexVersionId(), execution.leaseId(),
                        execution.fencing(), request.batchId(), request.batchSequence(),
                        validated.sha256(), request.chunks().size());
                return response(request, execution, "ACCEPTED");
            });
            if (receipt == null) {
                throw new IllegalStateException("Index batch transaction did not return a receipt");
            }
            return receipt;
        } catch (DataIntegrityViolationException duplicateOrInvalidWrite) {
            throw ApiFailure.batchConflict();
        }
    }

    private void insertChunk(LeaseAuthorizer.AuthorizedExecution execution,
                             IndexBatchRequest.Chunk chunk, List<BigDecimal> embedding) {
        IndexBatchRequest.Locator locator = chunk.locator();
        String kind = locator.kind();
        jdbc.update("""
                INSERT INTO knowflow.chunks
                    (id, index_version_id, document_id, content_version_id, sequence_no,
                     text_content, text_sha256, locator_kind, source_page, source_start, source_end)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, chunk.chunkId(), execution.indexVersionId(), execution.documentId(),
                execution.contentVersionId(), chunk.sequenceNo(), chunk.text(), chunk.textSha256(),
                kind, locator.page(), locator.start(), locator.end());
        jdbc.update("""
                INSERT INTO knowflow.chunk_embeddings
                    (chunk_id, index_version_id, document_id, content_version_id,
                     embedding_model_profile_id, embedding)
                VALUES (?, ?, ?, ?, ?, ?::public.vector)
                """, chunk.chunkId(), execution.indexVersionId(), execution.documentId(),
                execution.contentVersionId(), execution.embeddingModelProfileId(), vector(embedding));
    }

    private static String vector(List<BigDecimal> values) {
        StringBuilder output = new StringBuilder(values.size() * 10 + 2).append('[');
        for (int index = 0; index < values.size(); index++) {
            if (index > 0) {
                output.append(',');
            }
            output.append(values.get(index).toPlainString());
        }
        return output.append(']').toString();
    }

    private static IndexBatchReceipt response(IndexBatchRequest request,
            LeaseAuthorizer.AuthorizedExecution execution, String result) {
        return new IndexBatchReceipt(ApiError.CONTRACT_VERSION, request.requestId(),
                execution.taskId(), execution.indexVersionId(), request.batchId(),
                request.batchSha256(), result, request.chunks().size());
    }

    private static boolean isIdentifier(String value) {
        if (value.length() < 1 || value.length() > 128 || !isAsciiAlphaNumeric(value.charAt(0))) {
            return false;
        }
        for (int index = 1; index < value.length(); index++) {
            char character = value.charAt(index);
            if (!(isAsciiAlphaNumeric(character) || character == '.' || character == '_'
                    || character == ':' || character == '-')) {
                return false;
            }
        }
        return true;
    }

    private static boolean isAsciiAlphaNumeric(char character) {
        return character >= 'A' && character <= 'Z' || character >= 'a' && character <= 'z'
                || character >= '0' && character <= '9';
    }

    private record StoredReceipt(UUID indexVersionId, int batchSequence, String batchSha256,
                                 int chunkCount) {}
}
