package com.knowflow.api.answer;

import java.util.List;

public record AiAnswerStreamEvent(String contractVersion, String requestId, long sequence,
                                  String event, String delta, Boolean hasAnswer,
                                  List<AiAnswerResponse.AiSource> sources, String code,
                                  String message, Boolean retryable, ModelProfile modelProfile) {
    public AiAnswerStreamEvent(String contractVersion, String requestId, long sequence,
                               String event, String delta, Boolean hasAnswer,
                               List<AiAnswerResponse.AiSource> sources, String code,
                               String message, Boolean retryable) {
        this(contractVersion, requestId, sequence, event, delta, hasAnswer, sources,
                code, message, retryable, null);
    }
}
