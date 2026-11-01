package com.knowflow.api.answer;

import java.util.concurrent.CancellationException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Consumer;
import java.util.function.LongSupplier;

import com.knowflow.api.error.ApiFailure;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

final class AnswerStreamLifecycle {
    private static final Logger LOGGER = LoggerFactory.getLogger(AnswerStreamLifecycle.class);

    record Terminal(String requestId, Long firstDeltaMillis, long totalMillis,
                    String status, String errorCode) {}

    private final AtomicReference<String> requestId;
    private final long startedAtNanos;
    private final LongSupplier nanoTime;
    private final Consumer<Terminal> terminalSink;
    private final AtomicLong firstDeltaAtNanos = new AtomicLong(-1);
    private final AtomicBoolean terminal = new AtomicBoolean();

    AnswerStreamLifecycle(String fallbackRequestId) {
        this(fallbackRequestId, System::nanoTime, value -> LOGGER.info(
                "answer_stream_lifecycle request_id={} first_delta_ms={} total_ms={} "
                        + "terminal_status={} error_code={}",
                value.requestId(), value.firstDeltaMillis(), value.totalMillis(),
                value.status(), value.errorCode()));
    }

    AnswerStreamLifecycle(String fallbackRequestId, LongSupplier nanoTime,
                          Consumer<Terminal> terminalSink) {
        this.requestId = new AtomicReference<>(fallbackRequestId);
        this.nanoTime = nanoTime;
        this.startedAtNanos = nanoTime.getAsLong();
        this.terminalSink = terminalSink;
    }

    void sent(PublicAnswerStreamEvent event) {
        if (event.requestId() != null) {
            requestId.set(event.requestId());
        }
        if ("delta".equals(event.event()) && event.delta() != null) {
            firstDeltaAtNanos.compareAndSet(-1, nanoTime.getAsLong());
        }
    }

    void terminal(PublicAnswerStreamEvent event) {
        switch (event.event()) {
            case "completed" -> finish("completed", null);
            case "error" -> finish("PROCESSING_TIMEOUT".equals(event.code())
                    ? "timeout" : "failed", event.code());
            case "cancelled" -> finish("cancelled", null);
            default -> { }
        }
    }

    void failed(Throwable failure) {
        String status = "failed";
        String code = "AI_PROCESSING_FAILED";
        for (Throwable current = failure; current != null; current = current.getCause()) {
            if (current instanceof ApiFailure apiFailure) {
                code = apiFailure.code();
                if ("PROCESSING_TIMEOUT".equals(code)) {
                    status = "timeout";
                }
                break;
            }
            if (current instanceof TimeoutException
                    || current.getClass().getSimpleName().toLowerCase(java.util.Locale.ROOT)
                    .contains("timeout")) {
                status = "timeout";
                code = "PROCESSING_TIMEOUT";
                break;
            }
            if (current instanceof CancellationException) {
                status = "cancelled";
                code = null;
                break;
            }
        }
        finish(status, code);
    }

    void finish(String status, String errorCode) {
        if (!terminal.compareAndSet(false, true)) {
            return;
        }
        long now = nanoTime.getAsLong();
        long firstDeltaAt = firstDeltaAtNanos.get();
        terminalSink.accept(new Terminal(requestId.get(),
                firstDeltaAt < 0 ? null
                        : TimeUnit.NANOSECONDS.toMillis(firstDeltaAt - startedAtNanos),
                TimeUnit.NANOSECONDS.toMillis(now - startedAtNanos), status, errorCode));
    }
}
