package com.knowflow.api.answer;

import java.util.Base64;
import java.util.UUID;
import com.knowflow.api.config.QuestionProperties;
import com.knowflow.api.error.ApiFailure;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class LlmModelServiceTest {
    @Test void probeSharesCustomCapacity() {
        var properties = new QuestionProperties();
        properties.setMaxConcurrentRequests(3);
        var admission = new ModelRequestAdmission(properties);
        var jdbc = mock(JdbcTemplate.class);
        var ai = mock(AiAnswerClient.class);
        when(jdbc.update(anyString(), any(Object[].class))).thenReturn(1);
        var models = new LlmModelService(jdbc, ai, admission, true,
                Base64.getEncoder().encodeToString(new byte[32]));
        try (var answer = admission.tryAcquire(true); var probe = admission.tryAcquire(true)) {
            assertEquals("RESOURCE_LIMIT", assertThrows(ApiFailure.class, () -> models.save(UUID.randomUUID(), null,
                    new LlmModelService.Input("https://provider.example.test", "responses", "test", "secret"),
                    "trusted-request")).code());
            verifyNoInteractions(ai);
            try (var builtin = admission.tryAcquire(false)) { assertNotNull(builtin); }
        }
        verify(jdbc, times(1)).update(anyString(), any(Object[].class));
    }

    @Test void failedProbeReleasesAdmissionWithoutSaving() {
        var admission = new ModelRequestAdmission(new QuestionProperties());
        var jdbc = mock(JdbcTemplate.class);
        var ai = mock(AiAnswerClient.class);
        when(jdbc.update(anyString(), any(Object[].class))).thenReturn(1);
        when(ai.probeModel(any(), any(), eq("trusted-request"))).thenThrow(ApiFailure.modelBusy());
        var models = new LlmModelService(jdbc, ai, admission, true,
                Base64.getEncoder().encodeToString(new byte[32]));
        assertThrows(ApiFailure.class, () -> models.save(UUID.randomUUID(), null,
                new LlmModelService.Input("https://provider.example.test", "responses", "test", "secret"),
                "trusted-request"));
        verify(jdbc, times(1)).update(anyString(), any(Object[].class));
        try (var first = admission.tryAcquire(true); var second = admission.tryAcquire(true)) { assertNotNull(second); }
    }
}
