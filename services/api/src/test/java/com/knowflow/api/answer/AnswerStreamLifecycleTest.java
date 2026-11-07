package com.knowflow.api.answer;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicLong;

import com.knowflow.api.error.ApiFailure;
import org.junit.jupiter.api.Test;

class AnswerStreamLifecycleTest {
    @Test
    void recordsFirstSuccessfullySentDeltaAndOnlyOneTerminal() {
        AtomicLong now = new AtomicLong(1_000_000_000L);
        List<AnswerStreamLifecycle.Terminal> records = new ArrayList<>();
        AnswerStreamLifecycle lifecycle = new AnswerStreamLifecycle(
                "http-request-id", now::get, records::add);

        now.addAndGet(5_000_000L);
        lifecycle.sent(event("service-request-id", "started", null));
        now.addAndGet(22_000_000L);
        lifecycle.sent(event("service-request-id", "delta", "first"));
        now.addAndGet(18_000_000L);
        lifecycle.sent(event("service-request-id", "delta", "second"));
        now.addAndGet(15_000_000L);
        PublicAnswerStreamEvent completed = event("service-request-id", "completed", null);
        lifecycle.sent(completed);
        lifecycle.terminal(completed);
        lifecycle.finish("failed", "AI_PROCESSING_FAILED");

        assertThat(records).containsExactly(new AnswerStreamLifecycle.Terminal(
                "service-request-id", 27L, 60L, "completed", null));
    }

    @Test
    void timeoutWithoutDeltaRecordsNullFirstDeltaAndTimeoutCodeOnce() {
        AtomicLong now = new AtomicLong();
        List<AnswerStreamLifecycle.Terminal> records = new ArrayList<>();
        AnswerStreamLifecycle lifecycle = new AnswerStreamLifecycle(
                "http-request-id", now::get, records::add);

        now.set(2_500_000_000L);
        lifecycle.failed(ApiFailure.processingTimeout());
        lifecycle.finish("disconnected", null);

        assertThat(records).containsExactly(new AnswerStreamLifecycle.Terminal(
                "http-request-id", null, 2_500L, "timeout", "PROCESSING_TIMEOUT"));
    }

    @Test
    void recordsStreamErrorAndClientDisconnectExactlyOnce() {
        AtomicLong now = new AtomicLong(5_000_000L);
        List<AnswerStreamLifecycle.Terminal> records = new ArrayList<>();
        AnswerStreamLifecycle failed = new AnswerStreamLifecycle(
                "fallback", now::get, records::add);
        PublicAnswerStreamEvent error = new PublicAnswerStreamEvent(
                "0.2.0", "error-request-id", 1, "error",
                null, null, null, "DOCUMENT_UNAVAILABLE", "DOCUMENT_UNAVAILABLE", false);
        failed.sent(error);
        failed.terminal(error);
        failed.finish("disconnected", null);

        AnswerStreamLifecycle disconnected = new AnswerStreamLifecycle(
                "disconnect-request-id", now::get, records::add);
        disconnected.finish("disconnected", null);
        disconnected.finish("failed", "AI_PROCESSING_FAILED");

        assertThat(records).containsExactly(
                new AnswerStreamLifecycle.Terminal("error-request-id", null, 0L,
                        "failed", "DOCUMENT_UNAVAILABLE"),
                new AnswerStreamLifecycle.Terminal("disconnect-request-id", null, 0L,
                        "disconnected", null));
    }

    @Test
    void classifiesProcessingTimeoutErrorEventAsTimeout() {
        List<AnswerStreamLifecycle.Terminal> records = new ArrayList<>();
        AnswerStreamLifecycle lifecycle = new AnswerStreamLifecycle(
                "fallback", () -> 0L, records::add);
        PublicAnswerStreamEvent error = new PublicAnswerStreamEvent(
                "0.2.0", "timeout-request-id", 1, "error",
                null, null, null, "PROCESSING_TIMEOUT", "PROCESSING_TIMEOUT", true);

        lifecycle.sent(error);
        lifecycle.terminal(error);

        assertThat(records).containsExactly(new AnswerStreamLifecycle.Terminal(
                "timeout-request-id", null, 0L, "timeout", "PROCESSING_TIMEOUT"));
    }

    private static PublicAnswerStreamEvent event(String requestId, String name, String delta) {
        return new PublicAnswerStreamEvent("0.2.0", requestId, 1, name,
                delta, null, null, null, null, null);
    }
}
