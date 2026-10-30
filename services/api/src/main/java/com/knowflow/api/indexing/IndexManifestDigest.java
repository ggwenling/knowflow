package com.knowflow.api.indexing;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.List;
import java.util.UUID;

public final class IndexManifestDigest {
    private IndexManifestDigest() {}

    public static String calculate(ManifestIdentity identity, int chunkCount, int embeddingCount,
                                   List<BatchIdentity> batches) {
        var output = new java.io.ByteArrayOutputStream();
        output.writeBytes("knowflow-index-manifest-v1\n".getBytes(StandardCharsets.UTF_8));
        List<String> values = new java.util.ArrayList<>();
        values.add(identity.taskId().toString());
        values.add(identity.ownerId().toString());
        values.add(identity.knowledgeBaseId().toString());
        values.add(identity.documentId().toString());
        values.add(identity.contentVersionId().toString());
        values.add(identity.indexVersionId().toString());
        values.add(identity.pipelineProfileId());
        values.add(identity.embeddingModelProfileId());
        values.add(Integer.toString(identity.embeddingDimensions()));
        values.add(Integer.toString(chunkCount));
        values.add(Integer.toString(embeddingCount));
        values.add(Integer.toString(batches.size()));
        for (BatchIdentity batch : batches) {
            values.add(Integer.toString(batch.sequence()));
            values.add(batch.batchId().toString());
            values.add(batch.sha256());
            values.add(Integer.toString(batch.chunkCount()));
        }
        for (String value : values) {
            byte[] encoded = value.getBytes(StandardCharsets.UTF_8);
            output.writeBytes(Integer.toString(encoded.length).getBytes(StandardCharsets.US_ASCII));
            output.write(':');
            output.writeBytes(encoded);
            output.write('\n');
        }
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(output.toByteArray()));
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException("SHA-256 is unavailable", impossible);
        }
    }

    public record ManifestIdentity(UUID taskId, UUID ownerId, UUID knowledgeBaseId,
                                   UUID documentId, UUID contentVersionId, UUID indexVersionId,
                                   String pipelineProfileId, String embeddingModelProfileId,
                                   int embeddingDimensions) {}

    public record BatchIdentity(int sequence, UUID batchId, String sha256, int chunkCount) {}
}
