package com.knowflow.api.document;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.nio.charset.StandardCharsets;
import java.math.BigDecimal;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.Statement;
import java.net.InetSocketAddress;
import java.util.HexFormat;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Function;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.knowflow.api.ai.AiInternalHealthClient;
import com.knowflow.api.ai.InternalHealth;
import com.knowflow.api.answer.AiAnswerResponse;
import com.knowflow.api.answer.TrustedAnswerRequest;
import com.knowflow.api.auth.AuthService;
import com.knowflow.api.error.ApiError;
import com.knowflow.api.indexing.ClaimedIndexTask;
import com.knowflow.api.indexing.LeaseContext;
import com.knowflow.api.indexing.IndexingTaskQueue;
import com.knowflow.api.indexing.IndexBatchDigest;
import com.knowflow.api.indexing.IndexBatchRequest;
import com.knowflow.api.indexing.CompletionRequest;
import com.knowflow.api.indexing.HeartbeatRequest;
import com.knowflow.api.indexing.IndexManifestDigest;
import com.knowflow.api.indexing.SourceReadRequest;
import com.knowflow.api.indexing.AiExecutionCancellationClient;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDPage;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.http.HttpHeaders;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.containers.wait.strategy.Wait;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@SpringBootTest(properties = {
        "spring.profiles.active=database,storage",
        "knowflow.ai.internal-shared-secret=document-test-internal-secret-long-enough"
})
@AutoConfigureMockMvc
class DocumentApiIntegrationTest {
    private static final String ADMIN_PASSWORD = "document-test-admin-password";
    private static final String MIGRATOR_PASSWORD = "document-test-migrator-password";
    private static final String APP_PASSWORD = "document-test-app-password";
    private static final String AI_PASSWORD = "document-test-ai-password";
    private static final String MINIO_ACCESS = "knowflow-document-test";
    private static final String MINIO_SECRET = "document-test-minio-secret-at-least-eight";
    private static final String AI_SECRET = "document-test-internal-secret-long-enough";
    private static final ObjectMapper AI_MAPPER = new ObjectMapper()
            .setPropertyNamingStrategy(com.fasterxml.jackson.databind.PropertyNamingStrategies.SNAKE_CASE);
    private static final AtomicReference<String> AI_RECEIVED_AUTHORIZATION = new AtomicReference<>();
    private static final AtomicReference<String> AI_RECEIVED_REQUEST_ID = new AtomicReference<>();
    private static final AtomicReference<String> AI_HANDLER_FAILURE = new AtomicReference<>();
    private static final AtomicReference<Function<TrustedAnswerRequest, AiAnswerResponse>> AI_RESPONSE =
            new AtomicReference<>();
    private static final HttpServer AI_SERVER = startAiServer();
    private static final String POSTGRES_IMAGE = "pgvector/pgvector:0.8.1-pg16"
            + "@sha256:33198da2828a14c30348d2ccb4750833d5ed9a44c88d840a0e523d7417120337";
    private static final String MINIO_IMAGE = "bitnamilegacy/minio:2025.4.22"
            + "@sha256:50cec18ac4184af4671a78aedd5554942c8ae105d51a465fa82037949046da01";

    @Container
    private static final PostgreSQLContainer<?> DATABASE = new PostgreSQLContainer<>(
            DockerImageName.parse(POSTGRES_IMAGE).asCompatibleSubstituteFor("postgres"))
            .withDatabaseName("knowflow")
            .withUsername("postgres")
            .withPassword(ADMIN_PASSWORD)
            .withInitScript("db/bootstrap-roles.sql");

    @Container
    private static final GenericContainer<?> MINIO = new GenericContainer<>(
            DockerImageName.parse(MINIO_IMAGE))
            .withEnv("MINIO_ROOT_USER", MINIO_ACCESS)
            .withEnv("MINIO_ROOT_PASSWORD", MINIO_SECRET)
            .withExposedPorts(9000)
            .waitingFor(Wait.forHttp("/minio/health/live").forPort(9000).forStatusCode(200));

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private com.knowflow.api.storage.S3ObjectStore objectStore;

    @Autowired
    private TransactionTemplate transactions;

    @Autowired
    private AiExecutionCancellationClient cancellationClient;

    @Autowired
    private AiInternalHealthClient aiHealthClient;

    @Autowired
    private IndexingTaskQueue indexingTasks;

    @DynamicPropertySource
    static void serviceProperties(DynamicPropertyRegistry properties) {
        properties.add("knowflow.database.application.url", DATABASE::getJdbcUrl);
        properties.add("knowflow.database.application.username", () -> "knowflow_app");
        properties.add("knowflow.database.application.password", () -> APP_PASSWORD);
        properties.add("knowflow.storage.endpoint", () -> "http://" + MINIO.getHost() + ":"
                + MINIO.getMappedPort(9000));
        properties.add("knowflow.storage.bucket", () -> "knowflow-document-test");
        properties.add("knowflow.storage.access-key", () -> MINIO_ACCESS);
        properties.add("knowflow.storage.secret-key", () -> MINIO_SECRET);
        properties.add("knowflow.ai.base-url", () -> "http://127.0.0.1:"
                + AI_SERVER.getAddress().getPort());
    }

