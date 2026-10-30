package com.knowflow.api.indexing;

import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

public record IndexBatchRequest(String contractVersion, String requestId, LeaseContext lease,
                                UUID batchId, Integer batchSequence, String batchSha256,
                                List<Chunk> chunks) {
    public record Chunk(UUID chunkId, Integer sequenceNo, String text, String textSha256,
                        Locator locator, List<BigDecimal> embedding) {}

    public record Locator(String kind, Integer page, Integer start, Integer end, String unit) {}
}
