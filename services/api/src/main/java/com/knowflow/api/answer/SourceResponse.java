package com.knowflow.api.answer;

import java.util.UUID;

public record SourceResponse(String contractVersion, UUID sourceId, UUID documentId,
                             UUID contentVersionId, UUID indexVersionId, UUID chunkId,
                             Locator locator, String quote) {
    public record Locator(String kind, Integer page, Integer start, Integer end,
                          String unit) {}
}