    @BeforeAll
    static void migrate() throws Exception {
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

    @AfterAll
    static void stopAiServer() {
        AI_SERVER.stop(0);
    }

    @BeforeEach
    void clearDatabase() throws Exception {
        AI_RESPONSE.set(request -> new AiAnswerResponse(ApiError.CONTRACT_VERSION,
                request.requestId(), "I could not find supporting information.", false,
                java.util.List.of()));
        AI_RECEIVED_AUTHORIZATION.set(null);
        AI_RECEIVED_REQUEST_ID.set(null);
        AI_HANDLER_FAILURE.set(null);
        try (Connection connection = DriverManager.getConnection(
                DATABASE.getJdbcUrl(), DATABASE.getUsername(), DATABASE.getPassword());
             Statement statement = connection.createStatement()) {
            statement.execute("""
                    TRUNCATE knowflow.users, knowflow.storage_cleanup_queue,
                        knowflow.index_cleanup_queue, knowflow.execution_cancellation_queue CASCADE
                    """);
        }
    }

    @Test
    void uploadsObjectsAndCreatesOwnerScopedDocumentAndQueuedTask() throws Exception {
        JsonNode owner = register("document-owner@example.test");
        String token = owner.path("access_token").asText();
        String knowledgeBaseId = createKnowledgeBase(token, "Documents");
        byte[] text = "first line\nsecond line".getBytes(StandardCharsets.UTF_8);
        MockMultipartFile file = new MockMultipartFile("file", "notes.txt",
                MediaType.APPLICATION_OCTET_STREAM_VALUE, text);

        var uploaded = mockMvc.perform(multipart(
                        "/api/v1/knowledge-bases/{knowledgeBaseId}/documents", knowledgeBaseId)
                        .file(file)
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isAccepted())
                .andExpect(header().string("Location", org.hamcrest.Matchers.containsString("/api/v1/tasks/")))
                .andExpect(jsonPath("$.contract_version").value("0.2.0-draft.5"))
                .andExpect(jsonPath("$.status").value("QUEUED"))
                .andReturn();
        JsonNode response = objectMapper.readTree(uploaded.getResponse().getContentAsByteArray());
        String documentId = response.path("document_id").asText();
        String taskId = response.path("task_id").asText();

        mockMvc.perform(get("/api/v1/documents/{documentId}", documentId)
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("PROCESSING"))
                .andExpect(jsonPath("$.format").value("txt"))
                .andExpect(jsonPath("$.byte_size").value(text.length))
                .andExpect(jsonPath("$.source_sha256").value(
                        "73621482ff083eca9ea88880393298f7d3f53402200780b0c16354a9beb0535a"));
        mockMvc.perform(get("/api/v1/tasks/{taskId}", taskId)
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("QUEUED"))
                .andExpect(jsonPath("$.attempt_count").value(0))
                .andExpect(jsonPath("$.lease_id").doesNotExist());
        mockMvc.perform(get("/api/v1/knowledge-bases/{knowledgeBaseId}/documents",
                        knowledgeBaseId).header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items.length()").value(1))
                .andExpect(jsonPath("$.items[0].id").value(documentId));

        JsonNode other = register("document-other@example.test");
        String otherToken = other.path("access_token").asText();
        mockMvc.perform(get("/api/v1/documents/{documentId}", documentId)
                        .header("Authorization", "Bearer " + otherToken))
                .andExpect(status().isNotFound());
        mockMvc.perform(get("/api/v1/tasks/{taskId}", taskId)
                        .header("Authorization", "Bearer " + otherToken))
                .andExpect(status().isNotFound());
        mockMvc.perform(multipart("/api/v1/knowledge-bases/{knowledgeBaseId}/documents",
                        knowledgeBaseId)
                        .file(new MockMultipartFile("file", "notes.txt", "text/plain", text))
                        .header("Authorization", "Bearer " + otherToken))
                .andExpect(status().isNotFound());
        assertThat(jdbc.queryForObject("SELECT count(*) FROM knowflow.documents",
                Integer.class)).isEqualTo(1);
    }

    @Test
    void unsupportedFileTypesAndOversizedTextAreRejectedBeforeStorage() throws Exception {
        JsonNode owner = register("document-validation@example.test");
        String token = owner.path("access_token").asText();
        String knowledgeBaseId = createKnowledgeBase(token, "Validation");

        mockMvc.perform(multipart("/api/v1/knowledge-bases/{knowledgeBaseId}/documents",
                        knowledgeBaseId)
                        .file(new MockMultipartFile("file", "payload.exe",
                                "application/octet-stream", new byte[] {1, 2, 3}))
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("UNSUPPORTED_CONTENT"));
        mockMvc.perform(multipart("/api/v1/knowledge-bases/{knowledgeBaseId}/documents",
                        knowledgeBaseId)
                        .file(new MockMultipartFile("file", "fake.txt", "text/plain",
                                "%PDF-1.7".getBytes(StandardCharsets.US_ASCII)))
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("UNSUPPORTED_CONTENT"));
        mockMvc.perform(multipart("/api/v1/knowledge-bases/{knowledgeBaseId}/documents",
                        knowledgeBaseId)
                        .file(new MockMultipartFile("file", "large.txt", "text/plain",
                                "x".repeat(200_001).getBytes(StandardCharsets.UTF_8)))
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isPayloadTooLarge())
                .andExpect(jsonPath("$.code").value("RESOURCE_LIMIT"));
        assertThat(jdbc.queryForObject("SELECT count(*) FROM knowflow.documents",
                Integer.class)).isZero();
    }

    @Test
    void supportedPlainTextAndPdfContentHaveStrictFormatChecks() throws Exception {
        assertThat(DocumentFormat.fromNameAndBytes("book.md",
                "# title".getBytes(StandardCharsets.UTF_8))).isEqualTo(DocumentFormat.MD);
        assertThat(DocumentFormat.fromNameAndBytes("book.pdf", pdfBytes(1)))
                .isEqualTo(DocumentFormat.PDF);
        org.assertj.core.api.Assertions.assertThatThrownBy(() -> DocumentFormat.fromNameAndBytes(
                        "large.pdf", pdfBytes(UploadLimits.MAX_PDF_PAGES + 1)))
                .isInstanceOf(com.knowflow.api.error.ApiFailure.class)
                .hasMessage("The uploaded file exceeds a configured limit.");
        org.assertj.core.api.Assertions.assertThatThrownBy(() -> DocumentFormat.fromNameAndBytes(
                        "broken.pdf", "%PDF-1.7\nsynthetic".getBytes(StandardCharsets.US_ASCII)))
                .isInstanceOf(com.knowflow.api.error.ApiFailure.class)
                .hasMessage("The uploaded file is not supported.");
        org.assertj.core.api.Assertions.assertThatThrownBy(() -> DocumentFormat.fromNameAndBytes(
                        "broken.md", new byte[] {(byte) 0xc3, (byte) 0x28}))
                .isInstanceOf(com.knowflow.api.error.ApiFailure.class);
    }

    @Test
    void realWebClientHealthCheckUsesTheSharedSecretAndEchoedRequestId() {
        InternalHealth health = aiHealthClient.check("document-health-client-regression")
                .block(java.time.Duration.ofSeconds(3));

        assertThat(health).isNotNull();
        assertThat(health.contract_version()).isEqualTo(ApiError.CONTRACT_VERSION);
        assertThat(health.status()).isEqualTo("UP");
        assertThat(health.request_id()).isEqualTo("document-health-client-regression");
        assertThat(AI_RECEIVED_AUTHORIZATION.get()).isEqualTo("Bearer " + AI_SECRET);
        assertThat(AI_RECEIVED_REQUEST_ID.get()).isEqualTo("document-health-client-regression");
    }

    @Test
    void uploadsAndServesRealTextMarkdownAndPdfObjects() throws Exception {
        JsonNode owner = register("real-formats@example.test");
        String token = owner.path("access_token").asText();
        String knowledgeBaseId = createKnowledgeBase(token, "Real formats");
        byte[] text = "plain text".getBytes(StandardCharsets.UTF_8);
        byte[] markdown = "# Markdown\n正文".getBytes(StandardCharsets.UTF_8);
        byte[] pdf = pdfBytes(2);

        JsonNode textUpload = uploadBytes(token, knowledgeBaseId, "notes.txt", "text/plain", text);
        JsonNode markdownUpload = uploadBytes(token, knowledgeBaseId, "notes.md", "text/markdown", markdown);
        JsonNode pdfUpload = uploadBytes(token, knowledgeBaseId, "notes.pdf", "application/pdf", pdf);

        assertStoredObject(textUpload, text, "txt");
        assertStoredObject(markdownUpload, markdown, "md");
        assertStoredObject(pdfUpload, pdf, "pdf");
        mockMvc.perform(get("/api/v1/knowledge-bases/{knowledgeBaseId}/documents",
                        knowledgeBaseId).header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items.length()").value(3));
    }

    @Test
    void questionsRequirePublishedEvidenceAndSourcesAndFilesRemainOwnerBounded() throws Exception {
        JsonNode owner = register("question-owner@example.test");
        String token = owner.path("access_token").asText();
        String knowledgeBaseId = createKnowledgeBase(token, "Questions");
        String evidence = "The project stores verifiable source evidence.";
        PublishedIndex published = publishDocument(token, knowledgeBaseId,
                "evidence.txt", evidence, "question-index-publish");
        AI_RESPONSE.set(request -> {
            TrustedAnswerRequest.IndexScope scope = request.scope().indexes().getFirst();
            return new AiAnswerResponse(ApiError.CONTRACT_VERSION, request.requestId(),
                    "Evidence marker [evidence-1] supports the answer.", true,
                    java.util.List.of(new AiAnswerResponse.AiSource("evidence-1",
                            scope.documentId(), scope.contentVersionId(), scope.indexVersionId(),
                            published.chunkId(), new AiAnswerResponse.Locator("text_range", null,
                            0, evidence.codePointCount(0, evidence.length()),
                            "unicode_code_point"), evidence)));
        });

        var answerResult = mockMvc.perform(post(
                        "/api/v1/knowledge-bases/{knowledgeBaseId}/questions", knowledgeBaseId)
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsBytes(new com.knowflow.api.answer.PublicQuestion(
                                "What evidence is stored?"))))
                .andReturn();
        assertThat(answerResult.getResponse().getStatus())
                .withFailMessage("AI HTTP fixture failed: %s", AI_HANDLER_FAILURE.get())
                .isEqualTo(200);
        JsonNode answer = objectMapper.readTree(answerResult.getResponse().getContentAsByteArray());
        assertThat(answer.path("contract_version").asText()).isEqualTo(ApiError.CONTRACT_VERSION);
        assertThat(answer.path("has_answer").asBoolean()).isTrue();
        assertThat(answer.path("sources")).hasSize(1);
        assertThat(answer.path("sources").get(0).path("quote").asText()).isEqualTo(evidence);
        String sourceId = answer.path("sources").get(0).path("source_id").asText();
        assertThat(answer.path("answer").asText()).contains(sourceId);
        assertThat(AI_RECEIVED_AUTHORIZATION.get()).isEqualTo("Bearer " + AI_SECRET);
        assertThat(AI_RECEIVED_REQUEST_ID.get()).isEqualTo(answer.path("request_id").asText());

        mockMvc.perform(get("/api/v1/sources/{sourceId}", sourceId)
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.document_id").value(published.lease().documentId().toString()))
                .andExpect(jsonPath("$.index_version_id").value(
                        published.lease().indexVersionId().toString()))
                .andExpect(jsonPath("$.quote").value(evidence));

        JsonNode other = register("question-other@example.test");
        String otherToken = other.path("access_token").asText();
        mockMvc.perform(get("/api/v1/sources/{sourceId}", sourceId)
                        .header("Authorization", "Bearer " + otherToken))
                .andExpect(status().isNotFound());

        String filePath = "/api/v1/documents/" + published.lease().documentId()
                + "/contents/" + published.lease().contentVersionId() + "/file";
        mockMvc.perform(get(filePath).header("Authorization", "Bearer " + token)
                        .header(HttpHeaders.RANGE, "bytes=0-5"))
                .andExpect(status().isPartialContent())
                .andExpect(header().string(HttpHeaders.ACCEPT_RANGES, "bytes"))
                .andExpect(header().string(HttpHeaders.CONTENT_RANGE,
                        "bytes 0-5/" + evidence.getBytes(StandardCharsets.UTF_8).length))
                .andExpect(org.springframework.test.web.servlet.result.MockMvcResultMatchers.content()
                        .bytes("The pr".getBytes(StandardCharsets.UTF_8)));
        mockMvc.perform(get(filePath).header("Authorization", "Bearer " + token)
                        .header(HttpHeaders.RANGE, "bytes=999999-"))
                .andExpect(status().isRequestedRangeNotSatisfiable())
                .andExpect(header().string(HttpHeaders.CONTENT_RANGE,
                        "bytes */" + evidence.getBytes(StandardCharsets.UTF_8).length))
                .andExpect(jsonPath("$.code").value("INVALID_REQUEST"));
        mockMvc.perform(get(filePath).header("Authorization", "Bearer " + otherToken))
                .andExpect(status().isNotFound());

        mockMvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete(
                        "/api/v1/documents/{documentId}", published.lease().documentId())
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isNoContent());
        mockMvc.perform(get("/api/v1/sources/{sourceId}", sourceId)
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isNotFound());
        mockMvc.perform(get(filePath).header("Authorization", "Bearer " + token))
                .andExpect(status().isNotFound());
    }

    @Test
    void unsupportedAiEvidenceIsRejectedAndExplicitNoEvidenceRemainsARefusal() throws Exception {
        JsonNode owner = register("question-refusal@example.test");
        String token = owner.path("access_token").asText();
        String knowledgeBaseId = createKnowledgeBase(token, "Refusal");
        PublishedIndex published = publishDocument(token, knowledgeBaseId,
                "refusal.txt", "Trusted document text.", "refusal-index-publish");
        AI_RESPONSE.set(request -> new AiAnswerResponse(ApiError.CONTRACT_VERSION,
                request.requestId(), "Unsubstantiated claim [unknown-source].", true,
                java.util.List.of(new AiAnswerResponse.AiSource("unknown-source",
                        published.lease().documentId(), published.lease().contentVersionId(),
                        published.lease().indexVersionId(), UUID.randomUUID(),
                        new AiAnswerResponse.Locator("text_range", null, 0, 8,
                                "unicode_code_point"), "not stored"))));

        mockMvc.perform(post("/api/v1/knowledge-bases/{knowledgeBaseId}/questions",
                        knowledgeBaseId)
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsBytes(new com.knowflow.api.answer.PublicQuestion(
                                "What does the document say?"))))
                .andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.code").value("AI_PROCESSING_FAILED"));
        assertThat(AI_HANDLER_FAILURE.get()).isNull();
        assertThat(jdbc.queryForObject("SELECT status FROM knowflow.questions ORDER BY created_at DESC LIMIT 1",
                String.class)).isEqualTo("FAILED");

        AI_RESPONSE.set(request -> new AiAnswerResponse(ApiError.CONTRACT_VERSION,
                request.requestId(), "I could not find supporting information.", false,
                java.util.List.of()));
        var refusalResult = mockMvc.perform(post("/api/v1/knowledge-bases/{knowledgeBaseId}/questions",
                        knowledgeBaseId)
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsBytes(new com.knowflow.api.answer.PublicQuestion(
                                "What does the document say?"))))
                .andReturn();
        assertThat(refusalResult.getResponse().getStatus())
                .withFailMessage("AI HTTP fixture failed: %s", AI_HANDLER_FAILURE.get())
                .isEqualTo(200);
        JsonNode refusal = objectMapper.readTree(refusalResult.getResponse().getContentAsByteArray());
        assertThat(refusal.path("has_answer").asBoolean()).isFalse();
        assertThat(refusal.path("sources")).isEmpty();
    }

