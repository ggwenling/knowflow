package com.knowflow.api.answer;

import java.util.List;

public record AnswerResponse(String contractVersion, String requestId, String answer,
                             boolean hasAnswer, List<SourceResponse> sources) {}
