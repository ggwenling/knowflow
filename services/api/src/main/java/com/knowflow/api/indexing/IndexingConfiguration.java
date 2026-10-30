package com.knowflow.api.indexing;

import com.knowflow.api.config.IndexingProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration(proxyBeanMethods = false)
@Profile("database")
@EnableScheduling
@EnableConfigurationProperties(IndexingProperties.class)
public class IndexingConfiguration {
}
