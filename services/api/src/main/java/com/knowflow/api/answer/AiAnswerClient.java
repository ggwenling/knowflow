package com.knowflow.api.answer;

import java.time.Duration;
import java.util.UUID;
import java.io.IOException;
import java.util.concurrent.atomic.AtomicReference;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.knowflow.api.error.ApiError;
import com.knowflow.api.error.ApiFailure;
import com.knowflow.api.security.RequestIdFilter;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.codec.ServerSentEvent;

@Component
public final class AiAnswerClient {
    private final WebClient client;
    private final ObjectMapper mapper;

    public AiAnswerClient(WebClient aiServiceWebClient, ObjectMapper mapper) {
        this.client = aiServiceWebClient;
        this.mapper = mapper;
    }

    public AiAnswerResponse answer(TrustedAnswerRequest request, Duration remainingBudget) {
        return answer(request, remainingBudget, null);
    }

    AiAnswerResponse answer(TrustedAnswerRequest request, Duration remainingBudget, LlmModelService.Connection model) {
        if (remainingBudget == null || remainingBudget.isZero() || remainingBudget.isNegative()) {
            throw new IllegalStateException("Question budget exhausted",
                    new java.util.concurrent.TimeoutException());
        }
        AiAnswerResponse response = client.post()
                .uri(model == null ? "/internal/v1/answers" : "/internal/v1/custom-answers")
                .header(RequestIdFilter.HEADER, request.requestId())
                .bodyValue(model == null ? request : new CustomAnswer(request, model))
                .exchangeToMono(result -> {
                    if (!result.statusCode().is2xxSuccessful()) {
                        return upstreamFailure(result, request.requestId()).flatMap(Mono::error);
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

    public Flux<AiAnswerStreamEvent> stream(TrustedAnswerRequest request, Duration remainingBudget) {
        return stream(request, remainingBudget, null);
    }

    Flux<AiAnswerStreamEvent> stream(TrustedAnswerRequest request, Duration remainingBudget,
                                    LlmModelService.Connection model) {
        if (remainingBudget == null || remainingBudget.isZero() || remainingBudget.isNegative()) {
            return Flux.error(new IllegalStateException("Question budget exhausted",
                    new java.util.concurrent.TimeoutException()));
        }
        return Flux.defer(() -> {
            AtomicReference<StreamState> state = new AtomicReference<>(new StreamState(0, "START"));
            return client.post()
                .uri(model == null ? "/internal/v1/answers/stream" : "/internal/v1/custom-answers/stream")
                .header(RequestIdFilter.HEADER, request.requestId())
                .accept(org.springframework.http.MediaType.TEXT_EVENT_STREAM)
                .bodyValue(model == null ? request : new CustomAnswer(request, model))
                .retrieve()
                .onStatus(status -> !status.is2xxSuccessful(), result -> upstreamFailure(result, request.requestId()))
                .bodyToFlux(new ParameterizedTypeReference<ServerSentEvent<String>>() {})
                .timeout(remainingBudget)
                .takeUntilOther(Mono.delay(remainingBudget).flatMap(ignored ->
                        Mono.error(new java.util.concurrent.TimeoutException("Question stream budget exhausted"))))
                .map(frame -> {
                    AiAnswerStreamEvent event = decodeStreamEvent(frame.data());
                    if (!event.event().equals(frame.event())) {
                        throw new IllegalStateException("AI SSE event name does not match its payload");
                    }
                    return event;
                })
                .map(event -> validateStreamEvent(request, state, event))
                .takeUntil(event -> state.get().terminal())
                .concatWith(Flux.defer(() -> state.get().terminal()
                        ? Flux.empty()
                        : Flux.error(new IllegalStateException("AI stream ended without a terminal event"))));
        });
    }

    boolean probeModel(UUID owner, LlmModelService.Connection model, String requestId) {
        ModelProbe response = client.post().uri("/internal/v1/llm-models/probe")
                .header("X-KnowFlow-Owner-ID", owner.toString())
                .header(RequestIdFilter.HEADER, requestId).bodyValue(model)
                .exchangeToMono(result -> result.statusCode().is2xxSuccessful()
                        ? result.bodyToMono(ModelProbe.class)
                        : upstreamFailure(result, requestId).flatMap(Mono::error))
                .timeout(Duration.ofSeconds(12))
                .onErrorResume(failure -> failure instanceof ApiFailure apiFailure
                        && "RESOURCE_LIMIT".equals(apiFailure.code()) ? Mono.error(failure) : Mono.empty()).block();
        if (response == null) {
            throw new ApiFailure(org.springframework.http.HttpStatus.UNPROCESSABLE_ENTITY, "LLM_MODEL_PROBE_FAILED",
                    "The configured model could not complete a connection test.");
        }
        return response.supportsTools();
    }

    private Mono<? extends Throwable> upstreamFailure(
            org.springframework.web.reactive.function.client.ClientResponse response, String requestId) {
        if (response.statusCode().value() != 429) return response.createException();
        return response.bodyToMono(String.class).defaultIfEmpty("").map(body -> {
            try {
                com.fasterxml.jackson.databind.JsonNode value = mapper.readTree(body);
                if (value != null && value.isObject() && value.size() == 5
                        && ApiError.CONTRACT_VERSION.equals(value.path("contract_version").asText())
                        && requestId.equals(value.path("request_id").asText())
                        && "RESOURCE_LIMIT".equals(value.path("code").asText())
                        && value.path("message").isTextual() && value.path("retryable").isBoolean()
                        && value.path("retryable").booleanValue()) return ApiFailure.modelBusy();
            } catch (IOException invalid) {
                // Provider bodies never become public error text.
            }
            return new IllegalStateException("AI request failed");
        });
    }

    private record CustomAnswer(TrustedAnswerRequest request, LlmModelService.Connection model) {}
    private record ModelProbe(boolean supportsTools) {}

    private AiAnswerStreamEvent decodeStreamEvent(String data) {
        if (data == null) {
            throw new IllegalStateException("AI stream event has no data");
        }
        try {
            return mapper.readValue(data, AiAnswerStreamEvent.class);
        } catch (IOException invalid) {
            throw new IllegalStateException("AI stream event is invalid", invalid);
        }
    }

    static AiAnswerStreamEvent validateStreamEvent(TrustedAnswerRequest request,
            AtomicReference<StreamState> stateRef, AiAnswerStreamEvent event) {
        StreamState state = stateRef.get();
        if (!com.knowflow.api.error.ApiError.CONTRACT_VERSION.equals(event.contractVersion())
                || !request.requestId().equals(event.requestId())
                || event.sequence() != state.sequence() + 1 || state.terminal()) {
            throw new IllegalStateException("AI stream event sequence or request does not match");
        }
        boolean answerPayload = event.hasAnswer() != null || event.sources() != null;
        boolean errorPayload = event.code() != null || event.message() != null || event.retryable() != null;
        if (!"delta".equals(event.event()) && event.delta() != null
                || !"sources".equals(event.event()) && answerPayload
                || !"error".equals(event.event()) && errorPayload) {
            throw new IllegalStateException("AI stream payload does not match its event type");
        }
        String next = switch (event.event()) {
            case "started" -> {
                if (!"START".equals(state.phase()) || event.delta() != null || event.sources() != null) {
                    throw new IllegalStateException("AI stream started event is out of order");
                }
                yield "STARTED";
            }
            case "delta" -> {
                if (!"STARTED".equals(state.phase()) || event.delta() == null || event.delta().isEmpty()
                        || event.delta().codePointCount(0, event.delta().length()) > 16000) {
                    throw new IllegalStateException("AI stream delta event is invalid");
                }
                yield "STARTED";
            }
            case "sources" -> {
                if (!"STARTED".equals(state.phase()) || event.hasAnswer() == null
                        || event.sources() == null || event.sources().size() > 5
                        || event.hasAnswer() && event.sources().isEmpty()
                        || !event.hasAnswer() && !event.sources().isEmpty()) {
                    throw new IllegalStateException("AI stream sources event is invalid");
                }
                yield "SOURCES";
            }
            case "completed" -> {
                if (!"SOURCES".equals(state.phase()) || event.hasAnswer() != null) {
                    throw new IllegalStateException("AI stream completed event is out of order");
                }
                yield "TERMINAL";
            }
            case "error" -> {
                if ("START".equals(state.phase()) || event.code() == null || event.message() == null
                        || event.retryable() == null) {
                    throw new IllegalStateException("AI stream error event is invalid");
                }
                yield "TERMINAL";
            }
            case "cancelled" -> {
                if ("START".equals(state.phase())) {
                    throw new IllegalStateException("AI stream cancelled event is out of order");
                }
                yield "TERMINAL";
            }
            default -> throw new IllegalStateException("AI stream event type is unknown");
        };
        stateRef.set(new StreamState(event.sequence(), next));
        return event;
    }

    record StreamState(long sequence, String phase) {
        boolean terminal() {
            return "TERMINAL".equals(phase);
        }
    }
}
