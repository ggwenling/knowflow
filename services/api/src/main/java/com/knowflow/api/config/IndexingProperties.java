package com.knowflow.api.config;

import java.util.regex.Pattern;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "knowflow.indexing")
public class IndexingProperties {
    private static final Pattern PROFILE_ID =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}");
    private int leaseSeconds = 60;
    private int heartbeatSeconds = 15;
    private int maxAttempts = 3;
    private int pollDelayMillis = 1_000;
    private int maxBatchChunks = 32;
    private int maxBatchBytes = 1_048_576;
    private int chunkMaxCodepoints = 800;
    private int overlapCodepoints = 100;
    private int embeddingMaxBatchItems = 16;
    private String pipelineProfileId = "knowflow-index-v1";
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
    public int getChunkMaxCodepoints() { return chunkMaxCodepoints; }
    public void setChunkMaxCodepoints(int value) { chunkMaxCodepoints = value; }
    public int getOverlapCodepoints() { return overlapCodepoints; }
    public void setOverlapCodepoints(int value) { overlapCodepoints = value; }
    public int getEmbeddingMaxBatchItems() { return embeddingMaxBatchItems; }
    public void setEmbeddingMaxBatchItems(int value) { embeddingMaxBatchItems = value; }
    public String getPipelineProfileId() { return pipelineProfileId; }
    public void setPipelineProfileId(String value) { pipelineProfileId = value; }
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
                || chunkMaxCodepoints < 1 || chunkMaxCodepoints > 800
                || overlapCodepoints < 0 || overlapCodepoints >= chunkMaxCodepoints
                || embeddingMaxBatchItems < 1 || embeddingMaxBatchItems > 16
                || ("knowflow-index-v1".equals(pipelineProfileId)
                && (chunkMaxCodepoints != 800 || overlapCodepoints != 100))
                || !validProfileId(pipelineProfileId) || !validProfileId(runtimeProfileId)) {
            throw new IllegalStateException("Indexing settings are invalid");
        }
    }

    private static boolean validProfileId(String value) {
        return value != null && PROFILE_ID.matcher(value).matches();
    }
}
