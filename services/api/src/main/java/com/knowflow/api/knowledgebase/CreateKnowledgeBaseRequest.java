package com.knowflow.api.knowledgebase;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateKnowledgeBaseRequest(
        @NotBlank String contractVersion,
        @NotBlank @Size(max = 200) String name) {
}
