package com.knowflow.api.config;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

class DatabaseMigrationPropertiesTest {
    @Test
    void acceptsPostgresUrlWithCredentialsSeparatedFromTheUrl() {
        DatabaseMigrationProperties properties = new DatabaseMigrationProperties();
        properties.setUrl("jdbc:postgresql://localhost:5432/knowflow?sslmode=require");
        properties.setUsername("knowflow_migrator");
        properties.setPassword("test-only-password");

        properties.requireValid();
    }

    @Test
    void rejectsMissingCredentialsAndCredentialsEmbeddedInTheUrlWithoutEchoingThem() {
        DatabaseMigrationProperties properties = new DatabaseMigrationProperties();
        properties.setUrl("jdbc:postgresql://localhost:5432/knowflow?password=never-log-this");
        properties.setUsername("knowflow_migrator");
        properties.setPassword("separate-test-password");

        assertThatThrownBy(properties::requireValid)
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("without credentials")
                .hasMessageNotContaining("never-log-this")
                .hasMessageNotContaining("separate-test-password");

        properties.setUrl("jdbc:postgresql://localhost:5432/knowflow");
        properties.setPassword("");
        assertThatThrownBy(properties::requireValid)
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("KNOWFLOW_MIGRATION_DATABASE_PASSWORD")
                .hasMessageNotContaining("never-log-this")
                .hasMessageNotContaining("separate-test-password");
    }
}
