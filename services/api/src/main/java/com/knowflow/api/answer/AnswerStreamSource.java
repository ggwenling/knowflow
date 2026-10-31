package com.knowflow.api.answer;

import java.util.UUID;

public record AnswerStreamSource(UUID sourceId, UUID documentId, UUID contentVersionId,
                                 UUID indexVersionId, UUID chunkId,
                                 SourceResponse.Locator locator, String quote) {}
