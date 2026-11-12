package com.knowflow.api.answer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;

import java.util.UUID;

import com.knowflow.api.config.QuestionProperties;
import com.knowflow.api.error.ApiFailure;
import com.knowflow.api.security.AuthenticatedUser;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionTemplate;

class QuestionAdmissionTest {
    @Test
    void synchronousOverloadIsRejectedBeforeDatabaseOrAiWork() throws Exception {
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        AiAnswerClient client = mock(AiAnswerClient.class);
        QuestionProperties properties = new QuestionProperties();
        properties.setMaxConcurrentRequests(1);
        ModelRequestAdmission admission = new ModelRequestAdmission(properties);
        QuestionService service = new QuestionService(jdbc, mock(TransactionTemplate.class), client,
                properties, null, admission);
        var occupied = admission.tryAcquire(false);

        ApiFailure failure = assertThrows(ApiFailure.class, () -> service.ask(user(),
                UUID.randomUUID(), new PublicQuestion("question"), System.nanoTime(),
                new QuestionCancellation()));

        assertEquals("AI_PROCESSING_FAILED", failure.code());
        verifyNoInteractions(jdbc, client);
        occupied.close();
    }

    @Test
    void streamOverloadEmitsRetryableFailureWithoutCreatingQuestion() throws Exception {
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        AiAnswerClient client = mock(AiAnswerClient.class);
        QuestionProperties properties = new QuestionProperties();
        properties.setMaxConcurrentRequests(1);
        ModelRequestAdmission admission = new ModelRequestAdmission(properties);
        QuestionService service = new QuestionService(jdbc, mock(TransactionTemplate.class), client,
                properties, null, admission);
        var occupied = admission.tryAcquire(false);

        PublicAnswerStreamEvent event = service.stream(user(), UUID.randomUUID(),
                new PublicQuestion("question"), new QuestionCancellation(), null,
                System.nanoTime(), "admission-request")
                .blockFirst();

        assertEquals("error", event.event());
        assertEquals("admission-request", event.requestId());
        assertEquals("AI_PROCESSING_FAILED", event.code());
        assertEquals(true, event.retryable());
        verifyNoInteractions(jdbc, client);
        occupied.close();
    }

    private static AuthenticatedUser user() {
        return new AuthenticatedUser(UUID.randomUUID(), "user@example.invalid", "0".repeat(64));
    }
}
