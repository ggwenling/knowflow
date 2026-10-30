package com.knowflow.api.error;

import org.springframework.http.HttpStatus;

public final class ApiFailure extends RuntimeException {
    private static final long serialVersionUID = 1L;

    private final HttpStatus status;
    private final String code;
    private final boolean retryable;

    public ApiFailure(HttpStatus status, String code, String safeMessage) {
        this(status, code, safeMessage, false);
    }

    public ApiFailure(HttpStatus status, String code, String safeMessage, boolean retryable) {
        super(safeMessage);
        this.status = status;
        this.code = code;
        this.retryable = retryable;
    }

    public HttpStatus status() {
        return status;
    }

    public String code() {
        return code;
    }

    public boolean retryable() {
        return retryable;
    }

    public static ApiFailure invalidRequest() {
        return new ApiFailure(HttpStatus.BAD_REQUEST, "INVALID_REQUEST",
                "The request is invalid.");
    }

    public static ApiFailure unauthenticated() {
        return new ApiFailure(HttpStatus.UNAUTHORIZED, "UNAUTHENTICATED",
                "Authentication is required.");
    }

    public static ApiFailure accountCreateRejected() {
        return new ApiFailure(HttpStatus.CONFLICT, "ACCOUNT_CREATE_REJECTED",
                "The account could not be created.");
    }

    public static ApiFailure resourceNotFound() {
        return new ApiFailure(HttpStatus.NOT_FOUND, "RESOURCE_NOT_FOUND",
                "The requested resource is not available.");
    }

    public static ApiFailure unsupportedContent() {
        return new ApiFailure(HttpStatus.BAD_REQUEST, "UNSUPPORTED_CONTENT",
                "The uploaded file is not supported.");
    }

    public static ApiFailure resourceLimit() {
        return new ApiFailure(HttpStatus.PAYLOAD_TOO_LARGE, "RESOURCE_LIMIT",
                "The uploaded file exceeds a configured limit.");
    }

    public static ApiFailure storageUnavailable() {
        return new ApiFailure(HttpStatus.SERVICE_UNAVAILABLE, "STORAGE_UNAVAILABLE",
                "File storage is temporarily unavailable.", true);
    }

    public static ApiFailure leaseRejected() {
        return new ApiFailure(HttpStatus.CONFLICT, "LEASE_REJECTED",
                "The execution lease is no longer valid.");
    }

    public static ApiFailure documentUnavailable() {
        return new ApiFailure(HttpStatus.CONFLICT, "DOCUMENT_UNAVAILABLE",
                "The document is no longer available for this execution.");
    }

    public static ApiFailure batchConflict() {
        return new ApiFailure(HttpStatus.CONFLICT, "BATCH_CONFLICT",
                "The index batch conflicts with an accepted batch.");
    }

    public static ApiFailure completionConflict() {
        return new ApiFailure(HttpStatus.CONFLICT, "COMPLETION_CONFLICT",
                "The task already has a different completion result.");
    }

    public static ApiFailure knowledgeBaseNotReady() {
        return new ApiFailure(HttpStatus.CONFLICT, "KNOWLEDGE_BASE_NOT_READY",
                "The knowledge base has no available indexed documents.");
    }

    public static ApiFailure scopeLimit() {
        return new ApiFailure(HttpStatus.PAYLOAD_TOO_LARGE, "RESOURCE_LIMIT",
                "The knowledge base exceeds the configured answer scope limit.");
    }

    public static ApiFailure aiProcessingFailed() {
        return new ApiFailure(HttpStatus.BAD_GATEWAY, "AI_PROCESSING_FAILED",
                "The AI service could not complete the request.", true);
    }

    public static ApiFailure processingTimeout() {
        return new ApiFailure(HttpStatus.GATEWAY_TIMEOUT, "PROCESSING_TIMEOUT",
                "The AI service did not complete the request in time.", true);
    }
}
