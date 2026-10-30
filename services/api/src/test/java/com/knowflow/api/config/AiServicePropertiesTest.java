package com.knowflow.api.config;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.ArrayList;
import java.util.List;
import java.util.StringJoiner;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class AiServicePropertiesTest {
    private static final String VALID_SECRET = "test-secret-that-is-at-least-32-characters";

    private final ApplicationContextRunner contextRunner = new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(ValidationAutoConfiguration.class))
            .withUserConfiguration(PropertiesConfiguration.class);

    @Test
    void refusesToStartWithoutTheInternalSharedSecret() {
        contextRunner.withPropertyValues("knowflow.ai.base-url=http://localhost:8000")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(causeMessages(context.getStartupFailure()))
                            .contains("internalSharedSecret")
                            .doesNotContain(VALID_SECRET);
                });
    }

    @Test
    void refusesShortSecretsAndBaseUrlsWithEmbeddedCredentials() {
        contextRunner.withPropertyValues(
                        "knowflow.ai.base-url=http://user:password@localhost:8000",
                        "knowflow.ai.internal-shared-secret=too-short")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(causeMessages(context.getStartupFailure()))
                            .doesNotContain("user:password", "too-short");
                });
    }

    @Test
    void acceptsAnHttpsBaseUrlAndSecretWithoutConnectingDuringStartup() {
        contextRunner.withPropertyValues(
                        "knowflow.ai.base-url=https://ai.example.invalid",
                        "knowflow.ai.internal-shared-secret=" + VALID_SECRET)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context.getBean(AiServiceProperties.class).getBaseUrl().getScheme())
                            .isEqualTo("https");
                });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(AiServiceProperties.class)
    static class PropertiesConfiguration {
    }

    private static String causeMessages(Throwable cause) {
        StringJoiner messages = new StringJoiner("\n");
        for (Throwable current = cause; current != null; current = current.getCause()) {
            messages.add(String.valueOf(current.getMessage()));
        }
        return messages.toString();
    }
}
