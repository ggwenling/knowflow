package com.knowflow.api.answer;

import java.util.concurrent.FutureTask;
import java.util.UUID;
import java.io.IOException;
import java.util.concurrent.atomic.AtomicReference;

import com.knowflow.api.config.QuestionProperties;
import com.knowflow.api.error.ApiFailure;
import com.knowflow.api.security.AuthenticatedUser;
import com.knowflow.api.security.RequestIdFilter;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Profile;
import org.springframework.core.task.TaskExecutor;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.context.request.async.DeferredResult;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.http.MediaType;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import reactor.core.Disposable;

@RestController
@Profile("database")
public class QuestionController {
    private final QuestionService questions;
    private final QuestionProperties properties;
    private final TaskExecutor executor;
    private final QuestionHistoryService history;

    public QuestionController(QuestionService questions, QuestionProperties properties,
                              @Qualifier("questionExecutor") TaskExecutor executor,
                              QuestionHistoryService history) {
        this.questions = questions;
        this.properties = properties;
        this.executor = executor;
        this.history = history;
    }

    @GetMapping("/api/v1/questions")
    QuestionHistoryListResponse history(@AuthenticationPrincipal AuthenticatedUser user,
                                         @RequestParam(defaultValue = "50") int limit,
                                         @RequestParam(defaultValue = "0") int offset) {
        return history.list(user, limit, offset);
    }

    @GetMapping("/api/v1/questions/{questionId}")
    QuestionHistoryDetail history(@AuthenticationPrincipal AuthenticatedUser user,
                                  @PathVariable UUID questionId) {
        return history.get(user, questionId);
    }

    @DeleteMapping("/api/v1/questions/{questionId}")
    ResponseEntity<Void> delete(@AuthenticationPrincipal AuthenticatedUser user,
                                @PathVariable UUID questionId) {
        history.delete(user, questionId);
        return ResponseEntity.status(HttpStatus.NO_CONTENT).build();
    }

    @PostMapping("/api/v1/knowledge-bases/{knowledgeBaseId}/questions")
    DeferredResult<AnswerResponse> ask(@AuthenticationPrincipal AuthenticatedUser user,
                                       @PathVariable UUID knowledgeBaseId,
                                       @RequestHeader(value = "Idempotency-Key", required = false)
                                               String idempotencyKey,
                                       @RequestBody PublicQuestion question) {
        UUID parsedIdempotencyKey = QuestionService.parseIdempotencyKey(idempotencyKey);
        long requestStartedAt = System.nanoTime();
        QuestionCancellation cancellation = new QuestionCancellation();
        DeferredResult<AnswerResponse> result = new DeferredResult<>(
                properties.getTotalBudgetSeconds() * 1_000L);
        FutureTask<Void> task = new FutureTask<>(() -> {
            try {
                result.setResult(questions.ask(user, knowledgeBaseId, question,
                        requestStartedAt, cancellation, parsedIdempotencyKey));
            } catch (RuntimeException failure) {
                if (cancellation.reason() != QuestionCancellation.Reason.CLIENT_DISCONNECTED) {
                    result.setErrorResult(failure);
                }
            }
            return null;
        });

        result.onTimeout(() -> {
            cancellation.timeout();
            task.cancel(true);
            result.setErrorResult(ApiFailure.processingTimeout());
        });
        result.onError(failure -> {
            cancellation.clientDisconnected();
            task.cancel(true);
        });
        result.onCompletion(() -> {
            if (!result.hasResult()) {
                cancellation.clientDisconnected();
                task.cancel(true);
            }
        });

        try {
            executor.execute(task);
        } catch (TaskRejectedException overloaded) {
            result.setErrorResult(ApiFailure.aiProcessingFailed());
        }
        return result;
    }

    @PostMapping(path = "/api/v1/knowledge-bases/{knowledgeBaseId}/questions/stream",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    SseEmitter stream(@AuthenticationPrincipal AuthenticatedUser user,
                      @PathVariable UUID knowledgeBaseId,
                      @RequestHeader(value = "Idempotency-Key", required = false)
                              String idempotencyKey,
                      @RequestBody PublicQuestion question,
                      HttpServletRequest servletRequest) {
        QuestionService.parseIdempotencyKey(idempotencyKey);
        QuestionCancellation cancellation = new QuestionCancellation();
        Object requestIdAttribute = servletRequest.getAttribute(RequestIdFilter.ATTRIBUTE);
        String fallbackRequestId = requestIdAttribute instanceof String id
                ? id : UUID.randomUUID().toString();
        AnswerStreamLifecycle lifecycle = new AnswerStreamLifecycle(fallbackRequestId);
        SseEmitter emitter = new SseEmitter(properties.getTotalBudgetSeconds() * 1_000L);
        AtomicReference<Disposable> subscription = new AtomicReference<>();
        Runnable cancelUpstream = () -> {
            cancellation.clientDisconnected();
            Disposable current = subscription.getAndSet(null);
            if (current != null) {
                current.dispose();
            }
        };
        emitter.onTimeout(() -> {
            cancellation.timeout();
            lifecycle.finish("timeout", "PROCESSING_TIMEOUT");
            Disposable current = subscription.getAndSet(null);
            if (current != null) current.dispose();
            emitter.completeWithError(ApiFailure.processingTimeout());
        });
        emitter.onCompletion(() -> {
            cancelUpstream.run();
            lifecycle.finish("disconnected", null);
        });
        emitter.onError(error -> {
            cancelUpstream.run();
            lifecycle.failed(error);
        });
        try {
            executor.execute(() -> {
                try {
                    Disposable current = questions.stream(user, knowledgeBaseId, question,
                                    cancellation, idempotencyKey)
                            .subscribe(event -> send(emitter, event, cancellation, lifecycle),
                                    failure -> {
                                        lifecycle.failed(failure);
                                        emitter.completeWithError(failure);
                                    }, emitter::complete);
                    if (!subscription.compareAndSet(null, current)) {
                        current.dispose();
                    }
                } catch (RuntimeException failure) {
                    lifecycle.failed(failure);
                    emitter.completeWithError(failure);
                }
            });
        } catch (TaskRejectedException overloaded) {
            lifecycle.finish("failed", "AI_PROCESSING_FAILED");
            emitter.completeWithError(ApiFailure.aiProcessingFailed());
        }
        return emitter;
    }

    private static void send(SseEmitter emitter, PublicAnswerStreamEvent event,
                             QuestionCancellation cancellation,
                             AnswerStreamLifecycle lifecycle) {
        try {
            emitter.send(SseEmitter.event().name(event.event()).data(event, MediaType.APPLICATION_JSON));
            lifecycle.sent(event);
            lifecycle.terminal(event);
        } catch (IOException failure) {
            cancellation.clientDisconnected();
            lifecycle.finish("disconnected", null);
            emitter.completeWithError(failure);
        }
    }
}
