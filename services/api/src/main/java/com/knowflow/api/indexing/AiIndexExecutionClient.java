package com.knowflow.api.indexing;

import java.time.Duration;

import com.knowflow.api.error.ApiError;
import com.knowflow.api.security.RequestIdFilter;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Mono;

@Component
public final class AiIndexExecutionClient {
    private static final Duration DISPATCH_TIMEOUT = Duration.ofSeconds(10);
    private final WebClient client;

    public AiIndexExecutionClient(WebClient aiServiceWebClient) {
        this.client = aiServiceWebClient;
    }

    public IndexExecutionReceipt dispatch(IndexDispatch dispatch) {
        IndexExecutionReceipt receipt = client.post()
                .uri("/internal/v1/index-executions")
                .header(RequestIdFilter.HEADER, dispatch.requestId())
                .bodyValue(dispatch)
                .exchangeToMono(response -> {
                    if (response.statusCode().value() != 202) {
                        if (response.statusCode().isError()) {
                            return response.createException().flatMap(Mono::error);
                        }
                        return Mono.error(new IllegalStateException(
                                "AI index dispatch returned an unexpected status"));
                    }
                    return response.bodyToMono(IndexExecutionReceipt.class);
                })
                .timeout(DISPATCH_TIMEOUT)
                .block(DISPATCH_TIMEOUT.plusSeconds(1));
        if (receipt == null || !ApiError.CONTRACT_VERSION.equals(receipt.contractVersion())
                || !dispatch.requestId().equals(receipt.requestId())
                || !dispatch.lease().taskId().equals(receipt.taskId())
                || !dispatch.lease().indexVersionId().equals(receipt.indexVersionId())
                || !"ACCEPTED".equals(receipt.result())) {
            throw new IllegalStateException("AI index dispatch receipt does not match the contract");
        }
        return receipt;
    }

    public static boolean isDefinitiveClientRejection(Throwable failure) {
        if (!(failure instanceof WebClientResponseException response)) {
            return false;
        }
        int status = response.getStatusCode().value();
        return status >= 400 && status < 500 && status != 409;
    }
}
