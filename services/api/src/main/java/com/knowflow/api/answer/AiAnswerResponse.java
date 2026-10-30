package com.knowflow.api.answer;

import java.util.List;
import java.util.UUID;

public record AiAnswerResponse(String contractVersion, String requestId, String answer,
                               Boolean hasAnswer, List<AiSource> sources) {
    public record AiSource(String sourceId, UUID documentId, UUID contentVersionId,
                           UUID indexVersionId, UUID chunkId, Locator locator, String quote) {}

    public record Locator(String kind, Integer page, Integer start, Integer end, String unit) {}
}
