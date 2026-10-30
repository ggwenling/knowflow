package com.knowflow.api.indexing;

public record HeartbeatRequest(String contractVersion, String requestId, LeaseContext lease) {}
