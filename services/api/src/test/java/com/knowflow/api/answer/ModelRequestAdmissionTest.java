package com.knowflow.api.answer;

import com.knowflow.api.config.QuestionProperties;
import com.knowflow.api.error.ApiFailure;
import org.junit.jupiter.api.Test;
import java.time.Duration;
import java.util.UUID;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.http.HttpStatus;
import reactor.core.publisher.Mono;
import static org.junit.jupiter.api.Assertions.*;

class ModelRequestAdmissionTest {
    @Test void customSaturationLeavesBuiltinCapacity() throws Exception {
        var properties = new QuestionProperties();
        properties.setMaxConcurrentRequests(3);
        var admission = new ModelRequestAdmission(properties);
        var entered = new CountDownLatch(2);
        var release = new CountDownLatch(1);
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            java.util.concurrent.Callable<Void> held = () -> {
                try (var lease = admission.tryAcquire(true)) {
                    entered.countDown();
                    release.await();
                }
                return null;
            };
            var custom = executor.submit(held);
            var probe = executor.submit(held);
            try {
                assertTrue(entered.await(1, TimeUnit.SECONDS));
                ApiFailure busy = assertThrows(ApiFailure.class, () -> admission.tryAcquire(true));
                assertEquals(429, busy.status().value());
                assertEquals("RESOURCE_LIMIT", busy.code());
                assertEquals("模型请求繁忙，请稍后重试。", busy.getMessage());
                var client = new AiAnswerClient(WebClient.builder().baseUrl("http://unused.test")
                        .exchangeFunction(request -> {
                            assertEquals("/internal/v1/answers", request.url().getPath());
                            return Mono.just(ClientResponse.create(HttpStatus.OK)
                                    .header("Content-Type", "application/json")
                                    .body("{\"contract_version\":\"0.2.0\",\"request_id\":\"builtin-replay\","
                                            + "\"answer\":\"builtin replay\",\"has_answer\":false,\"sources\":[]}").build());
                        }).build(), new ObjectMapper().setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE));
                try (var builtin = admission.tryAcquire(false)) {
                    var request = new TrustedAnswerRequest("0.2.0", "builtin-replay", "question",
                            new TrustedAnswerRequest.TrustedScope(UUID.randomUUID(), UUID.randomUUID(),
                                    UUID.randomUUID(), List.of()));
                    assertEquals("builtin replay", client.answer(request, Duration.ofSeconds(1)).answer());
                    assertEquals("AI_PROCESSING_FAILED", assertThrows(ApiFailure.class,
                            () -> admission.tryAcquire(false)).code());
                }
                assertFalse(custom.isDone());
                assertFalse(probe.isDone());
            } finally {
                release.countDown();
                custom.get(1, TimeUnit.SECONDS);
                probe.get(1, TimeUnit.SECONDS);
            }
        }
    }

    @Test void probeSharesCustomCapacity() {
        QuestionProperties policy = new QuestionProperties();
        policy.setMaxConcurrentRequests(2);
        policy.setCustomMaxConcurrentRequests(32);
        ModelRequestAdmission admission = new ModelRequestAdmission(policy);
        try (var probe = admission.tryAcquire(true)) {
            assertEquals("RESOURCE_LIMIT", assertThrows(ApiFailure.class,
                    () -> admission.tryAcquire(true)).code());
            try (var builtin = admission.tryAcquire(false)) { assertNotNull(builtin); }
        }
    }

    @Test void cancelAndFailureReleaseBothPermits() throws Exception {
        ModelRequestAdmission admission = admission();
        var entered = new CountDownLatch(1);
        var closed = new CountDownLatch(1);
        try (var executor = Executors.newSingleThreadExecutor()) {
            var cancelled = executor.submit(() -> {
                try (var lease = admission.tryAcquire(true)) {
                    entered.countDown();
                    new CountDownLatch(1).await();
                } catch (InterruptedException cancellation) {
                    Thread.currentThread().interrupt();
                } finally {
                    closed.countDown();
                }
            });
            try {
                assertTrue(entered.await(1, TimeUnit.SECONDS));
                cancelled.cancel(true);
                assertTrue(closed.await(1, TimeUnit.SECONDS));
            } finally {
                cancelled.cancel(true);
            }
        }
        assertThrows(IllegalStateException.class, () -> {
            try (var failed = admission.tryAcquire(true)) { throw new IllegalStateException(); }
        });
        var idempotent = admission.tryAcquire(true);
        idempotent.close();
        idempotent.close();
        try (var one = admission.tryAcquire(true); var two = admission.tryAcquire(true);
             var three = admission.tryAcquire(false); var four = admission.tryAcquire(false)) {
            assertThrows(ApiFailure.class, () -> admission.tryAcquire(false));
        }
    }

    @Test void customEnabledRejectsSingleTotalPermit() {
        QuestionProperties properties = new QuestionProperties();
        properties.setMaxConcurrentRequests(1);
        properties.setCustomEnabled(true);
        assertEquals("LLM_ISOLATION_CONFIGURATION_INVALID", assertThrows(IllegalStateException.class,
                () -> new ModelRequestAdmission(properties)).getMessage());
        properties.setCustomEnabled(false);
        try (var only = new ModelRequestAdmission(properties).tryAcquire(false)) { assertNotNull(only); }
    }

    @Test void busyResponseDoesNotViolateQuestionFailureCodeConstraint() {
        assertEquals("AI_PROCESSING_FAILED", QuestionService.historyFailureCode(ApiFailure.modelBusy().code()));
        assertEquals("AI_PROCESSING_FAILED", QuestionService.historyFailureCode("unknown"));
        assertEquals("PROCESSING_TIMEOUT", QuestionService.historyFailureCode("PROCESSING_TIMEOUT"));
        assertEquals("DOCUMENT_UNAVAILABLE", QuestionService.historyFailureCode("DOCUMENT_UNAVAILABLE"));
    }

    private static ModelRequestAdmission admission() { return new ModelRequestAdmission(new QuestionProperties()); }
}
