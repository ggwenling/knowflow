package com.knowflow.api.document;

import java.time.OffsetDateTime;
import java.util.UUID;

import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record TaskStatusResponse(
        String contractVersion,
        UUID taskId,
        UUID documentId,
        String status,
        int attemptCount,
        String failureCode,
        OffsetDateTime createdAt,
        OffsetDateTime updatedAt) {}
