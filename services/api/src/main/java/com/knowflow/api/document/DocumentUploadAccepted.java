package com.knowflow.api.document;

import java.util.UUID;

public record DocumentUploadAccepted(
        String contractVersion,
        UUID documentId,
        UUID taskId,
        String status) {}