    @Test
    void indexBatchBodyLimitRejectsOversizedBodyBeforeJsonParsing() throws Exception {
        String oversized = "x".repeat(1_048_577);
        mockMvc.perform(post("/internal/v1/tasks/{taskId}/index-batches",
                        UUID.randomUUID())
                        .header("Authorization", "Bearer " + AI_SECRET)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(oversized))
                .andExpect(status().isPayloadTooLarge())
                .andExpect(jsonPath("$.code").value("RESOURCE_LIMIT"));
    }

    @Test
    void expiredExecutionsAreFencedAndRecoverIntoIsolatedCandidatesUpToRetryLimit()
            throws Exception {
        JsonNode owner = register("lease-recovery@example.test");
        String token = owner.path("access_token").asText();
        String knowledgeBaseId = createKnowledgeBase(token, "Lease recovery");
        JsonNode uploaded = upload(token, knowledgeBaseId, "leased.txt", "lease test");
        UUID taskId = UUID.fromString(uploaded.path("task_id").asText());

        ClaimedIndexTask first = indexingTasks.claimNext().orElseThrow();
        assertThat(first.lease().taskId()).isEqualTo(taskId);
        assertThat(first.lease().fencing()).isEqualTo(1);
        assertThat(jdbc.queryForObject("""
                SELECT execution_token_hash FROM knowflow.indexing_tasks WHERE id = ?
                """, String.class, taskId)).isEqualTo(AuthService.sha256(
                first.lease().executionToken()));
        assertThat(indexingTasks.claimNext()).isEmpty();

        expire(taskId);
        ClaimedIndexTask second = indexingTasks.claimNext().orElseThrow();
        assertThat(second.lease().fencing()).isEqualTo(2);
        assertThat(second.lease().leaseId()).isNotEqualTo(first.lease().leaseId());
        assertThat(second.lease().indexVersionId()).isNotEqualTo(first.lease().indexVersionId());
        assertThat(jdbc.queryForObject("""
                SELECT status || ':' || failure_code FROM knowflow.index_versions WHERE id = ?
                """, String.class, first.lease().indexVersionId())).isEqualTo("FAILED:WORKER_LOST");

        expire(taskId);
        ClaimedIndexTask third = indexingTasks.claimNext().orElseThrow();
        assertThat(third.lease().fencing()).isEqualTo(3);
        assertThat(third.lease().indexVersionId()).isNotEqualTo(second.lease().indexVersionId());

        expire(taskId);
        assertThat(indexingTasks.claimNext()).isEmpty();
        assertThat(jdbc.queryForObject("""
                SELECT status || ':' || failure_code FROM knowflow.indexing_tasks WHERE id = ?
                """, String.class, taskId)).isEqualTo("FAILED:WORKER_LOST");
        assertThat(jdbc.queryForObject("""
                SELECT status FROM knowflow.index_versions WHERE id = ?
                """, String.class, third.lease().indexVersionId())).isEqualTo("FAILED");
        assertThat(jdbc.queryForObject("""
                SELECT count(*) FROM knowflow.index_versions
                 WHERE document_id = ? AND content_version_id = ?
                """, Integer.class, UUID.fromString(uploaded.path("document_id").asText()),
                second.lease().contentVersionId())).isEqualTo(3);
    }

