package com.knowflow.api.indexing;

import java.util.UUID;

public record LeaseContext(
        UUID taskId,
        UUID ownerId,
        UUID knowledgeBaseId,
        UUID documentId,
        UUID contentVersionId,
        UUID indexVersionId,
        String pipelineProfileId,
        UUID leaseId,
        long fencing,
        String executionToken) {}
