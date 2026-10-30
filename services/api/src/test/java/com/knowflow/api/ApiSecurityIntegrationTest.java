package com.knowflow.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.UUID;
import java.util.ArrayList;
import java.util.concurrent.atomic.AtomicReference;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import com.knowflow.api.ai.AiInternalHealthClient;
import com.knowflow.api.security.RequestIdFilter;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;

@SpringBootTest(properties = "knowflow.ai.internal-shared-secret=integration-test-secret-value-32-bytes-minimum")
@AutoConfigureMockMvc
@Import(ApiSecurityIntegrationTest.TestEndpoints.class)
class ApiSecurityIntegrationTest {
    private static final String INTERNAL_SECRET =
            "integration-test-secret-value-32-bytes-minimum";
    private static final AtomicReference<String> RECEIVED_AUTHORIZATION = new AtomicReference<>();
    private static final AtomicReference<String> RECEIVED_REQUEST_ID = new AtomicReference<>();
    private static final HttpServer AI_STUB = startAiStub();

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private WebClient aiServiceWebClient;

    @Autowired
    private AiInternalHealthClient aiInternalHealthClient;

    @DynamicPropertySource
    static void aiServiceProperties(DynamicPropertyRegistry properties) {
        properties.add("knowflow.ai.base-url", () -> "http://127.0.0.1:"
                + AI_STUB.getAddress().getPort());
    }

    @AfterAll
    static void stopAiStub() {
        AI_STUB.stop(0);
    }

    @Test
    void healthIsPublicAndContainsNoEnvironmentDetails() throws Exception {
        var response = mockMvc.perform(get("/actuator/health"))
                .andExpect(status().isOk())
                .andExpect(header().exists(RequestIdFilter.HEADER))
                .andExpect(jsonPath("$.status").value("UP"))
                .andReturn();

        var body = com.fasterxml.jackson.databind.json.JsonMapper.builder().build()
                .readTree(response.getResponse().getContentAsByteArray());
        var fields = new ArrayList<String>();
        body.fieldNames().forEachRemaining(fields::add);
        assertThat(fields).containsExactly("status");
    }

