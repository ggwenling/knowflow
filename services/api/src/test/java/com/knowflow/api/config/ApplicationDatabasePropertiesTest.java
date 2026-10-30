package com.knowflow.api.config;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

class ApplicationDatabasePropertiesTest {
    @Test
    void acceptsPostgresCredentialsSuppliedSeparatelyFromTheJdbcUrl() {
        var properties = new ApplicationDatabaseProperties();
        properties.setUrl("jdbc:postgresql://localhost:5432/knowflow");
        properties.setUsername("knowflow_app");
        properties.setPassword("test-only-password");

        assertThatCode(properties::requireValid).doesNotThrowAnyException();
    }

    @Test
    void rejectsMissingPasswordWithoutIncludingCredentialsInTheError() {
        var properties = new ApplicationDatabaseProperties();
        properties.setUrl("jdbc:postgresql://localhost:5432/knowflow");
        properties.setUsername("knowflow_app");

        assertThatThrownBy(properties::requireValid)
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("KNOWFLOW_DATABASE_PASSWORD is required");
    }

    @Test
    void rejectsCredentialsEmbeddedInJdbcUrl() {
        var properties = new ApplicationDatabaseProperties();
        properties.setUrl("jdbc:postgresql://localhost:5432/knowflow?user=unsafe");
        properties.setUsername("knowflow_app");
        properties.setPassword("test-only-password");

        assertThatThrownBy(properties::requireValid)
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("KNOWFLOW_DATABASE_URL must be a PostgreSQL JDBC URL without credentials");
    }
}
