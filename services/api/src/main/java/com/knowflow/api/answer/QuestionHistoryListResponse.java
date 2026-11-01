package com.knowflow.api.answer;

import java.util.List;

public record QuestionHistoryListResponse(String contractVersion,
                                          List<QuestionHistoryItem> items,
                                          int limit, int offset, boolean hasMore) {}
