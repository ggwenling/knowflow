package com.knowflow.api.auth;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record LoginRequest(
        @NotBlank String contractVersion,
        @NotBlank @Email @Size(max = 320) String email,
        @NotBlank @Size(max = 128) String password) {
}
