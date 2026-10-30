package com.knowflow.api.indexing;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.Test;

class IndexBatchDigestTest {
    @Test
    void matchesTheSharedPythonGoldenBatchDigest() {
        LeaseContext lease = new LeaseContext(
                UUID.fromString("11111111-1111-4111-8111-111111111111"),
                UUID.fromString("22222222-2222-4222-8222-222222222222"),
                UUID.fromString("33333333-3333-4333-8333-333333333333"),
                UUID.fromString("44444444-4444-4444-8444-444444444444"),
                UUID.fromString("55555555-5555-4555-8555-555555555555"),
                UUID.fromString("66666666-6666-4666-8666-666666666666"),
                "pipeline-v1",
                UUID.fromString("77777777-7777-4777-8777-777777777777"), 3,
                "EXAMPLE_ONLY_NOT_A_USABLE_EXECUTION_TOKEN_1234567890");
        IndexBatchRequest.Chunk chunk = new IndexBatchRequest.Chunk(
                UUID.fromString("99999999-9999-4999-8999-999999999999"), 1,
                "Synthetic evidence.",
                "77b1c6bacf338d620e8aa02d40187be5163fbca4df6c04b33ab6af7c1c615c65",
                new IndexBatchRequest.Locator("text_range", null, 0, 19, "unicode_code_point"),
                java.util.Collections.nCopies(1024, BigDecimal.ZERO));
        IndexBatchRequest batch = new IndexBatchRequest("0.2.0-draft.5", "request-batch-1",
                lease, UUID.fromString("88888888-8888-4888-8888-888888888888"), 1,
                "0564303225ea440820c2aa05bd93ff31043e7ed80ee36965b16118dc037751bc",
                List.of(chunk));

        IndexBatchDigest.ValidatedBatch result = IndexBatchDigest.validateAndDigest(batch);

        assertThat(result.sha256()).isEqualTo(
                "0564303225ea440820c2aa05bd93ff31043e7ed80ee36965b16118dc037751bc");
        assertThat(result.normalizedEmbeddings().getFirst().getFirst())
                .isEqualTo(new BigDecimal("0.000000"));
    }

    @Test
    void rejectsTamperedTextAndNonFiniteOrOversizedNumericValues() {
        IndexBatchRequest valid = sample();
        IndexBatchRequest.Chunk original = valid.chunks().getFirst();
        IndexBatchRequest.Chunk tampered = new IndexBatchRequest.Chunk(original.chunkId(),
                original.sequenceNo(), "other text", original.textSha256(), original.locator(),
                original.embedding());
        assertThatThrownBy(() -> IndexBatchDigest.calculate(withChunk(valid, tampered)))
                .isInstanceOf(RuntimeException.class);

        var vector = new java.util.ArrayList<>(original.embedding());
        vector.set(0, new BigDecimal("1E+30"));
        IndexBatchRequest.Chunk huge = new IndexBatchRequest.Chunk(original.chunkId(),
                original.sequenceNo(), original.text(), original.textSha256(), original.locator(),
                vector);
        assertThatThrownBy(() -> IndexBatchDigest.calculate(withChunk(valid, huge)))
                .isInstanceOf(RuntimeException.class);
    }

    private static IndexBatchRequest sample() {
        LeaseContext lease = new LeaseContext(UUID.randomUUID(), UUID.randomUUID(), UUID.randomUUID(),
                UUID.randomUUID(), UUID.randomUUID(), UUID.randomUUID(), "pipeline-v1",
                UUID.randomUUID(), 1, "X".repeat(43));
        IndexBatchRequest.Chunk chunk = new IndexBatchRequest.Chunk(UUID.randomUUID(), 1, "text",
                "982d9e3eb996f559e633f4d194def3761d909f5a3b647d1a851fead67c32c9d1",
                new IndexBatchRequest.Locator("text_range", null, 0, 4, "unicode_code_point"),
                java.util.Collections.nCopies(1024, BigDecimal.ZERO));
        return new IndexBatchRequest("0.2.0-draft.5", "request-1", lease, UUID.randomUUID(),
                1, "0".repeat(64), List.of(chunk));
    }

    private static IndexBatchRequest withChunk(IndexBatchRequest batch,
                                               IndexBatchRequest.Chunk chunk) {
        return new IndexBatchRequest(batch.contractVersion(), batch.requestId(), batch.lease(),
                batch.batchId(), batch.batchSequence(), batch.batchSha256(), List.of(chunk));
    }
}