    @Test
    void heartbeatExtendsOnlyTheCurrentFencedLeaseAndRejectsExpiredOrReplacedWorkers()
            throws Exception {
        JsonNode owner = register("heartbeat-owner@example.test");
        String token = owner.path("access_token").asText();
        String knowledgeBaseId = createKnowledgeBase(token, "Heartbeat");
        JsonNode uploaded = upload(token, knowledgeBaseId, "heartbeat.txt", "lease heartbeat");
        ClaimedIndexTask first = indexingTasks.claimNext().orElseThrow();
        assertThat(first.lease().taskId().toString()).isEqualTo(uploaded.path("task_id").asText());
        var originalExpiry = jdbc.queryForObject("""
                SELECT lease_expires_at FROM knowflow.indexing_tasks WHERE id = ?
                """, java.time.OffsetDateTime.class, first.lease().taskId());
        HeartbeatRequest firstHeartbeat = new HeartbeatRequest(ApiError.CONTRACT_VERSION,
                "heartbeat-current", first.lease());

        var response = mockMvc.perform(post("/internal/v1/tasks/{taskId}/heartbeat",
                        first.lease().taskId())
                        .header("Authorization", "Bearer " + AI_SECRET)
                        .header("X-Request-ID", firstHeartbeat.requestId())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsBytes(firstHeartbeat)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.contract_version").value(ApiError.CONTRACT_VERSION))
                .andExpect(jsonPath("$.request_id").value(firstHeartbeat.requestId()))
                .andExpect(jsonPath("$.task_id").value(first.lease().taskId().toString()))
                .andReturn();
        JsonNode receipt = objectMapper.readTree(response.getResponse().getContentAsByteArray());
        java.time.OffsetDateTime renewedExpiry = java.time.OffsetDateTime.parse(
                receipt.path("lease_expires_at").asText());
        assertThat(renewedExpiry).isAfter(originalExpiry);

        expire(first.lease().taskId());
        mockMvc.perform(post("/internal/v1/tasks/{taskId}/heartbeat", first.lease().taskId())
                        .header("Authorization", "Bearer " + AI_SECRET)
                        .header("X-Request-ID", firstHeartbeat.requestId())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsBytes(firstHeartbeat)))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("LEASE_REJECTED"));

