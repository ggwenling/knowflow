package com.knowflow.api.storage;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.wait.strategy.Wait;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
class S3ObjectStoreIntegrationTest {
    private static final String ACCESS_KEY = "knowflow-test-access";
    private static final String SECRET_KEY = "integration-test-secret-key-for-minio";
    private static final String IMAGE = "bitnamilegacy/minio:2025.4.22"
            + "@sha256:50cec18ac4184af4671a78aedd5554942c8ae105d51a465fa82037949046da01";

    @Container
    private static final GenericContainer<?> MINIO = new GenericContainer<>(
            DockerImageName.parse(IMAGE))
            .withEnv("MINIO_ROOT_USER", ACCESS_KEY)
            .withEnv("MINIO_ROOT_PASSWORD", SECRET_KEY)
            .withExposedPorts(9000)
            .waitingFor(Wait.forHttp("/minio/health/live")
                    .forPort(9000)
                    .forStatusCode(200)
                    .withStartupTimeout(Duration.ofSeconds(90)));

    @Test
    void signedPutGetAndDeleteAreIdempotentAgainstRealMinio() {
        S3ObjectStore store = store(ACCESS_KEY, SECRET_KEY);
        store.ensureBucket();
        store.ensureBucket();
        String key = "integration/" + UUID.randomUUID();
        byte[] source = "safe source bytes\nline two".getBytes(StandardCharsets.UTF_8);

        store.putObject(key, "text/plain; charset=utf-8", source);
        assertThat(store.getObject(key, 128)).containsExactly(source);
        store.deleteObject(key);
        store.deleteObject(key);
        assertThatThrownBy(() -> store.getObject(key, 128))
                .isInstanceOf(ObjectStoreException.class)
                .hasMessage("Object storage returned HTTP 404");
    }

    @Test
    void objectReadLimitIsEnforcedAndCredentialsAreNotIncludedInErrors() {
        S3ObjectStore store = store(ACCESS_KEY, SECRET_KEY);
        store.ensureBucket();
        String key = "limit/" + UUID.randomUUID();
        store.putObject(key, "application/octet-stream", new byte[128]);
        assertThatThrownBy(() -> store.getObject(key, 16))
                .isInstanceOf(ObjectStoreException.class)
                .hasMessage("Object exceeds the configured read limit");

        S3ObjectStore wrongCredentials = store(ACCESS_KEY, "wrong-secret-value-not-to-log");
        assertThatThrownBy(wrongCredentials::ensureBucket)
                .isInstanceOf(ObjectStoreException.class)
                .hasMessage("Object storage returned HTTP 403")
                .hasMessageNotContaining("wrong-secret-value-not-to-log");
    }

    @Test
    void objectKeysCannotEscapeTheConfiguredBucket() {
        S3ObjectStore store = store(ACCESS_KEY, SECRET_KEY);
        assertThatThrownBy(() -> store.getObject("../other-bucket/file", 64))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("Object key is invalid");
    }

    private static S3ObjectStore store(String accessKey, String secretKey) {
        return new S3ObjectStore(URI.create("http://" + MINIO.getHost() + ":"
                + MINIO.getMappedPort(9000)), "knowflow-test", accessKey, secretKey);
    }
}
