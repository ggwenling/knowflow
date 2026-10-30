package com.knowflow.api.db;

import com.knowflow.api.config.DatabaseMigrationConfiguration;
import com.knowflow.api.config.DatabaseMigrationProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

public final class DatabaseMigrationApplication {
    private DatabaseMigrationApplication() {
    }

    public static void main(String[] args) {
        run(args);
    }

    public static void run(String[] args) {
        SpringApplication application = new SpringApplication(MigrationConfiguration.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setAdditionalProfiles("db-migrate");
        try (ConfigurableApplicationContext ignored = application.run(args)) {
            // Flyway runs during context initialization; closing the context ends the command.
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(DatabaseMigrationProperties.class)
    @Import(DatabaseMigrationConfiguration.class)
    static class MigrationConfiguration {
    }
}
