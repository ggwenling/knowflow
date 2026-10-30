package com.knowflow.api.config;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "knowflow.storage")
public class ObjectStorageProperties {
    private URI endpoint;
    private String bucket;
    private String accessKey;
    private String secretKey;
    private Duration requestTimeout = Duration.ofSeconds(10);

    public URI getEndpoint() { return endpoint; }
    public void setEndpoint(URI endpoint) { this.endpoint = endpoint; }
    public String getBucket() { return bucket; }
    public void setBucket(String bucket) { this.bucket = bucket; }
    public String getAccessKey() { return accessKey; }
    public void setAccessKey(String accessKey) { this.accessKey = accessKey; }
    public String getSecretKey() { return secretKey; }
    public void setSecretKey(String secretKey) { this.secretKey = secretKey; }
    public Duration getRequestTimeout() { return requestTimeout; }
    public void setRequestTimeout(Duration requestTimeout) { this.requestTimeout = requestTimeout; }

    public void requireValid() {
        if (endpoint == null || bucket == null || accessKey == null || secretKey == null) {
            throw new IllegalStateException("Object storage configuration is incomplete");
        }
        if (requestTimeout == null || requestTimeout.isNegative() || requestTimeout.isZero()
                || requestTimeout.compareTo(Duration.ofMinutes(2)) > 0) {
            throw new IllegalStateException("Object storage request timeout is invalid");
        }
    }
}
