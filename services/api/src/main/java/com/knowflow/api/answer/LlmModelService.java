package com.knowflow.api.answer;

import java.net.URI;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Base64;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.UUID;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

import com.knowflow.api.error.ApiFailure;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service
@Profile("database")
public class LlmModelService {
    private static final Set<String> PROTOCOLS = Set.of("chat_completions", "responses", "anthropic_messages");
    private static final int NONCE_BYTES = 12;
    private final JdbcTemplate jdbc;
    private final AiAnswerClient ai;
    private final SecretKeySpec encryptionKey;
    private final SecureRandom random = new SecureRandom();

    public LlmModelService(JdbcTemplate jdbc, AiAnswerClient ai,
            @Value("${KNOWFLOW_CUSTOM_LLM_ENABLED:false}") boolean enabled,
            @Value("${KNOWFLOW_CUSTOM_LLM_ENCRYPTION_KEY:}") String encodedKey) {
        this.jdbc = jdbc;
        this.ai = ai;
        if (!enabled) {
            encryptionKey = null;
            return;
        }
        byte[] key;
        try {
            key = Base64.getDecoder().decode(encodedKey);
        } catch (IllegalArgumentException invalid) {
            throw new IllegalStateException("Invalid custom model encryption key");
        }
        if (key.length != 32) throw new IllegalStateException("Invalid custom model encryption key length");
        encryptionKey = new SecretKeySpec(key, "AES");
        java.util.Arrays.fill(key, (byte) 0);
    }

    Catalog list(UUID owner) {
        if (encryptionKey == null) return new Catalog(false, List.of());
        List<Model> models = jdbc.query("""
                SELECT id, base_url, protocol, model_id, supports_tools FROM knowflow.llm_models
                WHERE owner_user_id = ? ORDER BY model_id, base_url, id
                """, (row, index) -> model(row), owner);
        return new Catalog(true, models);
    }

