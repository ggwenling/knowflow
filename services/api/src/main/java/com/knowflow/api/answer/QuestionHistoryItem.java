package com.knowflow.api.answer;

import java.time.OffsetDateTime;
import java.util.UUID;

public record QuestionHistoryItem(UUID questionId, UUID knowledgeBaseId, String question,
                                  String status, OffsetDateTime createdAt,
                                  OffsetDateTime finishedAt) {}
