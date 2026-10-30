package com.knowflow.api.storage;

import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Clock;
import java.time.Duration;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.HexFormat;
import java.util.Locale;
import java.util.regex.Pattern;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

/** Minimal path-style S3 client for the local MinIO-backed API. */
public final class S3ObjectStore {
    private static final Pattern BUCKET = Pattern.compile("[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]");
    private static final Pattern OBJECT_KEY = Pattern.compile("[A-Za-z0-9/_-]{1,512}");
    private static final DateTimeFormatter AMZ_DATE = DateTimeFormatter
            .ofPattern("yyyyMMdd'T'HHmmss'Z'", Locale.ROOT).withZone(ZoneOffset.UTC);
    private static final DateTimeFormatter DATE = DateTimeFormatter
            .ofPattern("yyyyMMdd", Locale.ROOT).withZone(ZoneOffset.UTC);
    private static final String SERVICE = "s3";
    private static final String REGION = "us-east-1";
    private static final String ALGORITHM = "AWS4-HMAC-SHA256";
    private final URI endpoint;
    private final String bucket;
    private final String accessKey;
    private final byte[] secretKey;
    private final Clock clock;
    private final HttpClient http;

    public S3ObjectStore(URI endpoint, String bucket, String accessKey, String secretKey) {
        this(endpoint, bucket, accessKey, secretKey, Clock.systemUTC());
    }

    S3ObjectStore(URI endpoint, String bucket, String accessKey, String secretKey, Clock clock) {
        if (endpoint == null || !("http".equals(endpoint.getScheme())
                || "https".equals(endpoint.getScheme()))
                || endpoint.getHost() == null || endpoint.getRawUserInfo() != null
                || (endpoint.getRawPath() != null && !endpoint.getRawPath().isEmpty()
                    && !"/".equals(endpoint.getRawPath()))
                || endpoint.getRawQuery() != null || endpoint.getRawFragment() != null) {
            throw new IllegalArgumentException("Object storage endpoint must be an HTTP origin");
        }
        if (bucket == null || !BUCKET.matcher(bucket).matches()
                || bucket.contains("..") || accessKey == null || accessKey.isBlank()
                || secretKey == null || secretKey.isBlank()) {
            throw new IllegalArgumentException("Object storage configuration is invalid");
        }
        this.endpoint = endpoint;
        this.bucket = bucket;
        this.accessKey = accessKey;
        this.secretKey = secretKey.getBytes(StandardCharsets.UTF_8);
        this.clock = clock;
        this.http = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .version(HttpClient.Version.HTTP_1_1)
                .build();
    }

    public void ensureBucket() {
        Response head = request("HEAD", bucketUri(), new byte[0], "application/octet-stream");
        if (head.status() == 200) {
            return;
        }
        if (head.status() != 404) {
            throw storageFailure(head.status());
        }
        Response create = request("PUT", bucketUri(), new byte[0], "application/octet-stream");
        if (create.status() != 200 && create.status() != 201) {
            throw storageFailure(create.status());
        }
    }

    public void putObject(String key, String contentType, byte[] contents) {
        URI uri = objectUri(key);
        Response response = request("PUT", uri, contents, contentType);
        if (response.status() != 200 && response.status() != 201) {
            throw storageFailure(response.status());
        }
    }

    public byte[] getObject(String key, int maximumBytes) {
        if (maximumBytes < 1) {
            throw new IllegalArgumentException("Object read limit must be positive");
        }
        URI uri = objectUri(key);
        SignedRequest signed = sign("GET", uri, new byte[0], "application/octet-stream");
        try {
            HttpResponse<InputStream> response = http.send(signed.request(),
                    HttpResponse.BodyHandlers.ofInputStream());
            if (response.statusCode() != 200) {
                closeQuietly(response.body());
                throw storageFailure(response.statusCode());
            }
            long declaredLength = response.headers().firstValueAsLong("Content-Length").orElse(-1);
            if (declaredLength > maximumBytes) {
                closeQuietly(response.body());
                throw new ObjectStoreException("Object exceeds the configured read limit");
            }
            try (InputStream body = response.body()) {
                byte[] contents = body.readNBytes(maximumBytes + 1);
                if (contents.length > maximumBytes || body.read() != -1) {
                    throw new ObjectStoreException("Object exceeds the configured read limit");
                }
                return contents;
            }
        } catch (IOException exception) {
            throw new ObjectStoreException("Object storage request failed", exception);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new ObjectStoreException("Object storage request was interrupted", exception);
        }
    }

    public void deleteObject(String key) {
        Response response = request("DELETE", objectUri(key), new byte[0], "application/octet-stream");
        if (response.status() != 204 && response.status() != 200 && response.status() != 404) {
            throw storageFailure(response.status());
        }
    }

