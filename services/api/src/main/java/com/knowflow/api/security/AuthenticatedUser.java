package com.knowflow.api.security;

import java.util.UUID;

public record AuthenticatedUser(UUID id, String email, String tokenSha256) {
}
