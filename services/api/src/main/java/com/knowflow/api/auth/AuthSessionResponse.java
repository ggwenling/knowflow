package com.knowflow.api.auth;

import java.time.OffsetDateTime;
import java.util.UUID;

public record AuthSessionResponse(
        String contractVersion,
        UUID userId,
        String email,
        String accessToken,
        String tokenType,
        OffsetDateTime expiresAt) {
}
