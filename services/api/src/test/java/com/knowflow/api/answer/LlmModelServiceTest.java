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
    private final UUID owner = UUID.randomUUID();
    private final java.time.Instant checkedAt = java.time.Instant.parse("2026-11-12T01:02:03Z");
    private final Store store = new Store();
    private final AiAnswerClient ai = mock(AiAnswerClient.class);
    private final LlmModelService service = new LlmModelService(store, ai,
            new ModelRequestAdmission(new QuestionProperties()), true,
            Base64.getEncoder().encodeToString(new byte[32]));
    private final LlmModelService.Input input = new LlmModelService.Input(
            "https://provider.example.test", "responses", "test", "secret");

    private LlmModelService.Model save() {
        when(ai.probeModel(eq(owner), any(), eq("trusted-request")))
                .thenReturn(new AiAnswerClient.ModelProbe(true, "success", checkedAt));
        return service.save(owner, null, input, "trusted-request");
    }

    @Test void rejectsWrongUrlWithoutSaving() {
        for (String url : new String[]{"http://api.example.test", "https://localhost", "https://127.0.0.1",
                "https://[::1]", "https://u:p@api.example.test", "https://api.example.test:444",
                "https://api.example.test?q=secret", "https://api.example.test#secret"}) {
            var failure = assertThrows(ApiFailure.class, () -> service.save(owner, null,
                    new LlmModelService.Input(url, "responses", "test", "secret"), "trusted-request"));
            assertEquals("LLM_MODEL_URL_INVALID", failure.code());
        }
        assertTrue(store.rows.isEmpty());
        assertEquals(0, store.attempts);
        verifyNoInteractions(ai);
    }

    private void rejectsWithoutSaving(String code) {
        when(ai.probeModel(eq(owner), any(), anyString())).thenThrow(AiAnswerClient.probeFailure(code));
        assertEquals(code, assertThrows(ApiFailure.class,
                () -> service.save(owner, null, input, "trusted-request")).code());
        assertTrue(store.rows.isEmpty());
        assertEquals(1, store.attempts);
    }
    @Test void rejectsWrongKeyWithoutSaving() { rejectsWithoutSaving("LLM_MODEL_AUTH_FAILED"); }
    @Test void rejectsMissingModelWithoutSaving() { rejectsWithoutSaving("LLM_MODEL_NOT_FOUND"); }
    @Test void rejectsWrongEndpointWithoutSaving() { rejectsWithoutSaving("LLM_MODEL_ENDPOINT_NOT_FOUND"); }

    @Test void successfulProbePersistsToolsStatusAndTimestamp() {
        var model = save();
        assertEquals(checkedAt, model.lastProbeAt());
        assertEquals("success", model.lastProbeStatus());
        assertTrue(model.supportsTools());
        assertEquals(model, service.list(owner).models().getFirst());
        var revision = store.rows.get(model.id()).get("revision");
        var newer = checkedAt.plusSeconds(1);
        when(ai.probeModel(eq(owner), any(), anyString()))
                .thenReturn(new AiAnswerClient.ModelProbe(false, "success", newer));
        var changed = service.save(owner, model.id(), new LlmModelService.Input(
                input.baseUrl(), input.protocol(), "updated", ""), "trusted-request");
        assertEquals(newer, service.list(owner).models().getFirst().lastProbeAt());
        assertFalse(changed.supportsTools());
        assertNotEquals(revision, store.rows.get(model.id()).get("revision"));
        assertTrue(store.lastUpdate.contains("AND revision=?"));
        assertEquals("secret", service.resolve(owner, model.id()).apiKey());
    }

    @Test void failedEditKeepsPreviousEncryptedKeyRevisionAndProbeResult() {
        var model = save();
        var before = new java.util.HashMap<>(store.rows.get(model.id()));
        when(ai.probeModel(eq(owner), any(), anyString()))
                .thenThrow(AiAnswerClient.probeFailure("LLM_MODEL_AUTH_FAILED"));
        assertThrows(ApiFailure.class, () -> service.save(owner, model.id(),
                new LlmModelService.Input(input.baseUrl(), input.protocol(), "changed", "new-secret"), "trusted-request"));
        assertEquals(before, store.rows.get(model.id()));
        assertEquals(model, service.list(owner).models().getFirst());
        assertEquals("secret", service.resolve(owner, model.id()).apiKey());
    }

    @Test void encryptedKeyIsNotPlaintextAndCannotBeResolvedByAnotherOwner() {
        var model = save();
        byte[] ciphertext = (byte[]) store.rows.get(model.id()).get("encrypted_key");
        assertFalse(new String(ciphertext, java.nio.charset.StandardCharsets.UTF_8).contains("secret"));
        assertEquals("secret", service.resolve(owner, model.id()).apiKey());
        assertTrue(service.list(UUID.randomUUID()).models().isEmpty());
        assertEquals("RESOURCE_NOT_FOUND", assertThrows(ApiFailure.class,
                () -> service.resolve(UUID.randomUUID(), model.id())).code());
        // Simulate tampering with ownership: AES-GCM AAD still prevents decrypting.
        UUID other = UUID.randomUUID();
        store.rows.get(model.id()).put("owner_user_id", other);
        assertEquals("LLM_MODELS_DISABLED", assertThrows(ApiFailure.class,
                () -> service.resolve(other, model.id())).code());
    }

    @Test void probeLimitRejectsBeforeAiCall() {
        store.limited = true;
        assertEquals("LLM_MODEL_PROBE_LIMIT", assertThrows(ApiFailure.class,
                () -> service.save(owner, null, input, "trusted-request")).code());
        verifyNoInteractions(ai);
        assertTrue(store.rows.isEmpty());
    }

    @Test void changedUrlRequiresNewKey() {
        var model = save();
        clearInvocations(ai);
        for (var change : java.util.List.of(
                new LlmModelService.Input("https://other.example.test", input.protocol(), "test", ""),
                new LlmModelService.Input(input.baseUrl(), "chat_completions", "test", ""))) {
            assertEquals("INVALID_REQUEST", assertThrows(ApiFailure.class,
                    () -> service.save(owner, model.id(), change, "trusted-request")).code());
        }
        verifyNoInteractions(ai);
        assertEquals(model, service.list(owner).models().getFirst());
    }

    @Test void revisionConflictDoesNotOverwriteConcurrentSave() {
        var model = save();
        var before = new java.util.HashMap<>(store.rows.get(model.id()));
        store.conflict = true;
        assertEquals("LLM_MODEL_CONFLICT", assertThrows(ApiFailure.class,
                () -> service.save(owner, model.id(), input, "trusted-request")).code());
        assertEquals(before, store.rows.get(model.id()));
    }

    /** In-memory JDBC boundary: exercises SQL bindings and real AES-GCM without a database. */
    private static class Store extends JdbcTemplate {
        final java.util.Map<UUID, java.util.Map<String, Object>> rows = new java.util.HashMap<>();
        int attempts;
        boolean limited, conflict;
        String lastUpdate;
        @Override public int update(String sql, Object... args) {
            lastUpdate = sql;
            if (sql.contains("llm_model_probe_limits")) { attempts++; return limited ? 0 : 1; }
            String[] columns;
            java.util.Map<String, Object> row;
            if (sql.stripLeading().startsWith("INSERT")) {
                columns = new String[]{"id", "owner_user_id", "base_url", "protocol", "model_id", "encrypted_key",
                        "supports_tools", "revision", "last_probe_at", "last_probe_status"};
                assertEquals(columns.length, args.length);
                row = new java.util.HashMap<>();
                for (int i = 0; i < columns.length; i++) row.put(columns[i], args[i]);
                rows.put((UUID) args[0], row);
                return 1;
            }
            assertTrue(sql.stripLeading().startsWith("UPDATE"));
            row = rows.get(args[8]);
            if (conflict || row == null || !row.get("owner_user_id").equals(args[9])
                    || !row.get("revision").equals(args[10])) return 0;
            columns = new String[]{"base_url", "protocol", "model_id", "encrypted_key", "supports_tools", "revision",
                    "last_probe_at", "last_probe_status"};
            for (int i = 0; i < columns.length; i++) row.put(columns[i], args[i]);
            return 1;
        }
        @Override public <T> java.util.List<T> query(String sql, org.springframework.jdbc.core.RowMapper<T> mapper,
                                                    Object... args) {
            java.util.List<T> result = new java.util.ArrayList<>();
            for (var row : rows.values()) {
                UUID requestedOwner = (UUID) args[args.length - 1];
                if (!row.get("owner_user_id").equals(requestedOwner)
                        || args.length == 2 && !row.get("id").equals(args[0])) continue;
                var rs = mock(java.sql.ResultSet.class);
                try {
                    when(rs.getObject(anyString(), eq(UUID.class))).thenAnswer(call -> row.get(call.getArgument(0)));
                    when(rs.getString(anyString())).thenAnswer(call -> row.get(call.getArgument(0)));
                    when(rs.getBytes(anyString())).thenAnswer(call -> row.get(call.getArgument(0)));
                    when(rs.getBoolean(anyString())).thenAnswer(call -> row.get(call.getArgument(0)));
                    when(rs.getTimestamp(anyString())).thenAnswer(call -> row.get(call.getArgument(0)));
                    result.add(mapper.mapRow(rs, result.size()));
                } catch (java.sql.SQLException invalid) { throw new AssertionError(invalid); }
            }
            return result;
        }
    }
}
