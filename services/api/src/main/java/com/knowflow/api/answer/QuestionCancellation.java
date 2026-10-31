package com.knowflow.api.answer;

import java.util.concurrent.atomic.AtomicReference;

final class QuestionCancellation {
    enum Reason {
        TIMEOUT,
        CLIENT_DISCONNECTED
    }

    private final AtomicReference<Reason> reason = new AtomicReference<>();

    void timeout() {
        reason.compareAndSet(null, Reason.TIMEOUT);
    }

    void clientDisconnected() {
        reason.compareAndSet(null, Reason.CLIENT_DISCONNECTED);
    }

    Reason reason() {
        return reason.get();
    }
}
