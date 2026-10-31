package com.knowflow.api.answer;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.Set;
import java.util.UUID;

import org.junit.jupiter.api.Test;

class StreamCitationMapperTest {
    @Test
    void rewritesSplitMarkersWithTheSamePublicIdAsAnswerPersistence() {
        var mapper = new StreamCitationMapper(UUID.randomUUID());
        assertThat(mapper.feed("Evidence [src-")).isEqualTo("Evidence ");
        assertThat(mapper.feed("one] and [src-two]"))
                .isEqualTo("[" + mapper.publicId("src-one") + "] and [" + mapper.publicId("src-two") + "]");
        mapper.finish(Set.of("src-one", "src-two"));
    }

    @Test
    void rejectsUnknownUnclosedAndOversizedMarkers() {
        var unknown = new StreamCitationMapper(UUID.randomUUID());
        unknown.feed("[unknown]");
        assertThatThrownBy(() -> unknown.finish(Set.of())).isInstanceOf(IllegalStateException.class);
        var unclosed = new StreamCitationMapper(UUID.randomUUID());
        unclosed.feed("[source");
        assertThatThrownBy(() -> unclosed.finish(Set.of("source"))).isInstanceOf(IllegalStateException.class);
        var oversized = new StreamCitationMapper(UUID.randomUUID());
        assertThatThrownBy(() -> oversized.feed("[" + "a".repeat(129)))
                .isInstanceOf(IllegalStateException.class);
    }
}