    private Response request(String method, URI uri, byte[] payload, String contentType) {
        SignedRequest signed = sign(method, uri, payload, contentType);
        try {
            HttpResponse<byte[]> response = http.send(signed.request(),
                    HttpResponse.BodyHandlers.ofByteArray());
            return new Response(response.statusCode(), response.body());
        } catch (IOException exception) {
            throw new ObjectStoreException("Object storage request failed", exception);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new ObjectStoreException("Object storage request was interrupted", exception);
        }
    }

    private SignedRequest sign(String method, URI uri, byte[] payload, String contentType) {
        var now = clock.instant();
        String amzDate = AMZ_DATE.format(now);
        String shortDate = DATE.format(now);
        String host = uri.getRawAuthority().toLowerCase(Locale.ROOT);
        String payloadHash = sha256Hex(payload);
        String canonicalHeaders = "host:" + host + "\n"
                + "x-amz-content-sha256:" + payloadHash + "\n"
                + "x-amz-date:" + amzDate + "\n";
        String signedHeaders = "host;x-amz-content-sha256;x-amz-date";
        String canonicalRequest = method + "\n" + uri.getRawPath() + "\n\n"
                + canonicalHeaders + "\n" + signedHeaders + "\n" + payloadHash;
        String scope = shortDate + "/" + REGION + "/" + SERVICE + "/aws4_request";
        String stringToSign = ALGORITHM + "\n" + amzDate + "\n" + scope + "\n"
                + sha256Hex(canonicalRequest.getBytes(StandardCharsets.UTF_8));
        byte[] signingKey = hmac(hmac(hmac(hmac(
                concat("AWS4".getBytes(StandardCharsets.UTF_8), secretKey), shortDate), REGION), SERVICE),
                "aws4_request");
        String signature = HexFormat.of().formatHex(hmac(signingKey, stringToSign));
        String authorization = ALGORITHM + " Credential=" + accessKey + "/" + scope
                + ", SignedHeaders=" + signedHeaders + ", Signature=" + signature;

        HttpRequest.Builder builder = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(10))
                .header("x-amz-content-sha256", payloadHash)
                .header("x-amz-date", amzDate)
                .header("Authorization", authorization);
        if ("PUT".equals(method) && !uri.equals(bucketUri())) {
            builder.header("Content-Type", contentType);
        }
        HttpRequest.BodyPublisher body = HttpRequest.BodyPublishers.ofByteArray(payload);
        builder.method(method, body);
        return new SignedRequest(builder.build());
    }

    private URI bucketUri() {
        return URI.create(origin() + "/" + bucket);
    }

    private URI objectUri(String key) {
        if (key == null || !OBJECT_KEY.matcher(key).matches() || key.startsWith("/")
                || key.contains("//") || key.contains("../")) {
            throw new IllegalArgumentException("Object key is invalid");
        }
        return URI.create(origin() + "/" + bucket + "/" + key);
    }

    private String origin() {
        int port = endpoint.getPort();
        String host = endpoint.getHost().contains(":")
                ? "[" + endpoint.getHost() + "]" : endpoint.getHost();
        boolean defaultPort = port == -1 || ("http".equals(endpoint.getScheme()) && port == 80)
                || ("https".equals(endpoint.getScheme()) && port == 443);
        return endpoint.getScheme() + "://" + host + (defaultPort ? "" : ":" + port);
    }

    private static ObjectStoreException storageFailure(int status) {
        return new ObjectStoreException("Object storage returned HTTP " + status);
    }

    private static String sha256Hex(byte[] value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value));
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException("SHA-256 is unavailable", impossible);
        }
    }

    private static byte[] hmac(byte[] key, String value) {
        return hmac(key, value.getBytes(StandardCharsets.UTF_8));
    }

    private static byte[] hmac(byte[] key, byte[] value) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(key, "HmacSHA256"));
            return mac.doFinal(value);
        } catch (Exception exception) {
            throw new IllegalStateException("HMAC-SHA256 is unavailable", exception);
        }
    }

    private static byte[] concat(byte[] first, byte[] second) {
        byte[] result = new byte[first.length + second.length];
        System.arraycopy(first, 0, result, 0, first.length);
        System.arraycopy(second, 0, result, first.length, second.length);
        return result;
    }

    private static void closeQuietly(InputStream stream) {
        try {
            stream.close();
        } catch (IOException ignored) {
            // Ignore an already failing response stream.
        }
    }

    private record Response(int status, byte[] body) {}
    private record SignedRequest(HttpRequest request) {}
}
