import com.knowflow.api.storage.S3ObjectStore;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpTimeoutException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

/** Repeat the original stalled-body probe against the fixed implementation. */
public class QS3ReadDeadlineAcceptance {
    public static void main(String[] args) throws Exception {
        var headersSent = new CountDownLatch(1);
        var releaseBody = new CountDownLatch(1);
        var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", exchange -> {
            try {
                exchange.sendResponseHeaders(200, 2);
                exchange.getResponseBody().write('a');
                exchange.getResponseBody().flush();
                headersSent.countDown();
                releaseBody.await();
                exchange.getResponseBody().write('b');
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            } finally {
                exchange.close();
            }
        });
        server.start();
        var executor = Executors.newSingleThreadExecutor();
        try {
            var store = new S3ObjectStore(URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort()), "probe-bucket", "synthetic-access", "synthetic-secret");
            long start = System.nanoTime();
            var result = executor.submit(() -> store.getObject("probe", 32));
            if (!headersSent.await(5, TimeUnit.SECONDS)) throw new AssertionError("No response headers");
            try {
                result.get(12, TimeUnit.SECONDS);
                throw new AssertionError("A stalled response should time out");
            } catch (ExecutionException expected) {
                Throwable cause = expected.getCause();
                while (cause != null && !(cause instanceof HttpTimeoutException)) cause = cause.getCause();
                if (cause == null) throw new AssertionError("Expected an HTTP timeout", expected);
                long elapsed = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - start);
                if (elapsed >= 12_000) throw new AssertionError("Read exceeded deadline tolerance");
                System.out.println("Q_S3_STALLED_BODY_TIMEOUT=PASS");
                System.out.println("Q_S3_TIMEOUT_AFTER_MS=" + elapsed);
            } catch (TimeoutException notFixed) {
                throw new AssertionError("The stalled body still blocks beyond the deadline", notFixed);
            }
        } finally {
            releaseBody.countDown();
            server.stop(0);
            executor.shutdownNow();
        }
    }
}
