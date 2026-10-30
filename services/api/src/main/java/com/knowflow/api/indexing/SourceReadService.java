package com.knowflow.api.indexing;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.UUID;
import java.util.regex.Pattern;

import com.knowflow.api.error.ApiError;
import com.knowflow.api.error.ApiFailure;
import com.knowflow.api.storage.ObjectStoreException;
import com.knowflow.api.storage.ObjectStore;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
@Profile("database & storage")
public class SourceReadService {
    private static final Pattern REQUEST_ID = Pattern.compile(
            "[A-Za-z0-9][A-Za-z0-9._:-]{0,127}");
    private final LeaseAuthorizer leases;
    private final ObjectStore objects;
    private final TransactionTemplate transactions;

    public SourceReadService(LeaseAuthorizer leases, ObjectStore objects,
                             TransactionTemplate transactions) {
        this.leases = leases;
        this.objects = objects;
        this.transactions = transactions;
    }

    public SourceFile read(UUID taskId, SourceReadRequest request) {
        if (request == null || !ApiError.CONTRACT_VERSION.equals(request.contractVersion())
                || request.requestId() == null || request.requestId().isBlank()
                || !REQUEST_ID.matcher(request.requestId()).matches()) {
            throw ApiFailure.invalidRequest();
        }
        LeaseAuthorizer.AuthorizedExecution execution = transactions.execute(status ->
                leases.lockAndVerify(taskId, request.lease()));
        if (execution == null) {
            throw new IllegalStateException("Source read did not complete");
        }
        byte[] contents = objects.getObject(execution.objectKey(), 8 * 1024 * 1024);
        if (contents.length != execution.byteSize()
                || !sha256(contents).equals(execution.sourceSha256())) {
            throw new ObjectStoreException("Stored source failed integrity verification");
        }

        transactions.executeWithoutResult(status -> {
            LeaseAuthorizer.AuthorizedExecution current =
                    leases.lockAndVerify(taskId, request.lease());
            if (!execution.equals(current)) {
                throw ApiFailure.leaseRejected();
            }
        });
        return new SourceFile(ApiError.CONTRACT_VERSION, request.requestId(), execution.taskId(),
                execution.documentId(), execution.contentVersionId(), execution.sourceFormat(),
                execution.sourceSha256(), contents);
    }

    private static String sha256(byte[] bytes) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException("SHA-256 is unavailable", impossible);
        }
    }

    public record SourceFile(String contractVersion, String requestId, UUID taskId,
                             UUID documentId, UUID contentVersionId, String format,
                             String sha256, byte[] contents) {}
}
