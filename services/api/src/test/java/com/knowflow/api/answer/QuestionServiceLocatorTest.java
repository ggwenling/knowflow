package com.knowflow.api.answer;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class QuestionServiceLocatorTest {
    private static final AiAnswerResponse.Locator CHUNK =
            new AiAnswerResponse.Locator("text_range", null, 10, 40, "unicode_code_point");

    @Test
    void acceptsTheChunkRangeAndNarrowerSubRanges() {
        assertThat(QuestionService.locatorWithinChunk(CHUNK, CHUNK)).isTrue();
        assertThat(QuestionService.locatorWithinChunk(
                new AiAnswerResponse.Locator("text_range", null, 18, 32,
                        "unicode_code_point"), CHUNK)).isTrue();
        assertThat(QuestionService.locatorWithinChunk(
                new AiAnswerResponse.Locator("text_range", null, 10, 20,
                        "unicode_code_point"), CHUNK)).isTrue();
    }

    @Test
    void rejectsRangesOutsideTheChunkOrWithADifferentShape() {
        assertThat(QuestionService.locatorWithinChunk(
                new AiAnswerResponse.Locator("text_range", null, 9, 20,
                        "unicode_code_point"), CHUNK)).isFalse();
        assertThat(QuestionService.locatorWithinChunk(
                new AiAnswerResponse.Locator("text_range", null, 30, 41,
                        "unicode_code_point"), CHUNK)).isFalse();
        assertThat(QuestionService.locatorWithinChunk(
                new AiAnswerResponse.Locator("text_range", null, 20, 20,
                        "unicode_code_point"), CHUNK)).isFalse();
        assertThat(QuestionService.locatorWithinChunk(
                new AiAnswerResponse.Locator("text_range", 1, 18, 32,
                        "unicode_code_point"), CHUNK)).isFalse();
        assertThat(QuestionService.locatorWithinChunk(
                new AiAnswerResponse.Locator("text_range", null, 18, 32,
                        "utf16_code_unit"), CHUNK)).isFalse();
        assertThat(QuestionService.locatorWithinChunk(
                new AiAnswerResponse.Locator("pdf_page", 2, null, null, null), CHUNK)).isFalse();
    }

    @Test
    void keepsPdfLocatorsAtChunkPageGranularity() {
        AiAnswerResponse.Locator page = new AiAnswerResponse.Locator("pdf_page", 2, null, null, null);
        assertThat(QuestionService.locatorWithinChunk(page, page)).isTrue();
        assertThat(QuestionService.locatorWithinChunk(
                new AiAnswerResponse.Locator("pdf_page", 3, null, null, null), page)).isFalse();
        assertThat(QuestionService.locatorWithinChunk(
                new AiAnswerResponse.Locator("pdf_page", 2, 3, 9, "unicode_code_point"), page))
                .isFalse();
    }
}
