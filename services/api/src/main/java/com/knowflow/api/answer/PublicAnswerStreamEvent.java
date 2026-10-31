package com.knowflow.api.answer;

import java.util.List;

public record PublicAnswerStreamEvent(String contractVersion, String requestId, long sequence,
                                      String event, String delta, Boolean hasAnswer,
                                      List<AnswerStreamSource> sources, String code,
                                      String message, Boolean retryable) {}
