package com.knowflow.api.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "knowflow.indexing")
public class IndexingProperties {
    private int leaseSeconds = 60;
    private int heartbeatSeconds = 15;
    private int maxAttempts = 3;
    private int pollDelayMillis = 1_000;
    private int maxBatchChunks = 32;
    private int maxBatchBytes = 1_048_576;
    private String runtimeProfileId = "runtime-default";
    private boolean schedulerEnabled;

    public IndexingProperties() {}

    public int getLeaseSeconds() { return leaseSeconds; }
    public void setLeaseSeconds(int value) { leaseSeconds = value; }
    public int getHeartbeatSeconds() { return heartbeatSeconds; }
    public void setHeartbeatSeconds(int value) { heartbeatSeconds = value; }
    public int getMaxAttempts() { return maxAttempts; }
    public void setMaxAttempts(int value) { maxAttempts = value; }
    public int getPollDelayMillis() { return pollDelayMillis; }
    public void setPollDelayMillis(int value) { pollDelayMillis = value; }
    public int getMaxBatchChunks() { return maxBatchChunks; }
    public void setMaxBatchChunks(int value) { maxBatchChunks = value; }
    public int getMaxBatchBytes() { return maxBatchBytes; }
    public void setMaxBatchBytes(int value) { maxBatchBytes = value; }
    public String getRuntimeProfileId() { return runtimeProfileId; }
    public void setRuntimeProfileId(String value) { runtimeProfileId = value; }
    public boolean isSchedulerEnabled() { return schedulerEnabled; }
    public void setSchedulerEnabled(boolean value) { schedulerEnabled = value; }

    public void requireValid() {
        if (leaseSeconds < 5 || leaseSeconds > 600 || heartbeatSeconds < 1
                || heartbeatSeconds >= leaseSeconds || maxAttempts < 1 || maxAttempts > 3
                || pollDelayMillis < 100 || pollDelayMillis > 60_000
                || maxBatchChunks < 1 || maxBatchChunks > 32
                || maxBatchBytes < 1 || maxBatchBytes > 1_048_576
                || runtimeProfileId == null || runtimeProfileId.isBlank()
                || runtimeProfileId.length() > 128) {
            throw new IllegalStateException("Indexing settings are invalid");
        }
    }
}
