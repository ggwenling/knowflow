package com.knowflow.api.indexing;

import java.util.UUID;

public record CompletionReceipt(String contractVersion, String requestId, UUID taskId,
                                UUID indexVersionId, String result) {}
