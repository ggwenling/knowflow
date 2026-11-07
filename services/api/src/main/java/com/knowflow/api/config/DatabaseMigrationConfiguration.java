package com.knowflow.api.config;

import org.flywaydb.core.Flyway;
import org.flywaydb.core.api.configuration.FluentConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("db-migrate")
public class DatabaseMigrationConfiguration {
    @Bean(initMethod = "migrate")
    Flyway databaseMigrations(DatabaseMigrationProperties properties) {
        properties.requireValid();
        FluentConfiguration configuration = Flyway.configure()
                .dataSource(properties.getUrl(), properties.getUsername(), properties.getPassword())
                .defaultSchema("knowflow_flyway")
                .schemas("knowflow_flyway", "knowflow")
                .createSchemas(false)
                .cleanDisabled(true)
                .locations("classpath:db/migration");
        if (properties.getTarget() != null && !properties.getTarget().isBlank()) {
            configuration.target(properties.getTarget());
        }
        return configuration.load();
    }
}
