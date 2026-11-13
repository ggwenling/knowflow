package com.knowflow.api.answer;

import java.nio.charset.StandardCharsets;
import java.util.HashSet;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Pattern;

/** Incrementally rewrites bounded citation markers; emitted text remains provisional until finish. */
final class StreamCitationMapper {
    private static final Pattern IDENTIFIER = Pattern.compile("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}");
    private final UUID questionId;
    private final StringBuilder marker = new StringBuilder();
    private final Set<String> referenced = new HashSet<>();
    private boolean inside;
    private int codePoints;

    StreamCitationMapper(UUID questionId) {
        this.questionId = questionId;
    }

    String feed(String fragment) {
        codePoints += fragment.codePointCount(0, fragment.length());
        if (codePoints > 16000) {
            throw new IllegalStateException("AI answer exceeds the contract limit");
        }
        StringBuilder output = new StringBuilder();
        for (int offset = 0; offset < fragment.length(); offset++) {
            char current = fragment.charAt(offset);
            if (!inside) {
                if (current == '[') {
                    inside = true;
                } else {
                    output.append(current);
                }
            } else if (current == '[') {
                output.append('[').append(marker);
                marker.setLength(0);
            } else if (current == ']') {
                String source = marker.toString();
                if (IDENTIFIER.matcher(source).matches()) {
                    referenced.add(source);
                    output.append('[').append(publicId(source)).append(']');
                } else {
                    output.append('[').append(source).append(']');
                }
                marker.setLength(0);
                inside = false;
            } else {
                marker.append(current);
                if (marker.length() > 128) {
                    output.append('[').append(marker);
                    marker.setLength(0);
                    inside = false;
                }
            }
        }
        return output.toString();
    }

    String finish(Set<String> acceptedSourceIds) {
        if (!acceptedSourceIds.equals(referenced)) {
            throw new IllegalStateException("AI citations do not match the verified sources");
        }
        return inside ? "[" + marker : "";
    }

    UUID publicId(String sourceId) {
        return UUID.nameUUIDFromBytes((questionId + ":" + sourceId).getBytes(StandardCharsets.UTF_8));
    }
}
