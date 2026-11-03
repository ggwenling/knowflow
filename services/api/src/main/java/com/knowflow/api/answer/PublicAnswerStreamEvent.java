package com.knowflow.api.answer;

import java.util.List;

import com.fasterxml.jackson.annotation.JsonInclude;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record PublicAnswerStreamEvent(String contractVersion, String requestId, long sequence,
                                      String event, String delta, Boolean hasAnswer,
                                      List<AnswerStreamSource> sources, String code,
                                      String message, Boolean retryable, ModelProfile modelProfile) {
    public PublicAnswerStreamEvent(String contractVersion, String requestId, long sequence,
                                   String event, String delta, Boolean hasAnswer,
                                   List<AnswerStreamSource> sources, String code,
                                   String message, Boolean retryable) {
        this(contractVersion, requestId, sequence, event, delta, hasAnswer, sources,
                code, message, retryable, null);
    }
}
