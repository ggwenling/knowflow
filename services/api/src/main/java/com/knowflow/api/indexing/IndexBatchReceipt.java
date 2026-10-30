package com.knowflow.api.indexing;

import java.util.UUID;

public record IndexBatchReceipt(String contractVersion, String requestId, UUID taskId,
                                UUID indexVersionId, UUID batchId, String batchSha256,
                                String result, int chunkCount) {}
