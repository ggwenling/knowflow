package com.knowflow.api.answer;

import java.util.UUID;

public record QuestionHistorySource(UUID sourceId, UUID documentId,
                                    UUID contentVersionId, UUID indexVersionId,
                                    UUID chunkId, String state,
                                    SourceResponse.Locator locator, String quote) {}
