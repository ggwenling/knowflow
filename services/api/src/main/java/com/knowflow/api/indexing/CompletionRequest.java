package com.knowflow.api.indexing;

public record CompletionRequest(String contractVersion, String requestId, LeaseContext lease,
                                String outcome, Manifest manifest, Failure failure) {
    public record Manifest(Integer chunkCount, Integer embeddingCount, Integer embeddingDimensions,
                           String embeddingModelProfileId, String manifestSha256) {}

    public record Failure(String code, String message, Boolean retryable) {}
}
