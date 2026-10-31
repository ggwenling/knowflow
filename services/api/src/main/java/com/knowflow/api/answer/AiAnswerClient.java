package com.knowflow.api.answer;

import java.time.Duration;
import java.io.IOException;
import java.util.concurrent.atomic.AtomicReference;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.knowflow.api.error.ApiError;
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

    public Flux<AiAnswerStreamEvent> stream(TrustedAnswerRequest request, Duration remainingBudget) {
        if (remainingBudget == null || remainingBudget.isZero() || remainingBudget.isNegative()) {
            return Flux.error(new IllegalStateException("Question budget exhausted",
                    new java.util.concurrent.TimeoutException()));
        }
        return Flux.defer(() -> {
            AtomicReference<StreamState> state = new AtomicReference<>(new StreamState(0, "START"));
            return client.post()
                .uri("/internal/v1/answers/stream")
                .header(RequestIdFilter.HEADER, request.requestId())
                .accept(org.springframework.http.MediaType.TEXT_EVENT_STREAM)
                .bodyValue(request)
                .retrieve()
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
