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
    void rejectsUnknownOrMissingSourceMarkers() {
        var unknown = new StreamCitationMapper(UUID.randomUUID());
        unknown.feed("[unknown]");
        assertThatThrownBy(() -> unknown.finish(Set.of())).isInstanceOf(IllegalStateException.class);
        var unclosed = new StreamCitationMapper(UUID.randomUUID());
        unclosed.feed("[source");
        assertThatThrownBy(() -> unclosed.finish(Set.of("source"))).isInstanceOf(IllegalStateException.class);
    }

    @Test
    void preservesLiteralBracketsAndRewritesOnlyIdentifiers() {
        var mapper = new StreamCitationMapper(UUID.randomUUID());
        assertThat(mapper.feed("范围 [2,3) [src-")).isEqualTo("范围 [2,3) ");
        assertThat(mapper.feed("one] 以及 [中文] [未闭合"))
                .isEqualTo("[" + mapper.publicId("src-one") + "] 以及 [中文] ");
        assertThat(mapper.finish(Set.of("src-one"))).isEqualTo("[未闭合");
        var oversized = new StreamCitationMapper(UUID.randomUUID());
        String literal = "[" + "a".repeat(129) + "]";
        assertThat(oversized.feed(literal)).isEqualTo(literal);
        assertThat(oversized.finish(Set.of())).isEmpty();
    }
}
