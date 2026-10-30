package com.knowflow.api.config;

import com.knowflow.api.storage.S3ObjectStore;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("database & storage")
@EnableConfigurationProperties(ObjectStorageProperties.class)
public class ObjectStorageConfiguration {
    @Bean
    S3ObjectStore objectStore(ObjectStorageProperties properties) {
        properties.requireValid();
        return new S3ObjectStore(properties.getEndpoint(), properties.getBucket(),
                properties.getAccessKey(), properties.getSecretKey(),
                properties.getRequestTimeout());
    }

    @Bean
    ApplicationRunner ensureObjectBucket(S3ObjectStore objectStore) {
        return arguments -> objectStore.ensureBucket();
    }
}
