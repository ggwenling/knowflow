package com.knowflow.api.answer;

import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.knowflow.api.error.ApiFailure;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
import static org.junit.jupiter.api.Assertions.*;

class AiAnswerClientProbeTest {
    private final UUID owner = UUID.randomUUID();
    private final LlmModelService.Connection model = new LlmModelService.Connection(UUID.randomUUID(),
            "https://provider.example.test", "responses", "test-model", "secret", false);

    @Test void forwardsTrustedOwnerAndRequestId() {
        AtomicReference<ClientRequest> sent = new AtomicReference<>();
        AiAnswerClient client = client(HttpStatus.OK, "{\"supports_tools\":true,\"status\":\"success\",\"checked_at\":\"2026-11-12T01:02:03Z\"}", sent);
        assertTrue(client.probeModel(owner, model, "safe-filtered-id").supportsTools());
        assertEquals(owner.toString(), sent.get().headers().getFirst("X-KnowFlow-Owner-ID"));
        assertEquals("safe-filtered-id", sent.get().headers().getFirst("X-Request-ID"));
    }

    @Test void mapsOnlyValidBusyEnvelopeWithoutProviderText() {
        AiAnswerClient busy = client(HttpStatus.TOO_MANY_REQUESTS, envelope("RESOURCE_LIMIT"), new AtomicReference<>());
        ApiFailure failure = assertThrows(ApiFailure.class, () -> busy.probeModel(owner, model, "request"));
        assertEquals("RESOURCE_LIMIT", failure.code());
        assertEquals("模型请求繁忙，请稍后重试。", failure.getMessage());
        for (String body : new String[]{"{\"code\":\"RESOURCE_LIMIT\"}", envelope("AI_PROCESSING_FAILED"),
                envelope("RESOURCE_LIMIT").replace("request", "different"), "provider-secret"}) {
            ApiFailure rejected = assertThrows(ApiFailure.class, () -> client(HttpStatus.TOO_MANY_REQUESTS,
                    body, new AtomicReference<>()).probeModel(owner, model, "request"));
            assertEquals("LLM_MODEL_PROBE_FAILED", rejected.code());
            assertFalse(rejected.getMessage().contains("provider-secret"));
        }
        assertEquals("LLM_MODEL_PROBE_FAILED", assertThrows(ApiFailure.class,
                () -> client(HttpStatus.SERVICE_UNAVAILABLE, envelope("RESOURCE_LIMIT"), new AtomicReference<>())
                        .probeModel(owner, model, "request")).code());
    }

    @Test void mapsAllowedProbeErrorsWithoutProviderText() {
        for (String code : AiAnswerClient.PROBE_MESSAGES.keySet()) {
            HttpStatus status = code.equals("LLM_MODEL_URL_INVALID") ? HttpStatus.BAD_REQUEST : HttpStatus.UNPROCESSABLE_ENTITY;
            String body = envelope(code).replace("true", "false");
            var failure = assertThrows(ApiFailure.class,
                    () -> client(status, body, new AtomicReference<>()).probeModel(owner, model, "request"));
            assertEquals(code, failure.code());
            assertEquals(status, failure.status());
            assertEquals(AiAnswerClient.PROBE_MESSAGES.get(code), failure.getMessage());
            assertNull(failure.getCause());
            assertFalse(failure.getMessage().contains("provider-secret"));
        }
    }

    @Test void rejectsMalformedSuccessAndUnknownErrorCode() {
        for (String body : new String[]{"", "null", "{}", "[]", "provider-secret", "{\"supports_tools\":false}",
                "{\"supports_tools\":true,\"status\":\"failed\",\"checked_at\":\"2026-11-12T01:02:03Z\"}",
                "{\"status\":\"success\",\"checked_at\":\"2026-11-12T01:02:03Z\"}",
                "{\"supports_tools\":\"false\",\"status\":\"success\",\"checked_at\":\"2026-11-12T01:02:03Z\"}",
                "{\"supports_tools\":false,\"status\":\"success\",\"checked_at\":\"invalid\"}",
                "x".repeat(1024 * 1024 + 1)}) {
            var failure = assertThrows(ApiFailure.class,
                    () -> client(HttpStatus.OK, body, new AtomicReference<>()).probeModel(owner, model, "request"));
            assertEquals("LLM_MODEL_PROBE_FAILED", failure.code());
        }
        for (String body : new String[]{envelope("UNKNOWN_SECRET_CODE").replace("true", "false"),
                envelope("LLM_MODEL_AUTH_FAILED").replace("true", "false").replace("request", "different"), "not-json"}) {
            assertEquals("LLM_MODEL_PROBE_FAILED", assertThrows(ApiFailure.class,
                    () -> client(HttpStatus.UNPROCESSABLE_ENTITY, body, new AtomicReference<>())
                            .probeModel(owner, model, "request")).code());
        }
        var broken = new AiAnswerClient(WebClient.builder().exchangeFunction(request -> Mono.error(
                new IllegalStateException("provider-secret"))).build(), new ObjectMapper());
        assertEquals("LLM_MODEL_PROBE_FAILED", assertThrows(ApiFailure.class,
                () -> broken.probeModel(owner, model, "request")).code());
        var unsafe = new AiAnswerClient(WebClient.builder().exchangeFunction(request -> Mono.error(
                new ApiFailure(HttpStatus.BAD_GATEWAY, "UNKNOWN_CODE", "provider-secret"))).build(), new ObjectMapper());
        var safe = assertThrows(ApiFailure.class, () -> unsafe.probeModel(owner, model, "request"));
        assertEquals("LLM_MODEL_PROBE_FAILED", safe.code());
        assertFalse(safe.getMessage().contains("provider-secret"));
    }

    @Test void answerAndStreamPreserveOnlyExplicitBusy() {
        var request = new TrustedAnswerRequest("0.2.0", "request", "question",
                new TrustedAnswerRequest.TrustedScope(owner, UUID.randomUUID(), UUID.randomUUID(), java.util.List.of()));
        var client = client(HttpStatus.TOO_MANY_REQUESTS, envelope("RESOURCE_LIMIT"), new AtomicReference<>());
        assertEquals("RESOURCE_LIMIT", assertThrows(ApiFailure.class,
                () -> client.answer(request, Duration.ofSeconds(1))).code());
        assertEquals("RESOURCE_LIMIT", assertThrows(ApiFailure.class,
                () -> client.stream(request, Duration.ofSeconds(1)).blockFirst()).code());
    }

    private static String envelope(String code) {
        return "{\"contract_version\":\"0.2.0\",\"request_id\":\"request\",\"code\":\"" + code
                + "\",\"message\":\"provider-secret\",\"retryable\":true}";
    }

    private static AiAnswerClient client(HttpStatus status, String body, AtomicReference<ClientRequest> sent) {
        WebClient web = WebClient.builder().baseUrl("http://unused.test").exchangeFunction(request -> {
            sent.set(request);
            return Mono.just(ClientResponse.create(status).header("Content-Type", MediaType.APPLICATION_JSON_VALUE)
                    .body(body).build());
        }).build();
        return new AiAnswerClient(web, new ObjectMapper()
                .setPropertyNamingStrategy(com.fasterxml.jackson.databind.PropertyNamingStrategies.SNAKE_CASE));
    }
}
