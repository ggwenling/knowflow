package com.knowflow.api.config;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

import java.net.URI;
import java.time.Duration;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.knowflow.api.ai.AiInternalHealthClient;
import com.knowflow.api.ai.InternalHealth;
import org.junit.jupiter.api.Test;

/** Opt-in smoke against a separately running Python internal service. */
class RealPythonHealthSmokeTest {
    @Test
    void javaWebClientCallsTheConfiguredPythonHealthEndpoint() {
        String baseUrl = System.getenv("KNOWFLOW_REAL_AI_BASE_URL");
        String secret = System.getenv("KNOWFLOW_REAL_AI_SECRET");
        assumeTrue(baseUrl != null && !baseUrl.isBlank()
                        && secret != null && !secret.isBlank(),
                "Set KNOWFLOW_REAL_AI_BASE_URL and KNOWFLOW_REAL_AI_SECRET for real service smoke");

        AiServiceProperties properties = new AiServiceProperties();
        properties.setBaseUrl(URI.create(baseUrl));
        properties.setInternalSharedSecret(secret);
        ObjectMapper mapper = new ObjectMapper()
                .setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
        var webClient = new AiHttpClientConfiguration().aiServiceWebClient(properties, mapper);

        InternalHealth response = new AiInternalHealthClient(webClient)
                .check("java-python-real-health-smoke").block(Duration.ofSeconds(7));

        assertThat(response).isNotNull();
        assertThat(response.contract_version()).isEqualTo("0.2.0-draft.6");
        assertThat(response.status()).isEqualTo("UP");
        assertThat(response.request_id()).isEqualTo("java-python-real-health-smoke");
    }
}
