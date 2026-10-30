package com.knowflow.api.indexing;

public record SourceReadRequest(String contractVersion, String requestId, LeaseContext lease) {}
