package com.knowflow.api.ai;

import java.time.Duration;
import java.util.UUID;
import java.util.regex.Pattern;

import com.knowflow.api.error.ApiError;
import com.knowflow.api.security.RequestIdFilter;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component
public final class AiInternalHealthClient {
    private static final Pattern REQUEST_ID = Pattern.compile("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}");
    private static final Duration CALL_TIMEOUT = Duration.ofSeconds(5);

    private final WebClient client;

    public AiInternalHealthClient(WebClient aiServiceWebClient) {
        this.client = aiServiceWebClient;
    }

    public Mono<InternalHealth> check() {
        return check(UUID.randomUUID().toString());
    }

    public Mono<InternalHealth> check(String requestId) {
        if (requestId == null || !REQUEST_ID.matcher(requestId).matches()) {
            return Mono.error(new IllegalArgumentException("A valid request ID is required"));
        }

        return client.get()
                .uri("/internal/v1/health")
                .header(RequestIdFilter.HEADER, requestId)
                .retrieve()
                .bodyToMono(InternalHealth.class)
                .timeout(CALL_TIMEOUT)
                .flatMap(response -> {
                    if (!ApiError.CONTRACT_VERSION.equals(response.contract_version())
                            || !"UP".equals(response.status())
                            || !requestId.equals(response.request_id())) {
                        return Mono.error(new IllegalStateException(
                                "AI internal health response does not match the contract"));
                    }
                    return Mono.just(response);
                });
    }
}
