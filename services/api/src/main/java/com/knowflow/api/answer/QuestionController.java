package com.knowflow.api.answer;

import java.util.concurrent.FutureTask;
import java.util.UUID;
import java.io.IOException;
import java.util.concurrent.atomic.AtomicReference;

import com.knowflow.api.config.QuestionProperties;
import com.knowflow.api.error.ApiFailure;
import com.knowflow.api.security.AuthenticatedUser;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Profile;
import org.springframework.core.task.TaskExecutor;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.context.request.async.DeferredResult;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.http.MediaType;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import reactor.core.Disposable;

@RestController
@Profile("database")
public class QuestionController {
    private final QuestionService questions;
    private final QuestionProperties properties;
    private final TaskExecutor executor;

    public QuestionController(QuestionService questions, QuestionProperties properties,
                              @Qualifier("questionExecutor") TaskExecutor executor) {
        this.questions = questions;
        this.properties = properties;
        this.executor = executor;
    }

    @PostMapping("/api/v1/knowledge-bases/{knowledgeBaseId}/questions")
    DeferredResult<AnswerResponse> ask(@AuthenticationPrincipal AuthenticatedUser user,
                                       @PathVariable UUID knowledgeBaseId,
                                       @RequestBody PublicQuestion question) {
        long requestStartedAt = System.nanoTime();
        QuestionCancellation cancellation = new QuestionCancellation();
        DeferredResult<AnswerResponse> result = new DeferredResult<>(
                properties.getTotalBudgetSeconds() * 1_000L);
        FutureTask<Void> task = new FutureTask<>(() -> {
            try {
                result.setResult(questions.ask(user, knowledgeBaseId, question,
                        requestStartedAt, cancellation));
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
                      @RequestBody PublicQuestion question) {
        QuestionCancellation cancellation = new QuestionCancellation();
        SseEmitter emitter = new SseEmitter(properties.getTotalBudgetSeconds() * 1_000L);
        AtomicReference<Disposable> subscription = new AtomicReference<>();
        Runnable disconnect = () -> {
            cancellation.clientDisconnected();
            Disposable current = subscription.getAndSet(null);
            if (current != null) {
                current.dispose();
            }
        };
        emitter.onTimeout(() -> {
            cancellation.timeout();
            Disposable current = subscription.getAndSet(null);
            if (current != null) current.dispose();
            emitter.completeWithError(ApiFailure.processingTimeout());
        });
        emitter.onCompletion(disconnect);
        emitter.onError(error -> disconnect.run());
        try {
            executor.execute(() -> {
                try {
                    Disposable current = questions.stream(user, knowledgeBaseId, question, cancellation)
                            .subscribe(event -> send(emitter, event, cancellation),
                                    emitter::completeWithError, emitter::complete);
                    if (!subscription.compareAndSet(null, current)) {
                        current.dispose();
                    }
                } catch (RuntimeException failure) {
                    emitter.completeWithError(failure);
                }
            });
        } catch (TaskRejectedException overloaded) {
            emitter.completeWithError(ApiFailure.aiProcessingFailed());
        }
        return emitter;
    }

    private static void send(SseEmitter emitter, PublicAnswerStreamEvent event,
                             QuestionCancellation cancellation) {
        try {
            emitter.send(SseEmitter.event().name(event.event()).data(event, MediaType.APPLICATION_JSON));
        } catch (IOException failure) {
            cancellation.clientDisconnected();
            emitter.completeWithError(failure);
        }
    }
}
