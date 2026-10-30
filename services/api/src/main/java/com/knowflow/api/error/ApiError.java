package com.knowflow.api.error;

public record ApiError(
        String contract_version,
        String request_id,
        String code,
        String message,
        boolean retryable) {
    public static final String CONTRACT_VERSION = "0.2.0-draft.4";
}
