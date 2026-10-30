package com.knowflow.api.config;

import org.flywaydb.core.Flyway;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("db-migrate")
public class DatabaseMigrationConfiguration {
    @Bean(initMethod = "migrate")
    Flyway databaseMigrations(DatabaseMigrationProperties properties) {
        properties.requireValid();
        return Flyway.configure()
                .dataSource(properties.getUrl(), properties.getUsername(), properties.getPassword())
                .defaultSchema("knowflow_flyway")
                .schemas("knowflow_flyway", "knowflow")
                .createSchemas(false)
                .cleanDisabled(true)
                .locations("classpath:db/migration")
                .load();
    }
}
