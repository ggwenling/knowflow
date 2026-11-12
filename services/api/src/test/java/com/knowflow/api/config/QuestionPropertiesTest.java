package com.knowflow.api.config;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;
import static org.assertj.core.api.Assertions.assertThat;

class QuestionPropertiesTest {
    private final ApplicationContextRunner runner = new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(ValidationAutoConfiguration.class))
            .withUserConfiguration(PropertiesConfiguration.class);

    @Test void defaultsAndBoundariesAreValidated() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            var policy = context.getBean(QuestionProperties.class);
            assertThat(policy.getMaxConcurrentRequests()).isEqualTo(4);
            assertThat(policy.getCustomMaxConcurrentRequests()).isEqualTo(2);
        });
        for (int total : new int[]{1, 32}) {
            runner.withPropertyValues("knowflow.questions.max-concurrent-requests=" + total,
                    "knowflow.questions.custom-max-concurrent-requests=" + total)
                    .run(context -> assertThat(context).hasNotFailed());
        }
        for (String field : new String[]{"max-concurrent-requests", "custom-max-concurrent-requests"}) {
            for (String value : new String[]{"0", "33", "1.5", "true"}) {
                runner.withPropertyValues("knowflow.questions." + field + "=" + value)
                        .run(context -> assertThat(context).hasFailed());
            }
        }
    }

    @Test void customEnabledRejectsSingleTotalPermit() {
        runner.withPropertyValues("knowflow.questions.custom-enabled=true",
                "knowflow.questions.max-concurrent-requests=1").run(context -> {
                    assertThat(context).hasFailed();
                    Throwable cause = context.getStartupFailure();
                    StringBuilder messages = new StringBuilder();
                    while (cause != null) { messages.append(cause.getMessage()); cause = cause.getCause(); }
                    assertThat(messages.toString()).contains("LLM_ISOLATION_CONFIGURATION_INVALID");
                });
        runner.withPropertyValues("knowflow.questions.custom-enabled=true",
                "knowflow.questions.max-concurrent-requests=2").run(context -> assertThat(context).hasNotFailed());
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(QuestionProperties.class)
    static class PropertiesConfiguration {}
}
