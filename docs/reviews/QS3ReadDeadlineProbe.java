import com.knowflow.api.storage.S3ObjectStore;
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.net.URI;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class QS3ReadDeadlineProbe {
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
                throw new AssertionError("Expected the stalled read to exceed its configured deadline");
            } catch (TimeoutException expected) {
                System.out.println("Q_S3_READ_STILL_BLOCKED_AFTER_MS="
                        + TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - start));
            }
            releaseBody.countDown();
            byte[] body = result.get(5, TimeUnit.SECONDS);
            System.out.println("Q_S3_LATE_READ_SUCCEEDED_BYTES=" + body.length);
        } finally {
            releaseBody.countDown();
            server.stop(0);
            executor.shutdownNow();
        }
    }
}
