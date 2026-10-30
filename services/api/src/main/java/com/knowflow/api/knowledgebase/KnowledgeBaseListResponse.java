package com.knowflow.api.knowledgebase;

import java.util.List;

public record KnowledgeBaseListResponse(
        String contractVersion,
        List<KnowledgeBaseResponse> items,
        int limit,
        int offset,
        boolean hasMore) {
}
