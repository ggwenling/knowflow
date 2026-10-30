package com.knowflow.api.answer;

import java.util.List;
import java.util.UUID;

public record TrustedAnswerRequest(String contractVersion, String requestId, String question,
                                   TrustedScope scope) {
    public record TrustedScope(UUID ownerId, UUID knowledgeBaseId, UUID snapshotId,
                               List<IndexScope> indexes) {}

    public record IndexScope(UUID documentId, UUID contentVersionId, UUID indexVersionId) {}
}
