package com.knowflow.api.storage;

public interface ObjectStore {
    void ensureBucket();

    void putObject(String key, String contentType, byte[] contents);

    byte[] getObject(String key, int maximumBytes);

    void deleteObject(String key);
}
