package com.knowflow.api;

import java.net.URI;
import java.time.Duration;
import java.util.Map;
import com.knowflow.api.config.AiHttpClientConfiguration;
import com.knowflow.api.config.AiServiceProperties;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class JavaPythonHealthIntegrationTest {
    @Autowired WebClient aiServiceWebClient;
    @LocalServerPort int javaPort;

    @Test void bothRealServicesAndRequestId() {
        Map<?,?> javaHealth = WebClient.create("http://127.0.0.1:" + javaPort)
            .get().uri("/actuator/health").retrieve().bodyToMono(Map.class).block(Duration.ofSeconds(5));
        assertEquals("UP", javaHealth.get("status"));
        var response = aiServiceWebClient.get().uri("/internal/v1/health")
            .header("X-Request-ID", "java-python-jp01-trace")
            .retrieve().toEntity(Map.class).block(Duration.ofSeconds(5));
        assertEquals(200, response.getStatusCode().value());
        assertEquals("UP", response.getBody().get("status"));
        assertEquals("0.2.0-draft.2", response.getBody().get("contract_version"));
        assertEquals("java-python-jp01-trace", response.getBody().get("request_id"));
        assertEquals("java-python-jp01-trace", response.getHeaders().getFirst("X-Request-ID"));
    }

    @Test void missingAndWrongCredentials() {
        var anonymous = aiServiceWebClient.mutate().defaultHeaders(h -> h.remove(HttpHeaders.AUTHORIZATION)).build();
        var missing = assertThrows(WebClientResponseException.class,
            () -> anonymous.get().uri("/internal/v1/health").retrieve().bodyToMono(String.class).block(Duration.ofSeconds(5)));
        assertEquals(401, missing.getStatusCode().value());
        assertTrue(missing.getResponseBodyAsString().contains("UNAUTHENTICATED"));
        var wrong = assertThrows(WebClientResponseException.class,
            () -> aiServiceWebClient.get().uri("/internal/v1/health")
                .headers(h -> h.setBearerAuth("fixture-only-wrong"))
                .retrieve().bodyToMono(String.class).block(Duration.ofSeconds(5)));
        assertEquals(401, wrong.getStatusCode().value());
    }

    @Test void routeAndMethodErrorsUseCandidateContract() {
        var missing = assertThrows(WebClientResponseException.class,
            () -> aiServiceWebClient.get().uri("/internal/missing").retrieve().bodyToMono(String.class).block(Duration.ofSeconds(5)));
        assertEquals(404, missing.getStatusCode().value());
        assertTrue(missing.getResponseBodyAsString().contains("ENDPOINT_UNAVAILABLE"));
        var method = assertThrows(WebClientResponseException.class,
            () -> aiServiceWebClient.post().uri("/internal/v1/health").retrieve().bodyToMono(String.class).block(Duration.ofSeconds(5)));
        assertEquals(405, method.getStatusCode().value());
        assertTrue(method.getResponseBodyAsString().contains("INVALID_REQUEST"));
        assertTrue(method.getHeaders().getFirst("Allow").contains("GET"));
    }

    private AnnotationConfigApplicationContext clientContext(String url) {
        var properties = new AiServiceProperties();
        properties.setBaseUrl(URI.create(url));
        properties.setInternalSharedSecret(System.getenv("KNOWFLOW_INTERNAL_SHARED_SECRET"));
        var context = new AnnotationConfigApplicationContext();
        context.registerBean(AiServiceProperties.class, () -> properties);
        context.register(AiHttpClientConfiguration.class);
        context.refresh();
        return context;
    }

    @Test void unreachableUsesBoundedRealTransport() {
        try (var ctx = clientContext(System.getenv("KNOWFLOW_JP01_UNREACHABLE_URL"))) {
            var client = ctx.getBean(WebClient.class);
            assertThrows(WebClientRequestException.class,
                () -> client.get().uri("/internal/v1/health").retrieve().bodyToMono(String.class).block(Duration.ofSeconds(5)));
        }
    }

    @Test void configuredResponseTimeoutIsBounded() {
        try (var ctx = clientContext(System.getenv("KNOWFLOW_JP01_SLOW_URL"))) {
            var client = ctx.getBean(WebClient.class);
            long start = System.nanoTime();
            assertThrows(WebClientRequestException.class,
                () -> client.get().uri("/").retrieve().bodyToMono(String.class).block(Duration.ofSeconds(35)));
            assertTrue(Duration.ofNanos(System.nanoTime() - start).toSeconds() <= 34);
        }
    }
}
