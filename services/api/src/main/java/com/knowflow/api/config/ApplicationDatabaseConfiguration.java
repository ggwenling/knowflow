package com.knowflow.api.config;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("database")
public class ApplicationDatabaseConfiguration {
    @Bean
    DataSource applicationDataSource(ApplicationDatabaseProperties properties) {
        properties.requireValid();

        HikariConfig config = new HikariConfig();
        config.setPoolName("knowflow-application");
        config.setJdbcUrl(properties.getUrl());
        config.setUsername(properties.getUsername());
        config.setPassword(properties.getPassword());
        config.setMaximumPoolSize(8);
        config.setMinimumIdle(0);
        config.setConnectionTimeout(2_000);
        config.setInitializationFailTimeout(2_000);
        return new HikariDataSource(config);
    }
}
