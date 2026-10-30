package com.knowflow.api.error;

import java.io.IOException;
import java.util.UUID;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.knowflow.api.security.RequestIdFilter;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;

@Component
public final class ApiErrorWriter {
    private final ObjectMapper objectMapper;

    public ApiErrorWriter(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public void write(HttpServletRequest request, HttpServletResponse response,
                      HttpStatusCode status, String code, String message) throws IOException {
        if (response.isCommitted()) {
            return;
        }
        Object value = request.getAttribute(RequestIdFilter.ATTRIBUTE);
        String requestId = value instanceof String id ? id : UUID.randomUUID().toString();
        response.setStatus(status.value());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding("UTF-8");
        objectMapper.writeValue(response.getOutputStream(),
                new ApiError(ApiError.CONTRACT_VERSION, requestId, code, message, false));
    }
}
