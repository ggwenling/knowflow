package com.knowflow.api.answer;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;

public record QuestionHistoryDetail(String contractVersion, UUID questionId,
                                    UUID knowledgeBaseId, String question,
                                    String status, OffsetDateTime createdAt,
                                    OffsetDateTime finishedAt, String answer,
                                    Boolean hasAnswer, String failureCode,
                                    String embeddingModelProfileId,
                                    String llmModelProfileId,
                                    List<QuestionHistorySource> sources) {}
