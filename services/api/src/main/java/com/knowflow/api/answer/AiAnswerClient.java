package com.knowflow.api.answer;

import java.time.Duration;

import com.knowflow.api.error.ApiError;
import com.knowflow.api.security.RequestIdFilter;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component
public final class AiAnswerClient {
    private final WebClient client;

    public AiAnswerClient(WebClient aiServiceWebClient) {
        this.client = aiServiceWebClient;
    }

    public AiAnswerResponse answer(TrustedAnswerRequest request, Duration remainingBudget) {
        if (remainingBudget == null || remainingBudget.isZero() || remainingBudget.isNegative()) {
            throw new IllegalStateException("Question budget exhausted",
                    new java.util.concurrent.TimeoutException());
        }
        AiAnswerResponse response = client.post()
                .uri("/internal/v1/answers")
                .header(RequestIdFilter.HEADER, request.requestId())
                .bodyValue(request)
                .exchangeToMono(result -> {
                    if (!result.statusCode().is2xxSuccessful()) {
                        return result.createException().flatMap(Mono::error);
                    }
                    return result.bodyToMono(AiAnswerResponse.class);
                })
                .timeout(remainingBudget)
                .block(remainingBudget);
        if (response == null || !ApiError.CONTRACT_VERSION.equals(response.contractVersion())
                || !request.requestId().equals(response.requestId())) {
            throw new IllegalStateException("AI answer response does not match the contract");
        }
        return response;
    }
}