    @Test
    void requestIdIsGeneratedAndSharedByErrorBodyAndHeader() throws Exception {
        var response = mockMvc.perform(get("/internal/test-auth")
                        .header(RequestIdFilter.HEADER, "caller-controlled-id"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.contract_version").value("0.2.0-draft.5"))
                .andExpect(jsonPath("$.code").value("UNAUTHENTICATED"))
                .andReturn();

        String responseId = response.getResponse().getHeader(RequestIdFilter.HEADER);
        UUID.fromString(responseId);
        assertThat(responseId).isNotEqualTo("caller-controlled-id");
        assertThat(response.getResponse().getContentAsString())
                .contains(responseId)
                .doesNotContain(INTERNAL_SECRET);
    }

    @Test
    void internalEndpointRejectsMissingAndIncorrectSecretsAndAcceptsTheConfiguredSecret()
            throws Exception {
        mockMvc.perform(get("/internal/test-auth"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("UNAUTHENTICATED"));
        mockMvc.perform(get("/internal/test-auth").header(HttpHeaders.AUTHORIZATION,
                        "Bearer wrong-test-secret"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("UNAUTHENTICATED"));
        mockMvc.perform(get("/internal/test-auth").header(HttpHeaders.AUTHORIZATION,
                        "Bearer " + INTERNAL_SECRET))
                .andExpect(status().isOk())
                .andExpect(content().json("{\"status\":\"authenticated\"}"));
    }

    @Test
    void authenticatedUnknownInternalRouteReturnsStandardizedNotFound() throws Exception {
        mockMvc.perform(get("/internal/not-found")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + INTERNAL_SECRET))
                .andExpect(status().isNotFound())
                .andExpect(header().exists(RequestIdFilter.HEADER))
                .andExpect(jsonPath("$.contract_version").value("0.2.0-draft.5"))
                .andExpect(jsonPath("$.code").value("ENDPOINT_UNAVAILABLE"))
                .andExpect(jsonPath("$.message").value("The requested endpoint is not available."));
    }

    @Test
    void unsupportedInternalMethodReturnsStandardizedMethodNotAllowed() throws Exception {
        mockMvc.perform(post("/internal/test-auth")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + INTERNAL_SECRET))
                .andExpect(status().isMethodNotAllowed())
                .andExpect(header().string(HttpHeaders.ALLOW, org.hamcrest.Matchers.containsString("GET")))
                .andExpect(header().exists(RequestIdFilter.HEADER))
                .andExpect(jsonPath("$.contract_version").value("0.2.0-draft.5"))
                .andExpect(jsonPath("$.code").value("INVALID_REQUEST"))
                .andExpect(jsonPath("$.message")
                        .value("The HTTP method is not supported for this endpoint."));
    }

    @Test
    void unsupportedAcceptTypePreservesNotAcceptableStatusAndFrameworkHeaders() throws Exception {
        mockMvc.perform(get("/internal/test-auth")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + INTERNAL_SECRET)
                        .accept(MediaType.APPLICATION_XML))
                .andExpect(status().isNotAcceptable())
                .andExpect(header().string(HttpHeaders.ACCEPT,
                        org.hamcrest.Matchers.containsString(MediaType.APPLICATION_JSON_VALUE)))
                .andExpect(header().exists(RequestIdFilter.HEADER))
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.contract_version").value("0.2.0-draft.5"))
                .andExpect(jsonPath("$.code").value("INVALID_REQUEST"))
                .andExpect(jsonPath("$.message").value("The requested response media type is not acceptable."));
    }

    @Test
    void apiRoutesAndOtherActuatorEndpointsRemainUnavailable() throws Exception {
        mockMvc.perform(get("/api/v1/me"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("UNAUTHENTICATED"));
        mockMvc.perform(get("/actuator/env"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("UNAUTHENTICATED"));
    }

    @Test
    void configuredAiClientSendsTheInternalSecretAndCallerRequestIdOnlyToTheLocalStub()
            throws Exception {
        RECEIVED_AUTHORIZATION.set(null);
        RECEIVED_REQUEST_ID.set(null);
        String value = aiServiceWebClient.get()
                .uri("/transport-probe")
                .header(RequestIdFilter.HEADER, "request-example-transport")
                .retrieve()
                .bodyToMono(String.class)
                .block(Duration.ofSeconds(3));

        assertThat(value).isEqualTo("local-test-response");
        assertThat(RECEIVED_AUTHORIZATION.get()).isEqualTo("Bearer " + INTERNAL_SECRET);
        assertThat(RECEIVED_REQUEST_ID.get()).isEqualTo("request-example-transport");
    }

    @Test
    void internalHealthClientChecksVersionStatusAndRequestIdAgainstTheLocalStub() {
        RECEIVED_AUTHORIZATION.set(null);
        RECEIVED_REQUEST_ID.set(null);

        var response = aiInternalHealthClient.check("request-health-integration")
                .block(Duration.ofSeconds(3));

        assertThat(response).isNotNull();
        assertThat(response.contract_version()).isEqualTo("0.2.0-draft.5");
        assertThat(response.status()).isEqualTo("UP");
        assertThat(response.request_id()).isEqualTo("request-health-integration");
        assertThat(RECEIVED_AUTHORIZATION.get()).isEqualTo("Bearer " + INTERNAL_SECRET);
        assertThat(RECEIVED_REQUEST_ID.get()).isEqualTo("request-health-integration");
    }

    private static HttpServer startAiStub() {
        try {
            HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            server.createContext("/transport-probe", ApiSecurityIntegrationTest::respondFromStub);
            server.createContext("/internal/v1/health", ApiSecurityIntegrationTest::respondHealth);
            server.start();
            return server;
        } catch (IOException exception) {
            throw new ExceptionInInitializerError(exception);
        }
    }

    private static void respondFromStub(HttpExchange exchange) throws IOException {
        RECEIVED_AUTHORIZATION.set(exchange.getRequestHeaders().getFirst(HttpHeaders.AUTHORIZATION));
        RECEIVED_REQUEST_ID.set(exchange.getRequestHeaders().getFirst(RequestIdFilter.HEADER));
        byte[] body = "local-test-response".getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(200, body.length);
        try (var output = exchange.getResponseBody()) {
            output.write(body);
        }
    }

    private static void respondHealth(HttpExchange exchange) throws IOException {
        RECEIVED_AUTHORIZATION.set(exchange.getRequestHeaders().getFirst(HttpHeaders.AUTHORIZATION));
        String requestId = exchange.getRequestHeaders().getFirst(RequestIdFilter.HEADER);
        RECEIVED_REQUEST_ID.set(requestId);
        String body = "{\"contract_version\":\"0.2.0-draft.5\",\"status\":\"UP\","
                + "\"request_id\":\"" + requestId + "\"}";
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8");
        exchange.sendResponseHeaders(200, bytes.length);
        try (var output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class TestEndpoints {
        @Bean
        InternalTestEndpoint internalTestEndpoint() {
            return new InternalTestEndpoint();
        }
    }

    @RestController
    static class InternalTestEndpoint {
        @GetMapping("/internal/test-auth")
        java.util.Map<String, String> authProbe() {
            return java.util.Map.of("status", "authenticated");
        }
    }
}
