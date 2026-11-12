package com.knowflow.api.answer;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.knowflow.api.security.AuthenticatedUser;
import com.knowflow.api.security.RequestIdFilter;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class LlmModelControllerTest {
    @Test void serializesProbeMetadataWithoutCredentials() throws Exception {
        UUID owner = UUID.randomUUID(), id = UUID.randomUUID();
        var model = new LlmModelService.Model(id, "https://provider.example.test", "responses", "test", true,
                Instant.parse("2026-11-12T01:02:03Z"), "success");
        var service = mock(LlmModelService.class);
        when(service.list(owner)).thenReturn(new LlmModelService.Catalog(true, List.of(model)));
        var controller = new LlmModelController(service);
        var user = new AuthenticatedUser(owner, "owner@example.test", "token-secret");
        var input = new LlmModelService.Input(model.baseUrl(), model.protocol(), model.modelId(), "key-secret");
        when(service.save(owner, null, input, "filtered-id")).thenReturn(model);
        var request = new MockHttpServletRequest();
        request.setAttribute(RequestIdFilter.ATTRIBUTE, "filtered-id");
        request.addHeader("X-Request-ID", "untrusted-id");
        var mapper = new ObjectMapper().findAndRegisterModules()
                .disable(com.fasterxml.jackson.databind.SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
                .setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
        for (Object response : List.of(controller.list(user), controller.create(user, input, request))) {
            String json = mapper.writeValueAsString(response);
            assertTrue(json.contains("2026-11-12T01:02:03Z"));
            assertTrue(json.contains("last_probe_status"));
            assertFalse(json.contains("api_key"));
            assertFalse(json.contains("encrypted_key"));
            assertFalse(json.contains("secret"));
        }
        verify(service).save(owner, null, input, "filtered-id");
        var connection = mapper.valueToTree(new LlmModelService.Connection(id, model.baseUrl(), model.protocol(),
                model.modelId(), "key-secret", true));
        assertEquals(6, connection.size());
        assertFalse(connection.has("last_probe_at"));
        assertFalse(connection.has("last_probe_status"));
        var legacy = mapper.valueToTree(new LlmModelService.Model(id, model.baseUrl(), model.protocol(), "old", false,
                null, null));
        assertTrue(legacy.path("last_probe_at").isNull() || legacy.path("last_probe_at").isMissingNode());
    }
}
