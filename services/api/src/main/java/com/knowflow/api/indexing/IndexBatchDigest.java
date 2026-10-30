package com.knowflow.api.indexing;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.List;
import java.util.Set;
import java.util.regex.Pattern;

import com.knowflow.api.error.ApiFailure;

/** Implements contracts/index_batch_hash.py byte-for-byte. */
public final class IndexBatchDigest {
    private static final Pattern SHA256 = Pattern.compile("[a-f0-9]{64}");
    private static final int EMBEDDING_DIMENSIONS = 1024;

    private IndexBatchDigest() {}

    public static ValidatedBatch validateAndDigest(IndexBatchRequest batch) {
        if (batch == null || batch.batchSha256() == null
                || !SHA256.matcher(batch.batchSha256()).matches()) {
            throw ApiFailure.invalidRequest();
        }
        ValidatedBatch calculated = calculate(batch);
        if (!calculated.sha256().equals(batch.batchSha256())) {
            throw ApiFailure.invalidRequest();
        }
        return calculated;
    }

    public static ValidatedBatch calculate(IndexBatchRequest batch) {
        if (batch == null || batch.lease() == null || batch.batchId() == null
                || batch.batchSequence() == null || batch.batchSequence() < 1
                || batch.chunks() == null || batch.chunks().isEmpty()
                || batch.chunks().size() > 32) {
            throw ApiFailure.invalidRequest();
        }
        List<String> fields = new ArrayList<>();
        LeaseContext lease = batch.lease();
        if (lease.taskId() == null || lease.ownerId() == null || lease.knowledgeBaseId() == null
                || lease.documentId() == null || lease.contentVersionId() == null
                || lease.indexVersionId() == null || lease.leaseId() == null
                || lease.fencing() < 1) {
            throw ApiFailure.invalidRequest();
        }
        fields.add(lease.taskId().toString());
        fields.add(lease.ownerId().toString());
        fields.add(lease.knowledgeBaseId().toString());
        fields.add(lease.documentId().toString());
        fields.add(lease.contentVersionId().toString());
        fields.add(lease.indexVersionId().toString());
        fields.add(lease.leaseId().toString());
        fields.add(Long.toString(lease.fencing()));
        fields.add(batch.batchId().toString());
        fields.add(Integer.toString(batch.batchSequence()));
        fields.add(Integer.toString(batch.chunks().size()));

        int previousSequence = 0;
        Set<java.util.UUID> chunkIds = new HashSet<>();
        List<List<BigDecimal>> normalizedVectors = new ArrayList<>(batch.chunks().size());
        for (IndexBatchRequest.Chunk chunk : batch.chunks()) {
            if (chunk == null || chunk.chunkId() == null || chunk.sequenceNo() == null
                    || chunk.sequenceNo() < 1 || chunk.text() == null || chunk.text().isEmpty()
                    || chunk.text().codePointCount(0, chunk.text().length()) > 800
                    || !validUnicode(chunk.text())
                    || chunk.textSha256() == null || !SHA256.matcher(chunk.textSha256()).matches()
                    || !chunkIds.add(chunk.chunkId())) {
                throw ApiFailure.invalidRequest();
            }
            if (previousSequence != 0 && chunk.sequenceNo() != previousSequence + 1) {
                throw ApiFailure.invalidRequest();
            }
            previousSequence = chunk.sequenceNo();
            String actualTextHash = sha256(utf8(chunk.text()));
            if (!actualTextHash.equals(chunk.textSha256())) {
                throw ApiFailure.invalidRequest();
            }
            fields.add(chunk.chunkId().toString());
            fields.add(Integer.toString(chunk.sequenceNo()));
            fields.add(chunk.textSha256());
            appendLocator(fields, chunk.locator());
            if (chunk.embedding() == null || chunk.embedding().size() != EMBEDDING_DIMENSIONS) {
                throw ApiFailure.invalidRequest();
            }
            List<BigDecimal> normalized = new ArrayList<>(EMBEDDING_DIMENSIONS);
            for (BigDecimal raw : chunk.embedding()) {
                if (raw == null || raw.precision() > 128
                        || raw.precision() - raw.scale() > 22) {
                    throw ApiFailure.invalidRequest();
                }
                BigDecimal value;
                if (raw.scale() > 128 && raw.precision() - raw.scale() < -7) {
                    value = BigDecimal.ZERO.setScale(6);
                } else {
                    try {
                        value = raw.setScale(6, RoundingMode.HALF_EVEN);
                    } catch (ArithmeticException | NumberFormatException invalidNumber) {
                        throw ApiFailure.invalidRequest();
                    }
                }
                if (value.signum() == 0) {
                    value = BigDecimal.ZERO.setScale(6);
                }
                normalized.add(value);
                fields.add(value.toPlainString());
            }
            normalizedVectors.add(List.copyOf(normalized));
        }
        String digest = sha256(canonicalBytes(fields));
        return new ValidatedBatch(digest, List.copyOf(normalizedVectors));
    }

    private static void appendLocator(List<String> fields, IndexBatchRequest.Locator locator) {
        if (locator == null || locator.kind() == null) {
            throw ApiFailure.invalidRequest();
        }
        fields.add(locator.kind());
        if ("pdf_page".equals(locator.kind())) {
            if (locator.page() == null || locator.page() < 1 || locator.start() != null
                    || locator.end() != null || locator.unit() != null) {
                throw ApiFailure.invalidRequest();
            }
            fields.add(Integer.toString(locator.page()));
        } else if ("text_range".equals(locator.kind())) {
            if (locator.page() != null || locator.start() == null || locator.start() < 0
                    || locator.end() == null || locator.end() <= locator.start()
                    || !"unicode_code_point".equals(locator.unit())) {
                throw ApiFailure.invalidRequest();
            }
            fields.add(Integer.toString(locator.start()));
            fields.add(Integer.toString(locator.end()));
            fields.add(locator.unit());
        } else {
            throw ApiFailure.invalidRequest();
        }
    }

    private static byte[] canonicalBytes(List<String> fields) {
        var output = new java.io.ByteArrayOutputStream();
        output.writeBytes("knowflow-index-batch-v1\n".getBytes(StandardCharsets.UTF_8));
        for (String field : fields) {
            byte[] encoded = field.getBytes(StandardCharsets.UTF_8);
            output.writeBytes(Integer.toString(encoded.length).getBytes(StandardCharsets.US_ASCII));
            output.write(':');
            output.writeBytes(encoded);
            output.write('\n');
        }
        return output.toByteArray();
    }

    private static boolean validUnicode(String value) {
        try {
            utf8(value);
            return true;
        } catch (IllegalArgumentException invalidUnicode) {
            return false;
        }
    }

    private static byte[] utf8(String value) {
        try {
            var encoded = StandardCharsets.UTF_8.newEncoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .encode(java.nio.CharBuffer.wrap(value));
            byte[] bytes = new byte[encoded.remaining()];
            encoded.get(bytes);
            return bytes;
        } catch (CharacterCodingException malformed) {
            throw new IllegalArgumentException("Text is not valid Unicode", malformed);
        }
    }

    private static String sha256(byte[] value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value));
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException("SHA-256 is unavailable", impossible);
        }
    }

    public record ValidatedBatch(String sha256, List<List<BigDecimal>> normalizedEmbeddings) {}
}