    Model save(UUID owner, UUID id, Input input) {
        requireEnabled();
        Stored previous = id == null ? null : find(owner, id);
        UUID modelId = id == null ? UUID.randomUUID() : id;
        String url = normalizeUrl(input.baseUrl());
        String protocol = input.protocol();
        String model = input.modelId() == null ? "" : input.modelId().strip();
        if (protocol == null || !PROTOCOLS.contains(protocol) || !model.matches("[^\\p{C}\\s]{1,160}")) {
            throw ApiFailure.invalidRequest();
        }
        String key = input.apiKey();
        if ((key == null || key.isEmpty()) && previous != null
                && url.equals(previous.model().baseUrl()) && protocol.equals(previous.model().protocol())) {
            key = decrypt(owner, previous);
        }
        if (key == null || !key.matches("[!-~]{1,2048}")) throw ApiFailure.invalidRequest();
        reserveProbe(owner);
        boolean tools = ai.probeModel(new Connection(modelId, url, protocol, model, key, false));
        byte[] encrypted = encrypt(owner, modelId, key);
        UUID revision = UUID.randomUUID();
        try {
            if (previous == null) {
                jdbc.update("""
                        INSERT INTO knowflow.llm_models
                            (id, owner_user_id, base_url, protocol, model_id, encrypted_key, supports_tools, revision)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, modelId, owner, url, protocol, model, encrypted, tools, revision);
            } else if (jdbc.update("""
                    UPDATE knowflow.llm_models SET base_url=?, protocol=?, model_id=?, encrypted_key=?,
                        supports_tools=?, revision=? WHERE id=? AND owner_user_id=? AND revision=?
                    """, url, protocol, model, encrypted, tools, revision, modelId, owner, previous.revision()) == 0) {
                throw conflict();
            }
        } catch (DuplicateKeyException duplicate) {
            throw conflict();
        }
        return new Model(modelId, url, protocol, model, tools);
    }

    void delete(UUID owner, UUID id) {
        if (jdbc.update("DELETE FROM knowflow.llm_models WHERE id=? AND owner_user_id=?", id, owner) == 0) {
            throw ApiFailure.resourceNotFound();
        }
    }

    Connection resolve(UUID owner, UUID id) {
        if (id == null) return null;
        requireEnabled();
        Stored stored = find(owner, id);
        Model model = stored.model();
        return new Connection(id, model.baseUrl(), model.protocol(), model.modelId(), decrypt(owner, stored),
                model.supportsTools());
    }

    private Stored find(UUID owner, UUID id) {
        return jdbc.query("""
                SELECT id, base_url, protocol, model_id, supports_tools, encrypted_key, revision
                FROM knowflow.llm_models WHERE id=? AND owner_user_id=?
                """, (row, index) -> new Stored(model(row), row.getBytes("encrypted_key"),
                        row.getObject("revision", UUID.class)), id, owner).stream().findFirst()
                .orElseThrow(ApiFailure::resourceNotFound);
    }

    private static Model model(ResultSet row) throws SQLException {
        return new Model(row.getObject("id", UUID.class), row.getString("base_url"), row.getString("protocol"),
                row.getString("model_id"), row.getBoolean("supports_tools"));
    }

    private void reserveProbe(UUID owner) {
        int updated = jdbc.update("""
                INSERT INTO knowflow.llm_model_probe_limits AS limits VALUES (?, statement_timestamp(), 1)
                ON CONFLICT (owner_user_id) DO UPDATE SET
                    attempts = CASE WHEN limits.window_start <= statement_timestamp() - INTERVAL '1 minute'
                                    THEN 1 ELSE limits.attempts + 1 END,
                    window_start = CASE WHEN limits.window_start <= statement_timestamp() - INTERVAL '1 minute'
                                        THEN statement_timestamp() ELSE limits.window_start END
                WHERE limits.attempts < 5 OR limits.window_start <= statement_timestamp() - INTERVAL '1 minute'
                """, owner);
        if (updated == 0) throw new ApiFailure(HttpStatus.TOO_MANY_REQUESTS, "LLM_MODEL_PROBE_LIMIT",
                "Too many model checks. Try again in a minute.", true);
    }

    private void requireEnabled() {
        if (encryptionKey == null) throw new ApiFailure(HttpStatus.SERVICE_UNAVAILABLE, "LLM_MODELS_DISABLED",
                "Custom models are unavailable.");
    }

    private static ApiFailure conflict() {
        return new ApiFailure(HttpStatus.CONFLICT, "LLM_MODEL_CONFLICT", "The model already exists or has changed.");
    }

    static String normalizeUrl(String value) {
        if (value == null || value.length() > 1024) throw ApiFailure.invalidRequest();
        try {
            URI uri = URI.create(value.strip());
            String host = uri.getHost();
            if (!"https".equalsIgnoreCase(uri.getScheme()) || host == null || uri.getRawUserInfo() != null
                    || uri.getRawQuery() != null || uri.getRawFragment() != null
                    || (uri.getPort() != -1 && uri.getPort() != 443)
                    || !host.matches("(?i)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\\.)+[a-z][a-z0-9-]{0,62}")) {
                throw ApiFailure.invalidRequest();
            }
            return "https://" + host.toLowerCase(Locale.ROOT) + uri.normalize().getRawPath().replaceFirst("/+$", "");
        } catch (IllegalArgumentException invalid) {
            throw ApiFailure.invalidRequest();
        }
    }

    private byte[] encrypt(UUID owner, UUID id, String key) {
        byte[] nonce = new byte[NONCE_BYTES];
        random.nextBytes(nonce);
        byte[] encrypted = crypt(Cipher.ENCRYPT_MODE, owner, id, nonce, key.getBytes(StandardCharsets.UTF_8));
        return ByteBuffer.allocate(nonce.length + encrypted.length).put(nonce).put(encrypted).array();
    }

    private String decrypt(UUID owner, Stored stored) {
        ByteBuffer encrypted = ByteBuffer.wrap(stored.encryptedKey());
        byte[] nonce = new byte[NONCE_BYTES];
        encrypted.get(nonce);
        byte[] ciphertext = new byte[encrypted.remaining()];
        encrypted.get(ciphertext);
        return new String(crypt(Cipher.DECRYPT_MODE, owner, stored.model().id(), nonce, ciphertext),
                StandardCharsets.UTF_8);
    }

    private byte[] crypt(int mode, UUID owner, UUID id, byte[] nonce, byte[] bytes) {
        try {
            Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(mode, encryptionKey, new GCMParameterSpec(128, nonce));
            cipher.updateAAD((owner + ":" + id).getBytes(StandardCharsets.US_ASCII));
            return cipher.doFinal(bytes);
        } catch (GeneralSecurityException invalid) {
            throw new ApiFailure(HttpStatus.SERVICE_UNAVAILABLE, "LLM_MODELS_DISABLED", "Model credentials unavailable.");
        }
    }

    record Input(String baseUrl, String protocol, String modelId, String apiKey) {
        @Override public String toString() { return "LlmModelInput"; }
    }
    record Model(UUID id, String baseUrl, String protocol, String modelId, boolean supportsTools) {}
    record Catalog(boolean enabled, List<Model> models) {}
    private record Stored(Model model, byte[] encryptedKey, UUID revision) {}
    record Connection(UUID id, String baseUrl, String protocol, String modelId, String apiKey, boolean supportsTools) {
        @Override public String toString() { return "LlmModelConnection[id=" + id + "]"; }
    }
}
