package com.knowflow.api.indexing;

import java.util.UUID;

public record CancelExecution(String contractVersion, String requestId, UUID taskId,
                              UUID leaseId, long fencing) {}
