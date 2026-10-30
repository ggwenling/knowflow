package com.knowflow.api.error;

import org.springframework.http.HttpStatus;

public final class ApiFailure extends RuntimeException {
    private static final long serialVersionUID = 1L;

    private final HttpStatus status;
    private final String code;

    public ApiFailure(HttpStatus status, String code, String safeMessage) {
        super(safeMessage);
        this.status = status;
        this.code = code;
    }

    public HttpStatus status() {
        return status;
    }

    public String code() {
        return code;
    }

    public static ApiFailure invalidRequest() {
        return new ApiFailure(HttpStatus.BAD_REQUEST, "INVALID_REQUEST",
                "The request is invalid.");
    }

    public static ApiFailure unauthenticated() {
        return new ApiFailure(HttpStatus.UNAUTHORIZED, "UNAUTHENTICATED",
                "Authentication is required.");
    }

    public static ApiFailure accountCreateRejected() {
        return new ApiFailure(HttpStatus.CONFLICT, "ACCOUNT_CREATE_REJECTED",
                "The account could not be created.");
    }

    public static ApiFailure resourceNotFound() {
        return new ApiFailure(HttpStatus.NOT_FOUND, "RESOURCE_NOT_FOUND",
                "The requested resource is not available.");
    }
}
