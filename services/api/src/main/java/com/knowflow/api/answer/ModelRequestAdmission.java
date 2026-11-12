package com.knowflow.api.answer;

import com.knowflow.api.config.QuestionProperties;
import com.knowflow.api.error.ApiFailure;
import org.springframework.stereotype.Component;

/** Immediate per-process admission shared by questions and save-time probes. */
@Component
public final class ModelRequestAdmission {
    private final int totalLimit;
    private final int customLimit;
    private int active;
    private int customActive;

    public ModelRequestAdmission(QuestionProperties properties) {
        properties.validateIsolation();
        totalLimit = properties.getMaxConcurrentRequests();
        customLimit = Math.min(properties.getCustomMaxConcurrentRequests(), totalLimit - 1);
    }

    public synchronized Lease tryAcquire(boolean custom) {
        if (active >= totalLimit) throw ApiFailure.aiProcessingFailed();
        if (custom && customActive >= customLimit) throw ApiFailure.modelBusy();
        active++;
        if (custom) customActive++;
        return new Lease(custom);
    }

    public final class Lease implements AutoCloseable {
        private final boolean custom;
        private boolean closed;

        private Lease(boolean custom) { this.custom = custom; }

        @Override public void close() {
            synchronized (ModelRequestAdmission.this) {
                if (closed) return;
                closed = true;
                active--;
                if (custom) customActive--;
            }
        }
    }
}
