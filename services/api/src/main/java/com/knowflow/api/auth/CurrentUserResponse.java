package com.knowflow.api.auth;

import java.util.UUID;

public record CurrentUserResponse(String contractVersion, UUID userId, String email) {
}
