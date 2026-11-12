package com.knowflow.api.config;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "knowflow.questions")
public class QuestionProperties {
    @Min(1)
    @Max(30)
    private int totalBudgetSeconds = 30;

    @Min(1)
    @Max(32)
    private int maxConcurrentRequests = 4;

    @Min(1)
    @Max(32)
    private int customMaxConcurrentRequests = 2;
    private boolean customEnabled;

    public int getCustomMaxConcurrentRequests() { return customMaxConcurrentRequests; }
    public void setCustomMaxConcurrentRequests(int value) { customMaxConcurrentRequests = value; }
    public boolean isCustomEnabled() { return customEnabled; }
    public void setCustomEnabled(boolean value) { customEnabled = value; }

    @jakarta.validation.constraints.AssertTrue(message = "LLM_ISOLATION_CONFIGURATION_INVALID")
    public boolean isIsolationValid() { return !customEnabled || maxConcurrentRequests >= 2; }

    public void validateIsolation() {
        if (!isIsolationValid()) throw new IllegalStateException("LLM_ISOLATION_CONFIGURATION_INVALID");
    }

    public int getTotalBudgetSeconds() {
        return totalBudgetSeconds;
    }

    public void setTotalBudgetSeconds(int value) {
        totalBudgetSeconds = value;
    }

    public int getMaxConcurrentRequests() {
        return maxConcurrentRequests;
    }

    public void setMaxConcurrentRequests(int value) {
        maxConcurrentRequests = value;
    }
}
