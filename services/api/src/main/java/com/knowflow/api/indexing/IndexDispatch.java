package com.knowflow.api.indexing;

import java.time.OffsetDateTime;
import java.util.UUID;

public record IndexDispatch(
        String contractVersion,
        String requestId,
        LeaseContext lease,
        OffsetDateTime leaseExpiresAt,
        SourceFile source,
        String runtimeProfileId,
        RuntimeProfile runtimeProfile) {
    public record SourceFile(UUID fileId, String sha256, String format) {}
    public record RuntimeProfile(String pipelineProfileId, int chunkMaxCodepoints,
                                 int overlapCodepoints, int embeddingMaxBatchItems,
                                 int indexMaxBatchChunks, int indexMaxBatchBytes) {}
}
