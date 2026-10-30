package com.knowflow.api.storage;

public final class ObjectStoreException extends RuntimeException {
    private static final long serialVersionUID = 1L;

    public ObjectStoreException(String message) {
        super(message);
    }

    public ObjectStoreException(String message, Throwable cause) {
        super(message, cause);
    }
}
