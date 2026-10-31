package com.knowflow.api.answer;

import java.util.function.Predicate;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

/** Applies the current authorization fence immediately before forwarding each upstream event. */
public final class AnswerStreamVisibilityBridge {
    private AnswerStreamVisibilityBridge() {}

    public static Flux<AiAnswerStreamEvent> authorize(
            Flux<AiAnswerStreamEvent> upstream, Predicate<AiAnswerStreamEvent> visible) {
        return upstream.concatMap(event -> Mono.defer(() -> visible.test(event)
                ? Mono.just(event)
                : Mono.error(new SecurityException("Answer scope is no longer visible"))));
    }
}
