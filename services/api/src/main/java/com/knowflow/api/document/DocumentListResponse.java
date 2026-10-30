package com.knowflow.api.document;

import java.util.List;

public record DocumentListResponse(
        String contractVersion,
        List<DocumentResponse> items,
        int limit,
        int offset,
        boolean hasMore) {}
