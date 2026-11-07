package com.knowflow.api.indexing;

import com.knowflow.api.config.IndexingProperties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration(proxyBeanMethods = false)
@Profile("database")
@EnableScheduling
@EnableConfigurationProperties(IndexingProperties.class)
public class IndexingConfiguration {
    private static final Logger LOGGER = LoggerFactory.getLogger(IndexingConfiguration.class);

    @Bean
    ApplicationRunner validateIndexingStartup(IndexingProperties properties) {
        return arguments -> {
            properties.requireValid();
            if (!properties.isSchedulerEnabled()) {
                LOGGER.warn("index_stage stage=startup outcome=disabled scheduler_enabled=false "
                        + "detail=queued indexing tasks and deletion outbox will not dispatch; "
                        + "set KNOWFLOW_INDEXING_SCHEDULER_ENABLED=true to enable");
            }
        };
    }
}
