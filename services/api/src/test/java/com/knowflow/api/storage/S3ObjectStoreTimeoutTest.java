package com.knowflow.api.storage;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpTimeoutException;
import java.time.Clock;
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.Test;

class S3ObjectStoreTimeoutTest {
    @Test
    void configuredTimeoutCoversTheEntireObjectBodyRead() throws Exception {
        CountDownLatch bodyStarted = new CountDownLatch(1);
        var executor = Executors.newSingleThreadExecutor();
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.setExecutor(executor);
        server.createContext("/test-bucket/slow-object", exchange -> {
            try {
                exchange.sendResponseHeaders(200, 2);
                exchange.getResponseBody().write('a');
                exchange.getResponseBody().flush();
                bodyStarted.countDown();
                Thread.sleep(2_000);
                exchange.getResponseBody().write('b');
                exchange.getResponseBody().flush();
            } catch (IOException ignored) {
                // The client closes the timed-out response.
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            } finally {
                exchange.close();
            }
        });
        server.start();
        try {
            var store = new S3ObjectStore(URI.create("http://127.0.0.1:" + server.getAddress().getPort()),
                    "test-bucket", "test-access", "test-secret", Clock.systemUTC(),
                    Duration.ofMillis(400));
            long started = System.nanoTime();
            ObjectStoreException failure = null;
            try {
                store.getObject("slow-object", 16);
            } catch (ObjectStoreException expected) {
                failure = expected;
            }
            long elapsedMillis = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - started);

            assertThat(failure).isNotNull().hasMessage("Object storage request failed");
            assertThat(hasTimeoutCause(failure)).isTrue();
            assertThat(bodyStarted.await(1, TimeUnit.SECONDS)).isTrue();
            assertThat(elapsedMillis).isLessThan(1_500);
        } finally {
            server.stop(0);
            executor.shutdownNow();
        }
    }

    private static boolean hasTimeoutCause(Throwable failure) {
        for (Throwable current = failure; current != null; current = current.getCause()) {
            if (current instanceof HttpTimeoutException) {
                return true;
            }
        }
        return false;
    }
}
