package com.knowflow.api.answer;

import java.util.UUID;

public record PublicQuestion(String question, UUID llmModelId) {
    public PublicQuestion(String question) { this(question, null); }
}
