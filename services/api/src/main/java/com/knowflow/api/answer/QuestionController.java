package com.knowflow.api.answer;

import java.util.concurrent.FutureTask;
import java.util.UUID;

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
}
