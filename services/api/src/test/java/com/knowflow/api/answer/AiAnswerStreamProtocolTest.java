package com.knowflow.api.answer;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.knowflow.api.error.ApiError;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Flux;

class AiAnswerStreamProtocolTest {
    @Test
    void acceptsOrderedStreamAndRejectsDuplicateTerminal() {
        var request = request();
        var state = new java.util.concurrent.atomic.AtomicReference<>(
                new AiAnswerClient.StreamState(0, "START"));
        assertThat(AiAnswerClient.validateStreamEvent(request, state,
                event(1, "started"))).isNotNull();
        assertThat(AiAnswerClient.validateStreamEvent(request, state,
                new AiAnswerStreamEvent(ApiError.CONTRACT_VERSION, request.requestId(), 2,
                        "delta", "Partial", null, null, null, null, null))).isNotNull();
        assertThat(AiAnswerClient.validateStreamEvent(request, state,
                new AiAnswerStreamEvent(ApiError.CONTRACT_VERSION, request.requestId(), 3,
                        "sources", null, false, List.of(), null, null, null))).isNotNull();
        assertThat(AiAnswerClient.validateStreamEvent(request, state,
                event(4, "completed"))).isNotNull();
        assertThatThrownBy(() -> AiAnswerClient.validateStreamEvent(request, state,
                event(5, "completed"))).isInstanceOf(IllegalStateException.class);
    }

    @Test
    void stopsForwardingAndCancelsUpstreamAsSoonAsVisibilityIsRevoked() {
        AtomicBoolean cancelled = new AtomicBoolean();
        Flux<AiAnswerStreamEvent> upstream = Flux.<AiAnswerStreamEvent>create(sink -> {
            sink.onCancel(() -> cancelled.set(true));
            sink.next(event(1, "started"));
            sink.next(new AiAnswerStreamEvent(ApiError.CONTRACT_VERSION, "request", 2,
                    "delta", "hidden", null, null, null, null, null));
            sink.complete();
        });
        assertThatThrownBy(() -> AnswerStreamVisibilityBridge.authorize(upstream,
                event -> event.sequence() == 1).collectList().block())
                .isInstanceOf(SecurityException.class);
        assertThat(cancelled).isTrue();
    }

    @Test
    void rejectsOutOfOrderSequence() {
        var request = request();
        assertThatThrownBy(() -> AiAnswerClient.validateStreamEvent(request,
                new java.util.concurrent.atomic.AtomicReference<>(
                        new AiAnswerClient.StreamState(0, "START")),
                event(2, "started"))).isInstanceOf(IllegalStateException.class);
    }

    @Test
    void decodesSseFramesIncrementallyAndRejectsTruncation() {
        var mapper = new ObjectMapper().setPropertyNamingStrategy(
                com.fasterxml.jackson.databind.PropertyNamingStrategies.SNAKE_CASE);
        var http = WebClient.builder().exchangeFunction(request -> reactor.core.publisher.Mono.just(
                org.springframework.web.reactive.function.client.ClientResponse.create(
                        org.springframework.http.HttpStatus.OK)
                        .header("Content-Type", "text/event-stream")
                        .body("""
                                event: started
                                data: {"contract_version":"%s","request_id":"request","sequence":1,"event":"started"}

                                event: delta
                                data: {"contract_version":"%s","request_id":"request","sequence":2,"event":"delta","delta":"Visible"}

                                """.formatted(ApiError.CONTRACT_VERSION, ApiError.CONTRACT_VERSION)).build())).build();
        var client = new AiAnswerClient(http, mapper);
        List<String> received = new java.util.ArrayList<>();
        assertThatThrownBy(() -> client.stream(request(), java.time.Duration.ofSeconds(2))
                .doOnNext(event -> received.add(event.event())).blockLast())
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("terminal");
        assertThat(received).containsExactly("started", "delta");
    }

    @Test
    void downstreamDisconnectCancelsTheUpstreamSubscription() {
        AtomicBoolean cancelled = new AtomicBoolean();
        Flux<AiAnswerStreamEvent> upstream = Flux.<AiAnswerStreamEvent>never()
                .doOnCancel(() -> cancelled.set(true));
        var subscription = AnswerStreamVisibilityBridge.authorize(upstream, ignored -> true)
                .subscribe();
        subscription.dispose();
        assertThat(cancelled).isTrue();
    }

    private static TrustedAnswerRequest request() {
        return new TrustedAnswerRequest(ApiError.CONTRACT_VERSION, "request", "question",
                new TrustedAnswerRequest.TrustedScope(null, null, null, List.of()));
    }

    private static AiAnswerStreamEvent event(long sequence, String type) {
        return new AiAnswerStreamEvent(ApiError.CONTRACT_VERSION, "request", sequence, type,
                null, null, null, null, null, null);
    }
}
