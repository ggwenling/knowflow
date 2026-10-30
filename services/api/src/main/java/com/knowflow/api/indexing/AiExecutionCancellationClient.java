package com.knowflow.api.indexing;

import java.time.Duration;

import com.knowflow.api.error.ApiError;
import com.knowflow.api.security.RequestIdFilter;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

@Component
public final class AiExecutionCancellationClient {
    private final WebClient client;

    public AiExecutionCancellationClient(WebClient aiServiceWebClient) {
        this.client = aiServiceWebClient;
    }

    public void cancel(CancelExecution cancellation) {
        if (!ApiError.CONTRACT_VERSION.equals(cancellation.contractVersion())) {
            throw new IllegalArgumentException("Cancellation contract version is invalid");
        }
        client.post()
                .uri("/internal/v1/index-executions/{taskId}/cancel", cancellation.taskId())
                .header(RequestIdFilter.HEADER, cancellation.requestId())
                .bodyValue(cancellation)
                .retrieve()
                .toBodilessEntity()
                .timeout(Duration.ofSeconds(10))
                .block(Duration.ofSeconds(11));
    }
}
