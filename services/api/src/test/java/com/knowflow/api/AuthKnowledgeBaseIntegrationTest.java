package com.knowflow.api;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.Statement;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.knowflow.api.auth.AuthService;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@SpringBootTest(properties = {
        "spring.profiles.active=database",
        "knowflow.ai.internal-shared-secret=auth-test-shared-secret-is-long-enough"
})
@AutoConfigureMockMvc
class AuthKnowledgeBaseIntegrationTest {
    private static final String ADMIN_PASSWORD = "auth-test-admin-password";
    private static final String MIGRATOR_PASSWORD = "auth-test-migrator-password";
    private static final String APP_PASSWORD = "auth-test-app-password";
    private static final String AI_PASSWORD = "auth-test-ai-password";
    private static final String IMAGE = "pgvector/pgvector:0.8.1-pg16"
            + "@sha256:33198da2828a14c30348d2ccb4750833d5ed9a44c88d840a0e523d7417120337";

    @Container
    private static final PostgreSQLContainer<?> DATABASE = new PostgreSQLContainer<>(
            DockerImageName.parse(IMAGE).asCompatibleSubstituteFor("postgres"))
            .withDatabaseName("knowflow")
            .withUsername("postgres")
            .withPassword(ADMIN_PASSWORD)
            .withInitScript("db/bootstrap-roles.sql");

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private PasswordEncoder passwordEncoder;

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry properties) {
        properties.add("knowflow.database.application.url", DATABASE::getJdbcUrl);
        properties.add("knowflow.database.application.username", () -> "knowflow_app");
        properties.add("knowflow.database.application.password", () -> APP_PASSWORD);
    }

    @BeforeAll
    static void provisionDatabase() throws Exception {
        try (Connection connection = DriverManager.getConnection(
                DATABASE.getJdbcUrl(), DATABASE.getUsername(), DATABASE.getPassword());
             Statement statement = connection.createStatement()) {
            statement.execute("ALTER ROLE knowflow_migrator PASSWORD '" + MIGRATOR_PASSWORD + "'");
            statement.execute("ALTER ROLE knowflow_app PASSWORD '" + APP_PASSWORD + "'");
            statement.execute("ALTER ROLE knowflow_ai PASSWORD '" + AI_PASSWORD + "'");
        }
        Flyway.configure()
                .dataSource(DATABASE.getJdbcUrl(), "knowflow_migrator", MIGRATOR_PASSWORD)
                .defaultSchema("knowflow_flyway")
                .schemas("knowflow_flyway", "knowflow")
                .createSchemas(false)
                .cleanDisabled(true)
                .locations("classpath:db/migration")
                .load()
                .migrate();
    }

    @Test
    void registrationAndLoginUseHashedPasswordsAndOpaqueRevocableSessions() throws Exception {
        String password = "synthetic-user-password-123";
        mockMvc.perform(post("/api/v1/auth/register")
                        .contentType(MediaType.TEXT_PLAIN)
                        .accept(MediaType.APPLICATION_JSON)
                        .content(registerBody("unsupported-content-type@example.test",
                                "synthetic-registration-password")))
                .andExpect(status().isUnsupportedMediaType())
                .andExpect(header().string(org.springframework.http.HttpHeaders.ACCEPT,
                        org.hamcrest.Matchers.containsString(MediaType.APPLICATION_JSON_VALUE)))
                .andExpect(jsonPath("$.code").value("INVALID_REQUEST"))
                .andExpect(jsonPath("$.message")
                        .value("The request content type is not supported."));

        mockMvc.perform(post("/api/v1/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(registerBody("short@example.test", "too-short")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_REQUEST"));

        JsonNode registered = register("Owner@Example.Test", password);
        String userId = registered.path("user_id").asText();
        String registrationToken = registered.path("access_token").asText();

        assertThat(registered.path("contract_version").asText()).isEqualTo("0.2.0-draft.4");
        assertThat(registered.path("email").asText()).isEqualTo("owner@example.test");
        assertThat(registrationToken).matches("[A-Za-z0-9_-]{43}");
        String encodedPassword = jdbc.queryForObject(
                "SELECT password_hash FROM knowflow.users WHERE id = ?",
                String.class, java.util.UUID.fromString(userId));
        assertThat(encodedPassword).isNotEqualTo(password).hasSizeGreaterThanOrEqualTo(64);
        assertThat(passwordEncoder.matches(password, encodedPassword)).isTrue();

        String tokenHash = jdbc.queryForObject("""
                SELECT token_sha256 FROM knowflow.user_sessions WHERE user_id = ?
                """, String.class, java.util.UUID.fromString(userId));
        assertThat(tokenHash).isEqualTo(AuthService.sha256(registrationToken))
                .isNotEqualTo(registrationToken);

        mockMvc.perform(get("/api/v1/me")
                        .header("Authorization", "Bearer " + registrationToken))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.user_id").value(userId))
                .andExpect(jsonPath("$.email").value("owner@example.test"));

        mockMvc.perform(post("/api/v1/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(loginBody("owner@example.test", "wrong-password")))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("UNAUTHENTICATED"))
                .andExpect(result -> assertThat(result.getResponse().getContentAsString())
                        .doesNotContain(password, "wrong-password", encodedPassword));

        JsonNode login = login("OWNER@example.test", password);
        String loginToken = login.path("access_token").asText();
        assertThat(login.path("expires_at").asText()).contains("Z");
        mockMvc.perform(post("/api/v1/auth/logout")
                        .header("Authorization", "Bearer " + loginToken))
                .andExpect(status().isNoContent());
        mockMvc.perform(get("/api/v1/me")
                        .header("Authorization", "Bearer " + loginToken))
                .andExpect(status().isUnauthorized());

        mockMvc.perform(post("/api/v1/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(registerBody("owner@example.test", password)))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("ACCOUNT_CREATE_REJECTED"))
                .andExpect(result -> assertThat(result.getResponse().getContentAsString())
                        .doesNotContain("owner@example.test", password));

        mockMvc.perform(post("/api/v1/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(loginBody("owner@example.test", password)
                                .replace("0.2.0-draft.4", "0.2.0-draft.3")))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_REQUEST"));
    }

    @Test
    void expiredSessionsCannotAuthenticate() throws Exception {
        JsonNode registered = register("expiry@example.test", "synthetic-expiry-password");
        String token = registered.path("access_token").asText();
        String hash = AuthService.sha256(token);
        jdbc.update("""
                UPDATE knowflow.user_sessions
                   SET created_at = CURRENT_TIMESTAMP - INTERVAL '1 day',
                       expires_at = CURRENT_TIMESTAMP - INTERVAL '1 second'
                 WHERE token_sha256 = ?
                """, hash);

        mockMvc.perform(get("/api/v1/me").header("Authorization", "Bearer " + token))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("UNAUTHENTICATED"));
    }

    @Test
    void knowledgeBaseOperationsAlwaysUseAuthenticatedOwnerAndDeleteRevokesDocuments()
            throws Exception {
        JsonNode ownerA = register("owner-a@example.test", "synthetic-owner-a-password");
        JsonNode ownerB = register("owner-b@example.test", "synthetic-owner-b-password");
        String tokenA = ownerA.path("access_token").asText();
        String tokenB = ownerB.path("access_token").asText();
        String ownerIdA = ownerA.path("user_id").asText();

        mockMvc.perform(get("/api/v1/knowledge-bases"))
                .andExpect(status().isUnauthorized());
        String body = """
                {"contract_version":"0.2.0-draft.4","name":"Research"}
                """;
        JsonNode created = objectMapper.readTree(mockMvc.perform(post("/api/v1/knowledge-bases")
                        .header("Authorization", "Bearer " + tokenA)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.status").value("ACTIVE"))
                .andReturn().getResponse().getContentAsByteArray());
        String knowledgeBaseId = created.path("id").asText();

        mockMvc.perform(post("/api/v1/knowledge-bases")
                        .header("Authorization", "Bearer " + tokenA)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"contract_version":"0.2.0-draft.4","name":"Injected",
                                 "owner_id":"%s"}
                                """.formatted(ownerA.path("user_id").asText())))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_REQUEST"));

        mockMvc.perform(get("/api/v1/knowledge-bases")
                        .header("Authorization", "Bearer " + tokenB))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items.length()").value(0));
        mockMvc.perform(get("/api/v1/knowledge-bases/{id}", knowledgeBaseId)
                        .header("Authorization", "Bearer " + tokenB))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("RESOURCE_NOT_FOUND"));
        mockMvc.perform(delete("/api/v1/knowledge-bases/{id}", knowledgeBaseId)
                        .header("Authorization", "Bearer " + tokenB))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("RESOURCE_NOT_FOUND"));

        java.util.UUID kbId = java.util.UUID.fromString(knowledgeBaseId);
        java.util.UUID ownerId = java.util.UUID.fromString(ownerIdA);
        java.util.UUID documentId = java.util.UUID.randomUUID();
        jdbc.update("""
                INSERT INTO knowflow.documents (id, knowledge_base_id, owner_user_id, original_name)
                VALUES (?, ?, ?, 'test.txt')
                """, documentId, kbId, ownerId);

        mockMvc.perform(get("/api/v1/knowledge-bases")
                        .header("Authorization", "Bearer " + tokenA)
                        .param("limit", "1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items.length()").value(1))
                .andExpect(jsonPath("$.has_more").value(false));
        mockMvc.perform(get("/api/v1/knowledge-bases")
                        .header("Authorization", "Bearer " + tokenA)
                        .param("owner_id", ownerB.path("user_id").asText()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items.length()").value(1))
                .andExpect(jsonPath("$.items[0].id").value(knowledgeBaseId));
        mockMvc.perform(get("/api/v1/knowledge-bases")
                        .header("Authorization", "Bearer " + tokenA)
                        .param("limit", "0"))
                .andExpect(status().isBadRequest());
        mockMvc.perform(get("/api/v1/knowledge-bases/not-a-uuid")
                        .header("Authorization", "Bearer " + tokenA))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_REQUEST"));

        java.util.UUID contentVersionId = java.util.UUID.randomUUID();
        java.util.UUID indexVersionId = java.util.UUID.randomUUID();
        java.util.UUID taskId = java.util.UUID.randomUUID();
        java.util.UUID leaseId = java.util.UUID.randomUUID();
        jdbc.update("""
                INSERT INTO knowflow.content_versions
                    (id, document_id, version_no, source_sha256, source_format, object_key, byte_size)
                VALUES (?, ?, 1, ?, 'txt', ?, 64)
                """, contentVersionId, documentId, "a".repeat(64),
                "objects/" + documentId + "/" + contentVersionId);
        jdbc.update("""
                UPDATE knowflow.documents
                   SET current_content_version_id = ?
                 WHERE id = ?
                """, contentVersionId, documentId);
        jdbc.update("""
                INSERT INTO knowflow.index_versions
                    (id, document_id, content_version_id, pipeline_profile_id,
                     generation, embedding_model_profile_id)
                VALUES (?, ?, ?, 'pipeline-test', 1, 'BAAI/bge-m3')
                """, indexVersionId, documentId, contentVersionId);
        jdbc.update("""
                INSERT INTO knowflow.indexing_tasks
                    (id, owner_user_id, knowledge_base_id, document_id,
                     content_version_id, index_version_id, status, attempt_count,
                     fencing, lease_id, lease_expires_at, execution_token_hash)
                VALUES (?, ?, ?, ?, ?, ?, 'RUNNING', 1, 1, ?,
                        CURRENT_TIMESTAMP + INTERVAL '1 hour', ?)
                """, taskId, ownerId, kbId, documentId, contentVersionId, indexVersionId,
                leaseId, "b".repeat(64));

        mockMvc.perform(delete("/api/v1/knowledge-bases/{id}", knowledgeBaseId)
                        .header("Authorization", "Bearer " + tokenA))
                .andExpect(status().isNoContent());
        assertThat(jdbc.queryForObject(
                "SELECT status FROM knowflow.documents WHERE id = ?", String.class, documentId))
                .isEqualTo("DELETED");
        assertThat(jdbc.queryForMap("""
                SELECT status, lease_id, lease_expires_at, execution_token_hash, finished_at
                  FROM knowflow.indexing_tasks WHERE id = ?
                """, taskId))
                .containsEntry("status", "CANCELLED")
                .containsEntry("lease_id", null)
                .containsEntry("lease_expires_at", null)
                .containsEntry("execution_token_hash", null)
                .doesNotContainEntry("finished_at", null);
        mockMvc.perform(get("/api/v1/knowledge-bases/{id}", knowledgeBaseId)
                        .header("Authorization", "Bearer " + tokenA))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("RESOURCE_NOT_FOUND"));
        mockMvc.perform(delete("/api/v1/knowledge-bases/{id}", knowledgeBaseId)
                        .header("Authorization", "Bearer " + tokenA))
                .andExpect(status().isNotFound());
    }

    private JsonNode register(String email, String password) throws Exception {
        return objectMapper.readTree(mockMvc.perform(post("/api/v1/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(registerBody(email, password)))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsByteArray());
    }

    private JsonNode login(String email, String password) throws Exception {
        return objectMapper.readTree(mockMvc.perform(post("/api/v1/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(loginBody(email, password)))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsByteArray());
    }

    private static String registerBody(String email, String password) {
        return """
                {"contract_version":"0.2.0-draft.4","email":"%s","password":"%s"}
                """.formatted(email, password);
    }

    private static String loginBody(String email, String password) {
        return registerBody(email, password);
    }
}