        ClaimedIndexTask replacement = indexingTasks.claimNext().orElseThrow();
        assertThat(replacement.lease().fencing()).isEqualTo(2);
        mockMvc.perform(post("/internal/v1/tasks/{taskId}/heartbeat", first.lease().taskId())
                        .header("Authorization", "Bearer " + AI_SECRET)
                        .header("X-Request-ID", firstHeartbeat.requestId())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsBytes(firstHeartbeat)))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("LEASE_REJECTED"));

        HeartbeatRequest current = new HeartbeatRequest(ApiError.CONTRACT_VERSION,
                "heartbeat-replacement", replacement.lease());
        mockMvc.perform(post("/internal/v1/tasks/{taskId}/heartbeat", replacement.lease().taskId())
                        .header("Authorization", "Bearer " + AI_SECRET)
                        .header("X-Request-ID", current.requestId())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsBytes(current)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.task_id").value(replacement.lease().taskId().toString()));
    }

    @Test
    void concurrentSchedulersClaimDifferentTasks() throws Exception {
        JsonNode owner = register("parallel-claims@example.test");
        String token = owner.path("access_token").asText();
        String knowledgeBaseId = createKnowledgeBase(token, "Parallel claims");
        upload(token, knowledgeBaseId, "first.txt", "first concurrent task");
        upload(token, knowledgeBaseId, "second.txt", "second concurrent task");

        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);
        try (var executor = Executors.newFixedThreadPool(2)) {
            var one = executor.submit(() -> {
                ready.countDown();
                start.await();
                return indexingTasks.claimNext().orElseThrow();
            });
            var two = executor.submit(() -> {
                ready.countDown();
                start.await();
                return indexingTasks.claimNext().orElseThrow();
            });
            assertThat(ready.await(5, TimeUnit.SECONDS)).isTrue();
            start.countDown();
            ClaimedIndexTask first = one.get(10, TimeUnit.SECONDS);
            ClaimedIndexTask second = two.get(10, TimeUnit.SECONDS);
            assertThat(first.lease().taskId()).isNotEqualTo(second.lease().taskId());
            assertThat(first.lease().fencing()).isEqualTo(1);
            assertThat(second.lease().fencing()).isEqualTo(1);
        }
    }

    @Test
    void sourceReadsRequireTheCurrentLeaseAndReturnBoundedMetadataOnly() throws Exception {
        JsonNode owner = register("source-read@example.test");
        String token = owner.path("access_token").asText();
        String knowledgeBaseId = createKnowledgeBase(token, "Source read");
        byte[] sourceBytes = "private source body".getBytes(StandardCharsets.UTF_8);
        JsonNode uploaded = upload(token, knowledgeBaseId, "source.md",
                new String(sourceBytes, StandardCharsets.UTF_8));
        ClaimedIndexTask claim = indexingTasks.claimNext().orElseThrow();
        assertThat(claim.lease().taskId().toString()).isEqualTo(uploaded.path("task_id").asText());
        String requestId = "source-read-regression";
        byte[] request = objectMapper.writeValueAsBytes(new SourceReadRequest(
                "0.2.0-draft.5", requestId, claim.lease()));

        var response = mockMvc.perform(post("/internal/v1/tasks/{taskId}/source",
                        claim.lease().taskId())
                        .header("Authorization", "Bearer document-test-internal-secret-long-enough")
                        .header("X-Request-ID", requestId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_OCTET_STREAM)
                        .content(request))
                .andExpect(status().isOk())
                .andExpect(header().string("X-Contract-Version", "0.2.0-draft.5"))
                .andExpect(header().string("X-Request-ID", requestId))
                .andExpect(header().string("X-Source-Format", "md"))
                .andExpect(header().string("X-Source-SHA256",
                        "5382bbc0935e381ac557c7a0e46d5fe8ec4480f0f2a8c12e1685afcabc408bbe"))
                .andExpect(header().doesNotExist("X-Object-Key"))
                .andReturn().getResponse();
        assertThat(response.getContentAsByteArray()).isEqualTo(sourceBytes);

        LeaseContext forged = new LeaseContext(claim.lease().taskId(), claim.lease().ownerId(),
                claim.lease().knowledgeBaseId(), claim.lease().documentId(),
                claim.lease().contentVersionId(), claim.lease().indexVersionId(),
                claim.lease().pipelineProfileId(), claim.lease().leaseId(),
                claim.lease().fencing(), "x".repeat(43));
        byte[] forgedRequest = objectMapper.writeValueAsBytes(new SourceReadRequest(
                "0.2.0-draft.5", requestId, forged));
        mockMvc.perform(post("/internal/v1/tasks/{taskId}/source", claim.lease().taskId())
                        .header("Authorization", "Bearer document-test-internal-secret-long-enough")
                        .header("X-Request-ID", requestId)
                        .contentType(MediaType.APPLICATION_JSON).content(forgedRequest))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("LEASE_REJECTED"));

        expire(claim.lease().taskId());
        mockMvc.perform(post("/internal/v1/tasks/{taskId}/source", claim.lease().taskId())
                        .header("Authorization", "Bearer document-test-internal-secret-long-enough")
                        .header("X-Request-ID", requestId)
                        .contentType(MediaType.APPLICATION_JSON).content(request))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("LEASE_REJECTED"));
    }

    @Test
    void indexBatchWriteIsFencedIdempotentAndConflictDetecting() throws Exception {
        JsonNode owner = register("batch-write@example.test");
        String token = owner.path("access_token").asText();
        String knowledgeBaseId = createKnowledgeBase(token, "Batch write");
        upload(token, knowledgeBaseId, "batch.txt", "index this text");
        ClaimedIndexTask claim = indexingTasks.claimNext().orElseThrow();
        String requestId = "batch-write-regression";
        IndexBatchRequest batch = createBatch(claim.lease(), requestId,
                UUID.randomUUID(), "first chunk");
        byte[] body = objectMapper.writeValueAsBytes(batch);

        mockMvc.perform(post("/internal/v1/tasks/{taskId}/index-batches",
                        claim.lease().taskId())
                        .header("Authorization", "Bearer document-test-internal-secret-long-enough")
                        .header("X-Request-ID", requestId)
                        .contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.result").value("ACCEPTED"))
                .andExpect(jsonPath("$.chunk_count").value(1));
        mockMvc.perform(post("/internal/v1/tasks/{taskId}/index-batches",
                        claim.lease().taskId())
                        .header("Authorization", "Bearer document-test-internal-secret-long-enough")
                        .header("X-Request-ID", requestId)
                        .contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.result").value("ALREADY_ACCEPTED"));
        assertThat(jdbc.queryForObject("SELECT count(*) FROM knowflow.chunks", Integer.class))
                .isEqualTo(1);
        assertThat(jdbc.queryForObject("SELECT count(*) FROM knowflow.chunk_embeddings",
                Integer.class)).isEqualTo(1);

        IndexBatchRequest changed = createBatch(claim.lease(), requestId, batch.batchId(),
                "different content");
        mockMvc.perform(post("/internal/v1/tasks/{taskId}/index-batches",
                        claim.lease().taskId())
                        .header("Authorization", "Bearer document-test-internal-secret-long-enough")
                        .header("X-Request-ID", requestId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsBytes(changed)))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("BATCH_CONFLICT"));

        expire(claim.lease().taskId());
        mockMvc.perform(post("/internal/v1/tasks/{taskId}/index-batches",
                        claim.lease().taskId())
                        .header("Authorization", "Bearer document-test-internal-secret-long-enough")
                        .header("X-Request-ID", requestId)
                        .contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("LEASE_REJECTED"));
        assertThat(jdbc.queryForObject("SELECT count(*) FROM knowflow.chunks", Integer.class))
                .isEqualTo(1);
    }

    @Test
    void completionVerifiesStoredRowsAndPublishesAtomicallyAndIdempotently() throws Exception {
        JsonNode owner = register("completion-success@example.test");
        String token = owner.path("access_token").asText();
        String knowledgeBaseId = createKnowledgeBase(token, "Completion success");
        JsonNode uploaded = upload(token, knowledgeBaseId, "complete.txt", "publish this evidence");
        ClaimedIndexTask claim = indexingTasks.claimNext().orElseThrow();
        assertThat(claim.lease().taskId().toString()).isEqualTo(uploaded.path("task_id").asText());
        String requestId = "completion-success-regression";
        IndexBatchRequest batch = createBatch(claim.lease(), requestId, UUID.randomUUID(),
                "publish this evidence");
        postBatch(batch, requestId);
        String manifestHash = IndexManifestDigest.calculate(
                new IndexManifestDigest.ManifestIdentity(claim.lease().taskId(),
                        claim.lease().ownerId(), claim.lease().knowledgeBaseId(),
                        claim.lease().documentId(), claim.lease().contentVersionId(),
                        claim.lease().indexVersionId(), claim.lease().pipelineProfileId(),
                        "BAAI/bge-m3", 1024),
                1, 1, java.util.List.of(new IndexManifestDigest.BatchIdentity(
                        1, batch.batchId(), batch.batchSha256(), 1)));
        CompletionRequest completion = new CompletionRequest("0.2.0-draft.5", requestId,
                claim.lease(), "SUCCEEDED",
                new CompletionRequest.Manifest(1, 1, 1024, "BAAI/bge-m3", manifestHash), null);
        byte[] body = objectMapper.writeValueAsBytes(completion);

        mockMvc.perform(post("/internal/v1/tasks/{taskId}/completion", claim.lease().taskId())
                        .header("Authorization", "Bearer document-test-internal-secret-long-enough")
                        .header("X-Request-ID", requestId)
                        .contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.result").value("ACCEPTED"));
        assertThat(jdbc.queryForObject("""
                SELECT status FROM knowflow.index_versions WHERE id = ?
                """, String.class, claim.lease().indexVersionId())).isEqualTo("READY");
        assertThat(jdbc.queryForObject("""
                SELECT active_index_version_id FROM knowflow.documents WHERE id = ?
                """, UUID.class, claim.lease().documentId()))
                .isEqualTo(claim.lease().indexVersionId());
        assertThat(jdbc.queryForObject("""
                SELECT status FROM knowflow.indexing_tasks WHERE id = ?
                """, String.class, claim.lease().taskId())).isEqualTo("SUCCEEDED");

        mockMvc.perform(post("/internal/v1/tasks/{taskId}/completion", claim.lease().taskId())
                        .header("Authorization", "Bearer document-test-internal-secret-long-enough")
                        .header("X-Request-ID", requestId)
                        .contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.result").value("ALREADY_ACCEPTED"));
        CompletionRequest altered = new CompletionRequest(completion.contractVersion(),
                completion.requestId(), completion.lease(), completion.outcome(),
                new CompletionRequest.Manifest(1, 1, 1024, "BAAI/bge-m3", "0".repeat(64)), null);
        mockMvc.perform(post("/internal/v1/tasks/{taskId}/completion", claim.lease().taskId())
                        .header("Authorization", "Bearer document-test-internal-secret-long-enough")
                        .header("X-Request-ID", requestId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsBytes(altered)))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("COMPLETION_CONFLICT"));
    }

    @Test
    void retryableCompletionFailureRequeuesForANewFencedCandidate() throws Exception {
        JsonNode owner = register("completion-retry@example.test");
        String token = owner.path("access_token").asText();
        String knowledgeBaseId = createKnowledgeBase(token, "Completion retry");
        JsonNode uploaded = upload(token, knowledgeBaseId, "retry.txt", "retry this task");
        ClaimedIndexTask first = indexingTasks.claimNext().orElseThrow();
        assertThat(first.lease().taskId().toString()).isEqualTo(uploaded.path("task_id").asText());
        CompletionRequest failure = new CompletionRequest("0.2.0-draft.5", "retryable-failure",
                first.lease(), "FAILED", null,
                new CompletionRequest.Failure("MODEL_TIMEOUT", "model request timed out", true));
        mockMvc.perform(post("/internal/v1/tasks/{taskId}/completion", first.lease().taskId())
                        .header("Authorization", "Bearer document-test-internal-secret-long-enough")
                        .header("X-Request-ID", "retryable-failure")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsBytes(failure)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.result").value("ACCEPTED"));
        assertThat(jdbc.queryForObject("""
                SELECT status FROM knowflow.indexing_tasks WHERE id = ?
                """, String.class, first.lease().taskId())).isEqualTo("QUEUED");
        assertThat(jdbc.queryForObject("""
                SELECT status FROM knowflow.index_versions WHERE id = ?
                """, String.class, first.lease().indexVersionId())).isEqualTo("FAILED");

        jdbc.update("""
                UPDATE knowflow.indexing_tasks SET available_at = clock_timestamp() - INTERVAL '1 second'
                 WHERE id = ?
                """, first.lease().taskId());
        ClaimedIndexTask second = indexingTasks.claimNext().orElseThrow();
        assertThat(second.lease().taskId()).isEqualTo(first.lease().taskId());
        assertThat(second.lease().fencing()).isEqualTo(2);
        assertThat(second.lease().indexVersionId()).isNotEqualTo(first.lease().indexVersionId());
    }

    @Test
    void definitiveDispatchRejectionUsesBackoffAndCreatesAFreshCandidate() throws Exception {
        JsonNode owner = register("dispatch-rejection@example.test");
        String token = owner.path("access_token").asText();
        String knowledgeBaseId = createKnowledgeBase(token, "Dispatch rejection");
        JsonNode uploaded = upload(token, knowledgeBaseId, "dispatch.txt", "retry dispatch safely");
        ClaimedIndexTask first = indexingTasks.claimNext().orElseThrow();
        assertThat(first.lease().taskId().toString()).isEqualTo(uploaded.path("task_id").asText());

        indexingTasks.rejectDispatch(first);

        assertThat(jdbc.queryForObject("""
                SELECT status FROM knowflow.indexing_tasks WHERE id = ?
                """, String.class, first.lease().taskId())).isEqualTo("QUEUED");
        assertThat(jdbc.queryForObject("""
                SELECT status || ':' || failure_code FROM knowflow.index_versions WHERE id = ?
                """, String.class, first.lease().indexVersionId())).isEqualTo("FAILED:MODEL_FAILURE");
        assertThat(indexingTasks.claimNext()).isEmpty();

        jdbc.update("""
                UPDATE knowflow.indexing_tasks SET available_at = clock_timestamp() - INTERVAL '1 second'
                 WHERE id = ?
                """, first.lease().taskId());
        ClaimedIndexTask second = indexingTasks.claimNext().orElseThrow();
        assertThat(second.lease().fencing()).isEqualTo(2);
        assertThat(second.lease().indexVersionId()).isNotEqualTo(first.lease().indexVersionId());
    }

    @Test
    void deletionImmediatelyRevokesVisibilityAndQueuesCancellationAndPhysicalCleanup()
            throws Exception {
        JsonNode owner = register("delete-document@example.test");
        String token = owner.path("access_token").asText();
        String knowledgeBaseId = createKnowledgeBase(token, "Delete document");
        JsonNode uploaded = upload(token, knowledgeBaseId, "delete.txt", "do not retain this");
        ClaimedIndexTask claim = indexingTasks.claimNext().orElseThrow();
        assertThat(claim.lease().taskId().toString()).isEqualTo(uploaded.path("task_id").asText());
        IndexBatchRequest batch = createBatch(claim.lease(), "delete-partial-index",
                UUID.randomUUID(), "do not retain this");
        postBatch(batch, "delete-partial-index");
        String objectKey = jdbc.queryForObject("""
                SELECT object_key FROM knowflow.content_versions WHERE id = ?
                """, String.class, claim.lease().contentVersionId());

        JsonNode other = register("delete-other@example.test");
        String otherToken = other.path("access_token").asText();
        mockMvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete(
                        "/api/v1/documents/{documentId}", claim.lease().documentId())
                        .header("Authorization", "Bearer " + otherToken))
                .andExpect(status().isNotFound());
        mockMvc.perform(org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete(
                        "/api/v1/documents/{documentId}", claim.lease().documentId())
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isNoContent());

        assertThat(jdbc.queryForObject("""
                SELECT status FROM knowflow.documents WHERE id = ?
                """, String.class, claim.lease().documentId())).isEqualTo("DELETED");
        assertThat(jdbc.queryForObject("""
                SELECT active_index_version_id IS NULL FROM knowflow.documents WHERE id = ?
                """, Boolean.class, claim.lease().documentId())).isTrue();
        assertThat(jdbc.queryForObject("""
                SELECT status FROM knowflow.indexing_tasks WHERE id = ?
                """, String.class, claim.lease().taskId())).isEqualTo("CANCELLED");
        assertThat(jdbc.queryForObject("""
                SELECT status FROM knowflow.index_versions WHERE id = ?
                """, String.class, claim.lease().indexVersionId())).isEqualTo("FAILED");
        assertThat(jdbc.queryForObject("""
                SELECT count(*) FROM knowflow.execution_cancellation_queue
                 WHERE task_id = ? AND lease_id = ? AND fencing = ?
                """, Integer.class, claim.lease().taskId(), claim.lease().leaseId(),
                claim.lease().fencing())).isEqualTo(1);
        assertThat(jdbc.queryForObject("SELECT count(*) FROM knowflow.storage_cleanup_queue",
                Integer.class)).isEqualTo(1);
        assertThat(jdbc.queryForObject("SELECT count(*) FROM knowflow.index_cleanup_queue",
                Integer.class)).isEqualTo(1);

        mockMvc.perform(get("/api/v1/documents/{documentId}", claim.lease().documentId())
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isNotFound());
        mockMvc.perform(post("/internal/v1/tasks/{taskId}/index-batches",
                        claim.lease().taskId())
                        .header("Authorization", "Bearer document-test-internal-secret-long-enough")
                        .header("X-Request-ID", "delete-partial-index")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsBytes(batch)))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("DOCUMENT_UNAVAILABLE"));
        HeartbeatRequest lateHeartbeat = new HeartbeatRequest(ApiError.CONTRACT_VERSION,
                "delete-late-heartbeat", claim.lease());
        mockMvc.perform(post("/internal/v1/tasks/{taskId}/heartbeat", claim.lease().taskId())
                        .header("Authorization", "Bearer " + AI_SECRET)
                        .header("X-Request-ID", lateHeartbeat.requestId())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsBytes(lateHeartbeat)))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("DOCUMENT_UNAVAILABLE"));

        DeletionOutboxScheduler cleanup = new DeletionOutboxScheduler(jdbc, transactions,
                objectStore, cancellationClient);
        cleanup.processOneObjectCleanup();
        cleanup.processOneIndexCleanup();
        assertThat(jdbc.queryForObject("SELECT count(*) FROM knowflow.storage_cleanup_queue",
                Integer.class)).isZero();
        assertThat(jdbc.queryForObject("SELECT count(*) FROM knowflow.index_cleanup_queue",
                Integer.class)).isZero();
        assertThat(jdbc.queryForObject("""
                SELECT count(*) FROM knowflow.chunks WHERE index_version_id = ?
                """, Integer.class, claim.lease().indexVersionId())).isZero();
        org.assertj.core.api.Assertions.assertThatThrownBy(() -> objectStore.getObject(objectKey,
                        1024))
                .isInstanceOf(com.knowflow.api.storage.ObjectStoreException.class);
    }

    private void postBatch(IndexBatchRequest batch, String requestId) throws Exception {
        mockMvc.perform(post("/internal/v1/tasks/{taskId}/index-batches",
                        batch.lease().taskId())
                        .header("Authorization", "Bearer document-test-internal-secret-long-enough")
                        .header("X-Request-ID", requestId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsBytes(batch)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.result").value("ACCEPTED"));
    }

    private PublishedIndex publishDocument(String token, String knowledgeBaseId, String filename,
                                           String text, String requestId) throws Exception {
        JsonNode uploaded = upload(token, knowledgeBaseId, filename, text);
        ClaimedIndexTask claimed = indexingTasks.claimNext().orElseThrow();
        assertThat(claimed.lease().taskId().toString()).isEqualTo(uploaded.path("task_id").asText());
        IndexBatchRequest batch = createBatch(claimed.lease(), requestId, UUID.randomUUID(), text);
        postBatch(batch, requestId);
        String manifestHash = IndexManifestDigest.calculate(
                new IndexManifestDigest.ManifestIdentity(claimed.lease().taskId(),
                        claimed.lease().ownerId(), claimed.lease().knowledgeBaseId(),
                        claimed.lease().documentId(), claimed.lease().contentVersionId(),
                        claimed.lease().indexVersionId(), claimed.lease().pipelineProfileId(),
                        "BAAI/bge-m3", 1024),
                1, 1, java.util.List.of(new IndexManifestDigest.BatchIdentity(
                        1, batch.batchId(), batch.batchSha256(), 1)));
        CompletionRequest completion = new CompletionRequest(ApiError.CONTRACT_VERSION,
                requestId, claimed.lease(), "SUCCEEDED",
                new CompletionRequest.Manifest(1, 1, 1024, "BAAI/bge-m3", manifestHash), null);
        mockMvc.perform(post("/internal/v1/tasks/{taskId}/completion", claimed.lease().taskId())
                        .header("Authorization", "Bearer " + AI_SECRET)
                        .header("X-Request-ID", requestId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsBytes(completion)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.result").value("ACCEPTED"));
        return new PublishedIndex(claimed.lease(), batch.chunks().getFirst().chunkId());
    }

    private JsonNode uploadBytes(String token, String knowledgeBaseId, String filename,
                                 String contentType, byte[] contents) throws Exception {
        var response = mockMvc.perform(multipart(
                        "/api/v1/knowledge-bases/{knowledgeBaseId}/documents", knowledgeBaseId)
                        .file(new MockMultipartFile("file", filename, contentType, contents))
                        .header("Authorization", "Bearer " + token))
                .andReturn();
        assertThat(response.getResponse().getStatus())
                .withFailMessage("MinIO upload failed: %s; container log: %s",
                        response.getResponse().getContentAsString(), MINIO.getLogs())
                .isEqualTo(202);
        return objectMapper.readTree(response.getResponse().getContentAsByteArray());
    }

    private void assertStoredObject(JsonNode upload, byte[] expected, String expectedFormat) {
        UUID documentId = UUID.fromString(upload.path("document_id").asText());
        UUID contentVersionId = jdbc.queryForObject("""
                SELECT current_content_version_id FROM knowflow.documents WHERE id = ?
                """, UUID.class, documentId);
        var metadata = jdbc.queryForMap("""
                SELECT object_key, source_format, byte_size FROM knowflow.content_versions
                 WHERE id = ? AND document_id = ?
                """, contentVersionId, documentId);
        assertThat(metadata.get("source_format")).isEqualTo(expectedFormat);
        assertThat(((Number) metadata.get("byte_size")).longValue()).isEqualTo(expected.length);
        assertThat(objectStore.getObject((String) metadata.get("object_key"),
                (int) com.knowflow.api.document.UploadLimits.MAX_FILE_BYTES)).isEqualTo(expected);
    }

    private static HttpServer startAiServer() {
        try {
            HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            server.createContext("/internal/v1/health", DocumentApiIntegrationTest::respondHealth);
            server.createContext("/internal/v1/answers", DocumentApiIntegrationTest::respondAnswer);
            server.start();
            return server;
        } catch (java.io.IOException exception) {
            throw new ExceptionInInitializerError(exception);
        }
    }

    private static void respondHealth(HttpExchange exchange) throws java.io.IOException {
        String requestId = receiveInternalHeaders(exchange);
        if (requestId == null) {
            return;
        }
        if (!"GET".equals(exchange.getRequestMethod())) {
            respond(exchange, 405, "{}");
            return;
        }
        respond(exchange, 200, "{\"contract_version\":\"" + ApiError.CONTRACT_VERSION
                + "\",\"status\":\"UP\",\"request_id\":\"" + requestId + "\"}");
    }

    private static void respondAnswer(HttpExchange exchange) throws java.io.IOException {
        String requestId = receiveInternalHeaders(exchange);
        if (requestId == null) {
            return;
        }
        if (!"POST".equals(exchange.getRequestMethod())) {
            respond(exchange, 405, "{}");
            return;
        }
        try {
            TrustedAnswerRequest request = AI_MAPPER.readValue(exchange.getRequestBody(),
                    TrustedAnswerRequest.class);
            if (!requestId.equals(request.requestId())) {
                respond(exchange, 400, "{}");
                return;
            }
            AiAnswerResponse answer = AI_RESPONSE.get().apply(request);
            respond(exchange, 200, AI_MAPPER.writeValueAsString(answer));
        } catch (Exception failure) {
            AI_HANDLER_FAILURE.set(failure.getClass().getSimpleName() + ": "
                    + failure.getMessage());
            respond(exchange, 500, "{}");
        }
    }

    private static String receiveInternalHeaders(HttpExchange exchange) throws java.io.IOException {
        String authorization = exchange.getRequestHeaders().getFirst(HttpHeaders.AUTHORIZATION);
        String requestId = exchange.getRequestHeaders().getFirst("X-Request-ID");
        AI_RECEIVED_AUTHORIZATION.set(authorization);
        AI_RECEIVED_REQUEST_ID.set(requestId);
        exchange.getResponseHeaders().set("X-Request-ID", requestId == null ? "invalid" : requestId);
        if (!("Bearer " + AI_SECRET).equals(authorization)) {
            respond(exchange, 401, "{}");
            return null;
        }
        return requestId;
    }

    private static void respond(HttpExchange exchange, int status, String body)
            throws java.io.IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(HttpHeaders.CONTENT_TYPE, "application/json; charset=utf-8");
        exchange.sendResponseHeaders(status, bytes.length);
        try (var output = exchange.getResponseBody()) {
            output.write(bytes);
        }
        exchange.close();
    }

    private void expire(UUID taskId) {
        jdbc.update("""
                UPDATE knowflow.indexing_tasks
                   SET lease_expires_at = clock_timestamp() - INTERVAL '1 second'
                 WHERE id = ? AND status = 'RUNNING'
                """, taskId);
    }

    private static IndexBatchRequest createBatch(LeaseContext lease, String requestId,
                                                  UUID batchId, String text) {
        String hash = sha256(text.getBytes(StandardCharsets.UTF_8));
        IndexBatchRequest.Chunk chunk = new IndexBatchRequest.Chunk(UUID.randomUUID(), 1, text,
                hash, new IndexBatchRequest.Locator("text_range", null, 0,
                text.codePointCount(0, text.length()), "unicode_code_point"),
                java.util.Collections.nCopies(1024, BigDecimal.ZERO));
        IndexBatchRequest candidate = new IndexBatchRequest("0.2.0-draft.5", requestId, lease,
                batchId, 1, "0".repeat(64), java.util.List.of(chunk));
        String digest = IndexBatchDigest.calculate(candidate).sha256();
        return new IndexBatchRequest(candidate.contractVersion(), candidate.requestId(),
                candidate.lease(), candidate.batchId(), candidate.batchSequence(), digest,
                candidate.chunks());
    }

    private static String sha256(byte[] bytes) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException(impossible);
        }
    }

    private static byte[] pdfBytes(int pages) throws Exception {
        try (PDDocument document = new PDDocument();
             var output = new java.io.ByteArrayOutputStream()) {
            for (int index = 0; index < pages; index++) {
                document.addPage(new PDPage());
            }
            document.save(output);
            return output.toByteArray();
        }
    }

    private JsonNode upload(String token, String knowledgeBaseId, String filename, String text)
            throws Exception {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        var response = mockMvc.perform(multipart(
                        "/api/v1/knowledge-bases/{knowledgeBaseId}/documents", knowledgeBaseId)
                        .file(new MockMultipartFile("file", filename, "text/plain", bytes))
                        .header("Authorization", "Bearer " + token))
                .andReturn();
        assertThat(response.getResponse().getStatus())
                .withFailMessage("MinIO upload failed: %s; container log: %s",
                        response.getResponse().getContentAsString(), MINIO.getLogs())
                .isEqualTo(202);
        return objectMapper.readTree(response.getResponse().getContentAsByteArray());
    }


    private JsonNode register(String email) throws Exception {
        return objectMapper.readTree(mockMvc.perform(post("/api/v1/auth/register")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"contract_version":"0.2.0-draft.5","email":"%s",
                                 "password":"synthetic-document-password"}
                                """.formatted(email)))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsByteArray());
    }

    private String createKnowledgeBase(String token, String name) throws Exception {
        JsonNode created = objectMapper.readTree(mockMvc.perform(post("/api/v1/knowledge-bases")
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"contract_version":"0.2.0-draft.5","name":"%s"}
                                """.formatted(name)))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsByteArray());
        return created.path("id").asText();
    }

    private record PublishedIndex(LeaseContext lease, UUID chunkId) {}
}
