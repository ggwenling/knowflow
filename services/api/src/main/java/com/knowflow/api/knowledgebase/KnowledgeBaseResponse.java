package com.knowflow.api.knowledgebase;

import java.time.OffsetDateTime;
import java.util.UUID;

public record KnowledgeBaseResponse(
        String contractVersion,
        UUID id,
        String name,
        String status,
        OffsetDateTime createdAt,
        OffsetDateTime updatedAt) {
}
