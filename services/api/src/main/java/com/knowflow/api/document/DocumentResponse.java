package com.knowflow.api.document;

import java.time.OffsetDateTime;
import java.util.UUID;

import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record DocumentResponse(
        String contractVersion,
        UUID id,
        UUID knowledgeBaseId,
        String originalName,
        String status,
        String format,
        long byteSize,
        String sourceSha256,
        UUID activeIndexVersionId,
        OffsetDateTime createdAt,
        OffsetDateTime updatedAt) {}
