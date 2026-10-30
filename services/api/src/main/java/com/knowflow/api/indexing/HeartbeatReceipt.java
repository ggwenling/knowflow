package com.knowflow.api.indexing;

import java.time.OffsetDateTime;
import java.util.UUID;

public record HeartbeatReceipt(String contractVersion, String requestId, UUID taskId,
                               OffsetDateTime leaseExpiresAt) {}
