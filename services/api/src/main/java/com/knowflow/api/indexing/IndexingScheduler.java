package com.knowflow.api.indexing;

import com.knowflow.api.config.IndexingProperties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Profile;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@Profile("database")
@ConditionalOnProperty(prefix = "knowflow.indexing", name = "scheduler-enabled",
        havingValue = "true")
public class IndexingScheduler {
    private static final Logger LOGGER = LoggerFactory.getLogger(IndexingScheduler.class);
    private final IndexingTaskQueue queue;
    private final AiIndexExecutionClient client;

    public IndexingScheduler(IndexingTaskQueue queue, AiIndexExecutionClient client,
                             IndexingProperties properties) {
        properties.requireValid();
        this.queue = queue;
        this.client = client;
    }

    @Scheduled(fixedDelayString = "${knowflow.indexing.poll-delay-millis:1000}")
    public void dispatchOne() {
        queue.claimNext().ifPresent(claim -> {
            try {
                client.dispatch(claim.dispatch());
            } catch (RuntimeException dispatchFailure) {
                if (AiIndexExecutionClient.isDefinitiveClientRejection(dispatchFailure)) {
                    queue.rejectDispatch(claim);
                    LOGGER.warn("AI service rejected an index dispatch; the task was rescheduled");
                } else {
                    // The service may have accepted the request before a timeout or disconnect.
                    // Keep the lease active and let expiry/fencing recover it safely.
                    LOGGER.warn("AI dispatch outcome is unknown; the task lease will expire safely");
                }
            }
        });
    }
}
