package com.knowflow.api.document;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
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
import java.time.Duration;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Function;
import javax.sql.DataSource;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.zaxxer.hikari.HikariDataSource;
import com.knowflow.api.ai.AiInternalHealthClient;
import com.knowflow.api.ai.InternalHealth;
import com.knowflow.api.answer.AiAnswerResponse;
import com.knowflow.api.answer.TrustedAnswerRequest;
import com.knowflow.api.auth.AuthService;
import com.knowflow.api.config.IndexingProperties;
import com.knowflow.api.config.QuestionProperties;
import com.knowflow.api.error.ApiError;
import com.knowflow.api.indexing.ClaimedIndexTask;
import com.knowflow.api.indexing.LeaseContext;
import com.knowflow.api.indexing.IndexingTaskQueue;
import com.knowflow.api.indexing.IndexBatchDigest;
import com.knowflow.api.indexing.IndexBatchRequest;
import com.knowflow.api.indexing.CompletionRequest;
import com.knowflow.api.indexing.HeartbeatRequest;
import com.knowflow.api.indexing.IndexDispatch;
import com.knowflow.api.indexing.IndexManifestDigest;
import com.knowflow.api.indexing.SourceReadRequest;
import com.knowflow.api.indexing.AiExecutionCancellationClient;
import com.knowflow.api.storage.ObjectStore;
import com.knowflow.api.storage.ObjectStoreException;
import com.knowflow.api.storage.S3ObjectStore;
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
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
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
import org.testcontainers.containers.wait.strategy.WaitAllStrategy;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@SpringBootTest(properties = {
        "spring.profiles.active=database,storage",
        "knowflow.ai.internal-shared-secret=document-test-internal-secret-long-enough"
})
@AutoConfigureMockMvc
@Import(DocumentApiIntegrationTest.StorageConcurrencyTestConfiguration.class)
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
    private static final AtomicReference<CountDownLatch> AI_REQUEST_RECEIVED =
            new AtomicReference<>(new CountDownLatch(1));
    private static final AtomicReference<String> AI_HANDLER_FAILURE = new AtomicReference<>();
    private static final AtomicReference<Integer> AI_HTTP_STATUS = new AtomicReference<>(200);
    private static final AtomicReference<CountDownLatch> AI_RESPONSE_GATE =
            new AtomicReference<>(new CountDownLatch(0));
    private static final AtomicReference<String> AI_STREAM_TERMINAL_EVENT =
            new AtomicReference<>("completed");
    private static final AtomicReference<CountDownLatch> AI_STREAM_TERMINAL_GATE =
            new AtomicReference<>(new CountDownLatch(0));
    private static final AtomicReference<CountDownLatch> AI_STREAM_SOURCES_SENT =
            new AtomicReference<>(new CountDownLatch(0));
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
            .waitingFor(new WaitAllStrategy()
                    .withStrategy(Wait.forLogMessage(".*\\*\\* Starting MinIO \\*\\*.*", 1))
                    .withStrategy(Wait.forHttp("/minio/health/ready").forPort(9000)
                            .forStatusCode(200).withStartupTimeout(Duration.ofSeconds(90)))
                    .withStartupTimeout(Duration.ofSeconds(90)));

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private DataSource applicationDataSource;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private com.knowflow.api.storage.S3ObjectStore objectStore;

    @Autowired
    private BlockingObjectStore blockingObjectStore;

    @Autowired
    private TransactionTemplate transactions;

    @Autowired
    private AiExecutionCancellationClient cancellationClient;

    @Autowired
    private AiInternalHealthClient aiHealthClient;

    @Autowired
    private IndexingTaskQueue indexingTasks;

    @Autowired
    private IndexingProperties indexingProperties;

    @Autowired
    private QuestionProperties questionProperties;

    @Autowired
    private com.knowflow.api.answer.QuestionRecoveryService questionRecovery;

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
        AI_REQUEST_RECEIVED.set(new CountDownLatch(1));
        AI_HANDLER_FAILURE.set(null);
        AI_HTTP_STATUS.set(200);
        AI_RESPONSE_GATE.set(new CountDownLatch(0));
        AI_STREAM_TERMINAL_EVENT.set("completed");
        AI_STREAM_TERMINAL_GATE.set(new CountDownLatch(0));
        AI_STREAM_SOURCES_SENT.set(new CountDownLatch(0));
        questionProperties.setTotalBudgetSeconds(30);
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
                .andExpect(jsonPath("$.contract_version").value("0.2.0"))
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
                .andExpect(jsonPath("$.active_index_version_id").doesNotHaveJsonPath())
                .andExpect(jsonPath("$.byte_size").value(text.length))
                .andExpect(jsonPath("$.latest_task_id").value(taskId))
                .andExpect(jsonPath("$.latest_task_status").value("QUEUED"))
                .andExpect(jsonPath("$.source_sha256").value(
                        "73621482ff083eca9ea88880393298f7d3f53402200780b0c16354a9beb0535a"));
        mockMvc.perform(get("/api/v1/tasks/{taskId}", taskId)
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("QUEUED"))
                .andExpect(jsonPath("$.attempt_count").value(0))
                .andExpect(jsonPath("$.failure_code").doesNotHaveJsonPath())
                .andExpect(jsonPath("$.lease_id").doesNotExist());
        mockMvc.perform(get("/api/v1/knowledge-bases/{knowledgeBaseId}/documents",
                        knowledgeBaseId).header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items.length()").value(1))
                .andExpect(jsonPath("$.items[0].id").value(documentId))
                .andExpect(jsonPath("$.items[0].latest_task_id").value(taskId))
                .andExpect(jsonPath("$.items[0].latest_task_status").value("QUEUED"));

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
                    "The plain ID s1 remains; [s10] and [s1] are citations.", true,
                    java.util.List.of(
                            new AiAnswerResponse.AiSource("s1", scope.documentId(),
                                    scope.contentVersionId(), scope.indexVersionId(),
                                    published.chunkId(), new AiAnswerResponse.Locator("text_range",
                                    null, 0, evidence.codePointCount(0, evidence.length()),
                                    "unicode_code_point"), evidence),
                            new AiAnswerResponse.AiSource("s10", scope.documentId(),
                                    scope.contentVersionId(), scope.indexVersionId(),
                                    published.chunkId(), new AiAnswerResponse.Locator("text_range",
                                    null, 0, evidence.codePointCount(0, evidence.length()),
                                    "unicode_code_point"), evidence)));
        });

        var answerResult = mockMvc.perform(post(
                        "/api/v1/knowledge-bases/{knowledgeBaseId}/questions", knowledgeBaseId)
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsBytes(new com.knowflow.api.answer.PublicQuestion(
                                "What evidence is stored?"))))
                .andReturn();
        answerResult = dispatchAsync(answerResult);
        assertThat(answerResult.getResponse().getStatus())
                .withFailMessage("AI HTTP fixture failed: %s", AI_HANDLER_FAILURE.get())
                .isEqualTo(200);
        JsonNode answer = objectMapper.readTree(answerResult.getResponse().getContentAsByteArray());
        assertThat(answer.path("contract_version").asText()).isEqualTo(ApiError.CONTRACT_VERSION);
        assertThat(answer.path("has_answer").asBoolean()).isTrue();
        assertThat(answer.path("sources")).hasSize(2);
        assertThat(answer.path("sources").get(0).path("quote").asText()).isEqualTo(evidence);
        String sourceId = answer.path("sources").get(0).path("source_id").asText();
        String sourceId10 = answer.path("sources").get(1).path("source_id").asText();
        assertThat(answer.path("answer").asText()).isEqualTo(
                "The plain ID s1 remains; [" + sourceId10 + "] and [" + sourceId
                        + "] are citations.");
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
    void deletingDocumentDuringAnswerGenerationPreventsAnswerAndSourcePublication() throws Exception {
        JsonNode owner = register("question-delete-during-generation@example.test");
        String token = owner.path("access_token").asText();
        String knowledgeBaseId = createKnowledgeBase(token, "Delete during generation");
        String evidence = "This evidence must not escape after deletion.";
        PublishedIndex published = publishDocument(token, knowledgeBaseId,
                "evidence.txt", evidence, "question-delete-during-generation-index");
        AI_RESPONSE.set(request -> {
            TrustedAnswerRequest.IndexScope scope = request.scope().indexes().getFirst();
            return new AiAnswerResponse(ApiError.CONTRACT_VERSION, request.requestId(),
                    "Secret answer [deleted-source].", true,
                    java.util.List.of(new AiAnswerResponse.AiSource("deleted-source",
                            scope.documentId(), scope.contentVersionId(), scope.indexVersionId(),
                            published.chunkId(), new AiAnswerResponse.Locator("text_range",
                            null, 0, evidence.codePointCount(0, evidence.length()),
                            "unicode_code_point"), evidence)));
        });
        CountDownLatch responseGate = new CountDownLatch(1);
        AI_RESPONSE_GATE.set(responseGate);

        var initial = mockMvc.perform(post(
                        "/api/v1/knowledge-bases/{knowledgeBaseId}/questions", knowledgeBaseId)
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsBytes(
                                new com.knowflow.api.answer.PublicQuestion("What is private?"))))
                .andReturn();
        try {
            assertThat(initial.getRequest().isAsyncStarted()).isTrue();
            assertThat(AI_REQUEST_RECEIVED.get().await(5, TimeUnit.SECONDS)).isTrue();
            mockMvc.perform(delete("/api/v1/documents/{documentId}",
                            published.lease().documentId())
                            .header("Authorization", "Bearer " + token))
                    .andExpect(status().isNoContent());
        } finally {
            responseGate.countDown();
        }

        var result = mockMvc.perform(asyncDispatch(initial)).andReturn();
        assertThat(result.getResponse().getStatus()).isEqualTo(409);
        assertThat(result.getResponse().getContentAsString())
                .doesNotContain("Secret answer", evidence, "deleted-source");
        var failedQuestion = jdbc.queryForMap("""
                SELECT status, failure_code, answer_text FROM knowflow.questions
                 ORDER BY created_at DESC LIMIT 1
                """);
        assertThat(failedQuestion.get("status")).isEqualTo("FAILED");
        assertThat(failedQuestion.get("failure_code")).isEqualTo("DOCUMENT_UNAVAILABLE");
        assertThat(failedQuestion.get("answer_text")).isNull();
        assertThat(jdbc.queryForObject("""
                SELECT count(*) FROM knowflow.question_sources qs
                  JOIN knowflow.questions q ON q.id = qs.question_id
                 WHERE q.request_id = ?
                """, Integer.class, AI_RECEIVED_REQUEST_ID.get())).isZero();
    }

    @Test
    void publicAnswerStreamForwardsValidatedEventsAndPersistsTheAnswer() throws Exception {
        JsonNode owner = register("question-stream@example.test");
        String token = owner.path("access_token").asText();
        String knowledgeBaseId = createKnowledgeBase(token, "Stream answer");
        String evidence = "Streaming evidence is persisted.";
        PublishedIndex published = publishDocument(token, knowledgeBaseId,
                "stream.txt", evidence, "question-stream-index");
        AI_RESPONSE.set(request -> {
            TrustedAnswerRequest.IndexScope scope = request.scope().indexes().getFirst();
            return new AiAnswerResponse(ApiError.CONTRACT_VERSION, request.requestId(),
                    "Streaming answer [stream-source]", true,
                    List.of(new AiAnswerResponse.AiSource("stream-source", scope.documentId(),
                            scope.contentVersionId(), scope.indexVersionId(), published.chunkId(),
                            new AiAnswerResponse.Locator("text_range", null, 0,
                                    evidence.codePointCount(0, evidence.length()), "unicode_code_point"), evidence)),
                    new com.knowflow.api.answer.ModelProfile("BAAI/bge-m3", "deepseek-flash"));
        });
        CountDownLatch terminalGate = new CountDownLatch(1);
        AI_STREAM_TERMINAL_GATE.set(terminalGate);
        AI_STREAM_SOURCES_SENT.set(new CountDownLatch(1));
        var initial = mockMvc.perform(post(
                        "/api/v1/knowledge-bases/{knowledgeBaseId}/questions/stream", knowledgeBaseId)
                        .header("Authorization", "Bearer " + token)
                        .header("X-Request-ID", "stream-client-request")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.TEXT_EVENT_STREAM)
                        .content(objectMapper.writeValueAsBytes(new com.knowflow.api.answer.PublicQuestion(
                                "What is streamed?"))))
                .andReturn();
        assertThat(initial.getRequest().isAsyncStarted()).isTrue();
        try {
            assertThat(AI_STREAM_SOURCES_SENT.get().await(5, TimeUnit.SECONDS)).isTrue();
            awaitSseEvent(initial, "event:sources");
            UUID questionId = jdbc.queryForObject("SELECT id FROM knowflow.questions WHERE request_id = ?",
                    UUID.class, AI_RECEIVED_REQUEST_ID.get());
            assertThat(jdbc.queryForObject("SELECT status FROM knowflow.questions WHERE id = ?",
                    String.class, questionId)).isEqualTo("PROCESSING");
            assertThat(jdbc.queryForObject("""
                    SELECT embedding_model_profile_id || ':' || llm_model_profile_id
                      FROM knowflow.questions WHERE id = ?
                    """, String.class, questionId)).isEqualTo("BAAI/bge-m3:deepseek-flash");
            assertThat(jdbc.queryForObject("SELECT answer_text FROM knowflow.questions WHERE id = ?",
                    String.class, questionId)).isNull();
            assertThat(jdbc.queryForObject("SELECT count(*) FROM knowflow.question_sources WHERE question_id = ?",
                    Integer.class, questionId)).isZero();
        } finally {
            terminalGate.countDown();
        }
        var streamed = mockMvc.perform(asyncDispatch(initial)).andReturn();
        assertThat(streamed.getResponse().getStatus()).isEqualTo(200);
        String body = streamed.getResponse().getContentAsString();
        assertThat(body).contains("event:started", "event:delta", "event:sources", "event:completed")
                .doesNotContain("stream-source");
        assertThat(AI_RECEIVED_REQUEST_ID.get())
                .isEqualTo(streamed.getResponse().getHeader("X-Request-ID"))
                .isEqualTo("stream-client-request");
        assertSseContractFrames(body);
        assertThat(jdbc.queryForObject("SELECT status FROM knowflow.questions WHERE request_id = ?",
                String.class, AI_RECEIVED_REQUEST_ID.get())).isEqualTo("SUCCEEDED");
        assertThat(jdbc.queryForObject("""
                SELECT embedding_model_profile_id || ':' || llm_model_profile_id
                  FROM knowflow.questions WHERE request_id = ?
                """, String.class, AI_RECEIVED_REQUEST_ID.get()))
                .isEqualTo("BAAI/bge-m3:deepseek-flash");
        assertThat(jdbc.queryForObject("""
                SELECT count(*) FROM knowflow.question_sources qs
                  JOIN knowflow.questions q ON q.id = qs.question_id
                 WHERE q.request_id = ?
                """, Integer.class, AI_RECEIVED_REQUEST_ID.get())).isEqualTo(1);
    }

    @Test
    void publicAnswerStreamErrorsAndTruncationAfterSourcesMarkQuestionFailed() throws Exception {
        JsonNode owner = register("question-stream-failure@example.test");
        String token = owner.path("access_token").asText();
        String knowledgeBaseId = createKnowledgeBase(token, "Stream failures");
        String evidence = "Streaming evidence is persisted.";
        PublishedIndex published = publishDocument(token, knowledgeBaseId,
                "stream-failure.txt", evidence, "question-stream-failure-index");
        AI_RESPONSE.set(request -> {
            TrustedAnswerRequest.IndexScope scope = request.scope().indexes().getFirst();
            return new AiAnswerResponse(ApiError.CONTRACT_VERSION, request.requestId(),
                    "Streaming answer [stream-source]", true,
                    List.of(new AiAnswerResponse.AiSource("stream-source", scope.documentId(),
                            scope.contentVersionId(), scope.indexVersionId(), published.chunkId(),
                            new AiAnswerResponse.Locator("text_range", null, 0,
                                    evidence.codePointCount(0, evidence.length()), "unicode_code_point"), evidence)));
        });

        for (String terminal : List.of("error", "truncated", "cancelled")) {
            AI_STREAM_TERMINAL_EVENT.set(terminal);
            CountDownLatch terminalGate = new CountDownLatch("truncated".equals(terminal) ? 1 : 0);
            AI_STREAM_TERMINAL_GATE.set(terminalGate);
            AI_STREAM_SOURCES_SENT.set(new CountDownLatch(1));
            var initial = mockMvc.perform(post(
                            "/api/v1/knowledge-bases/{knowledgeBaseId}/questions/stream", knowledgeBaseId)
                            .header("Authorization", "Bearer " + token)
                            .contentType(MediaType.APPLICATION_JSON)
                            .accept(MediaType.TEXT_EVENT_STREAM)
                            .content(objectMapper.writeValueAsBytes(new com.knowflow.api.answer.PublicQuestion(
                                    "What failed after sources?"))))
                    .andReturn();
            org.springframework.test.web.servlet.MvcResult streamed;
            try {
                if ("truncated".equals(terminal)) {
                    assertThat(AI_STREAM_SOURCES_SENT.get().await(5, TimeUnit.SECONDS)).isTrue();
                    awaitSseEvent(initial, "event:sources");
                }
                terminalGate.countDown();
                streamed = mockMvc.perform(asyncDispatch(initial)).andReturn();
            } finally {
                terminalGate.countDown();
            }
            String requestId = AI_RECEIVED_REQUEST_ID.get();
            String body = streamed.getResponse().getContentAsString();
            assertThat(requestId).isEqualTo(streamed.getResponse().getHeader("X-Request-ID"));
            assertThat(body).contains("event:sources",
                    "event:" + ("cancelled".equals(terminal) ? "cancelled" : "error"))
                    .doesNotContain("event:completed");
            assertSseContractFrames(body);
            var failed = jdbc.queryForMap("""
                    SELECT status, failure_code, answer_text FROM knowflow.questions WHERE request_id = ?
                    """, requestId);
            boolean cancelled = "cancelled".equals(terminal);
            assertThat(failed.get("status")).isEqualTo(cancelled ? "CANCELLED" : "FAILED");
            assertThat(failed.get("failure_code"))
                    .isEqualTo(cancelled ? null : "AI_PROCESSING_FAILED");
            assertThat(failed.get("answer_text")).isNull();
            assertThat(jdbc.queryForObject("""
                    SELECT count(*) FROM knowflow.question_sources qs
                      JOIN knowflow.questions q ON q.id = qs.question_id
                     WHERE q.request_id = ?
                    """, Integer.class, requestId)).isZero();
        }
    }

    @Test
    void publicAnswerStreamDisconnectAfterSourcesMarksQuestionCancelled() throws Exception {
        JsonNode owner = register("question-stream-disconnect@example.test");
        String token = owner.path("access_token").asText();
        String knowledgeBaseId = createKnowledgeBase(token, "Stream disconnect");
        String evidence = "Streaming disconnect evidence.";
        PublishedIndex published = publishDocument(token, knowledgeBaseId,
                "stream-disconnect.txt", evidence, "question-stream-disconnect-index");
        AI_RESPONSE.set(request -> streamedAnswer(request, published, evidence));
        CountDownLatch terminalGate = new CountDownLatch(1);
        AI_STREAM_TERMINAL_GATE.set(terminalGate);
        AI_STREAM_SOURCES_SENT.set(new CountDownLatch(1));

        var initial = mockMvc.perform(post(
                        "/api/v1/knowledge-bases/{knowledgeBaseId}/questions/stream", knowledgeBaseId)
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.TEXT_EVENT_STREAM)
                        .content(objectMapper.writeValueAsBytes(new com.knowflow.api.answer.PublicQuestion(
                                "Disconnect after sources?"))))
                .andReturn();
        try {
            assertThat(AI_STREAM_SOURCES_SENT.get().await(5, TimeUnit.SECONDS)).isTrue();
            awaitSseEvent(initial, "event:sources");
            String requestId = AI_RECEIVED_REQUEST_ID.get();
            UUID questionId = jdbc.queryForObject("SELECT id FROM knowflow.questions WHERE request_id = ?",
                    UUID.class, requestId);
            assertThat(jdbc.queryForObject("SELECT status FROM knowflow.questions WHERE id = ?",
                    String.class, questionId)).isEqualTo("PROCESSING");
            initial.getRequest().getAsyncContext().complete();
            awaitQuestionStatus(questionId, "CANCELLED");
            var cancelled = jdbc.queryForMap("""
                    SELECT failure_code, answer_text FROM knowflow.questions WHERE id = ?
                    """, questionId);
            assertThat(cancelled.get("failure_code")).isNull();
            assertThat(cancelled.get("answer_text")).isNull();
            assertThat(jdbc.queryForObject("SELECT count(*) FROM knowflow.question_sources WHERE question_id = ?",
                    Integer.class, questionId)).isZero();
        } finally {
            terminalGate.countDown();
        }
    }

    @Test
    void publicAnswerStreamTimeoutAfterSourcesMarksQuestionFailedWithTimeout() throws Exception {
        JsonNode owner = register("question-stream-timeout@example.test");
        String token = owner.path("access_token").asText();
        String knowledgeBaseId = createKnowledgeBase(token, "Stream timeout");
        String evidence = "Streaming timeout evidence.";
        PublishedIndex published = publishDocument(token, knowledgeBaseId,
                "stream-timeout.txt", evidence, "question-stream-timeout-index");
        AI_RESPONSE.set(request -> streamedAnswer(request, published, evidence));
        CountDownLatch terminalGate = new CountDownLatch(1);
        AI_STREAM_TERMINAL_GATE.set(terminalGate);
        AI_STREAM_SOURCES_SENT.set(new CountDownLatch(1));
        int originalBudget = questionProperties.getTotalBudgetSeconds();
        questionProperties.setTotalBudgetSeconds(3);

        var initial = mockMvc.perform(post(
                        "/api/v1/knowledge-bases/{knowledgeBaseId}/questions/stream", knowledgeBaseId)
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.TEXT_EVENT_STREAM)
                        .content(objectMapper.writeValueAsBytes(new com.knowflow.api.answer.PublicQuestion(
                                "Timeout after sources?"))))
                .andReturn();
        try {
            assertThat(AI_STREAM_SOURCES_SENT.get().await(5, TimeUnit.SECONDS)).isTrue();
            awaitSseEvent(initial, "event:sources");
            String requestId = AI_RECEIVED_REQUEST_ID.get();
            UUID questionId = jdbc.queryForObject("SELECT id FROM knowflow.questions WHERE request_id = ?",
                    UUID.class, requestId);
            assertThat(jdbc.queryForObject("SELECT status FROM knowflow.questions WHERE id = ?",
                    String.class, questionId)).isEqualTo("PROCESSING");
            awaitQuestionStatus(questionId, "FAILED");
            var failed = jdbc.queryForMap("""
                    SELECT failure_code, answer_text FROM knowflow.questions WHERE id = ?
                    """, questionId);
            assertThat(failed.get("failure_code")).isEqualTo("PROCESSING_TIMEOUT");
            assertThat(failed.get("answer_text")).isNull();
            assertThat(jdbc.queryForObject("SELECT count(*) FROM knowflow.question_sources WHERE question_id = ?",
                    Integer.class, questionId)).isZero();
            awaitSseEvent(initial, "event:error");
            var streamed = mockMvc.perform(asyncDispatch(initial)).andReturn();
            String body = streamed.getResponse().getContentAsString();
            assertSseContractFrames(body);
            assertThat(body).contains("PROCESSING_TIMEOUT").doesNotContain("event:completed");
            assertThat(body.split("event:error", -1)).hasSize(2);
        } finally {
            terminalGate.countDown();
            questionProperties.setTotalBudgetSeconds(originalBudget);
        }
    }

    @Test
    void expiredQuestionRecoveryWinsAgainstALateStreamCompletion() throws Exception {
        String token = register("question-recovery@example.test").path("access_token").asText();
        String knowledgeBaseId = createKnowledgeBase(token, "Question recovery");
        String evidence = "Recovery evidence.";
        PublishedIndex published = publishDocument(token, knowledgeBaseId,
                "recovery.txt", evidence, "question-recovery-index");
        AI_RESPONSE.set(request -> streamedAnswer(request, published, evidence));
        CountDownLatch terminalGate = new CountDownLatch(1);
        AI_STREAM_TERMINAL_GATE.set(terminalGate);
        AI_STREAM_SOURCES_SENT.set(new CountDownLatch(1));

        var initial = mockMvc.perform(post(
                        "/api/v1/knowledge-bases/{knowledgeBaseId}/questions/stream", knowledgeBaseId)
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.TEXT_EVENT_STREAM)
                        .content("{\"question\":\"What is the recovery evidence?\"}"))
                .andReturn();
        UUID questionId;
        try {
            assertThat(AI_STREAM_SOURCES_SENT.get().await(5, TimeUnit.SECONDS)).isTrue();
            awaitSseEvent(initial, "event:sources");
            String requestId = AI_RECEIVED_REQUEST_ID.get();
            questionId = jdbc.queryForObject("SELECT id FROM knowflow.questions WHERE request_id = ?",
                    UUID.class, requestId);
            jdbc.update("UPDATE knowflow.questions SET deadline_at = clock_timestamp() - INTERVAL '3 seconds' WHERE id = ?",
                    questionId);
            questionRecovery.recoverExpiredQuestions();
            assertThat(jdbc.queryForObject("SELECT status FROM knowflow.questions WHERE id = ?",
                    String.class, questionId)).isEqualTo("FAILED");
            assertThat(jdbc.queryForObject("SELECT failure_code FROM knowflow.questions WHERE id = ?",
                    String.class, questionId)).isEqualTo("PROCESSING_TIMEOUT");
        } finally {
            terminalGate.countDown();
        }
        var finished = mockMvc.perform(asyncDispatch(initial)).andReturn();
        assertThat(finished.getResponse().getStatus()).isEqualTo(200);
        String body = finished.getResponse().getContentAsString();
        assertThat(body.split("event:error", -1)).hasSize(2);
        assertThat(body).doesNotContain("event:completed");
        String errorData = body.substring(body.indexOf("event:error")).lines()
                .filter(line -> line.startsWith("data:"))
                .map(line -> line.substring("data:".length()).trim())
                .findFirst().orElseThrow();
        JsonNode errorEvent = objectMapper.readTree(errorData);
        assertThat(errorEvent.path("code").asText()).isEqualTo("PROCESSING_TIMEOUT");
        assertThat(errorEvent.path("message").asText()).isEqualTo("PROCESSING_TIMEOUT");
        assertThat(errorEvent.path("retryable").asBoolean()).isTrue();
        assertThat(jdbc.queryForObject("SELECT status FROM knowflow.questions WHERE id = ?",
                String.class, questionId)).isEqualTo("FAILED");
        assertThat(jdbc.queryForObject("SELECT failure_code FROM knowflow.questions WHERE id = ?",
                String.class, questionId)).isEqualTo("PROCESSING_TIMEOUT");
        assertThat(jdbc.queryForObject("SELECT answer_text FROM knowflow.questions WHERE id = ?",
                String.class, questionId)).isNull();
        assertThat(jdbc.queryForObject("SELECT count(*) FROM knowflow.question_sources WHERE question_id = ?",
                Integer.class, questionId)).isZero();
    }

    @Test
    void forwardsQuestionsThroughTheSharedContractLengthLimit() throws Exception {
        JsonNode owner = register("question-length-owner@example.test");
        String token = owner.path("access_token").asText();
        String knowledgeBaseId = createKnowledgeBase(token, "Question length");
        publishDocument(token, knowledgeBaseId, "evidence.txt", "Trusted evidence.",
                "question-length-index");
        AtomicReference<Integer> forwardedCodePoints = new AtomicReference<>();
        AI_RESPONSE.set(request -> {
            forwardedCodePoints.set(request.question().codePointCount(0, request.question().length()));
            return new AiAnswerResponse(ApiError.CONTRACT_VERSION, request.requestId(),
                    "No supporting evidence was found.", false, java.util.List.of());
        });

        for (int length : java.util.List.of(801, 16000)) {
            var result = mockMvc.perform(post(
                            "/api/v1/knowledge-bases/{knowledgeBaseId}/questions", knowledgeBaseId)
                            .header("Authorization", "Bearer " + token)
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsBytes(
                                    new com.knowflow.api.answer.PublicQuestion("问".repeat(length)))))
                    .andReturn();
            result = dispatchAsync(result);

            assertThat(result.getResponse().getStatus())
                    .withFailMessage("AI HTTP fixture failed: %s", AI_HANDLER_FAILURE.get())
                    .isEqualTo(200);
            assertThat(forwardedCodePoints.get()).isEqualTo(length);
        }
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

        var unsupportedResult = mockMvc.perform(post("/api/v1/knowledge-bases/{knowledgeBaseId}/questions",
                        knowledgeBaseId)
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsBytes(new com.knowflow.api.answer.PublicQuestion(
                                "What does the document say?"))))
                .andReturn();
        unsupportedResult = dispatchAsync(unsupportedResult);
        assertThat(unsupportedResult.getResponse().getStatus()).isEqualTo(502);
        assertThat(objectMapper.readTree(unsupportedResult.getResponse().getContentAsByteArray())
                .path("code").asText()).isEqualTo("AI_PROCESSING_FAILED");
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
        refusalResult = dispatchAsync(refusalResult);
        assertThat(refusalResult.getResponse().getStatus())
                .withFailMessage("AI HTTP fixture failed: %s", AI_HANDLER_FAILURE.get())
                .isEqualTo(200);
        JsonNode refusal = objectMapper.readTree(refusalResult.getResponse().getContentAsByteArray());
        assertThat(refusal.path("has_answer").asBoolean()).isFalse();
        assertThat(refusal.path("sources")).isEmpty();
    }

    @Test
    void pythonUnavailableMapsToRetryablePublicFailureAndMarksQuestionFailed() throws Exception {
        JsonNode owner = register("question-ai-unavailable@example.test");
        String token = owner.path("access_token").asText();
        String knowledgeBaseId = createKnowledgeBase(token, "AI unavailable");
        publishDocument(token, knowledgeBaseId, "evidence.txt", "Local evidence text.",
                "ai-unavailable-index");
        AI_HTTP_STATUS.set(503);

        var result = mockMvc.perform(post(
                        "/api/v1/knowledge-bases/{knowledgeBaseId}/questions", knowledgeBaseId)
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsBytes(new com.knowflow.api.answer.PublicQuestion(
                                "What is the evidence?"))))
                .andReturn();
        result = dispatchAsync(result);

        assertThat(result.getResponse().getStatus()).isEqualTo(502);
        JsonNode error = objectMapper.readTree(result.getResponse().getContentAsByteArray());
        assertThat(error.path("code").asText()).isEqualTo("AI_PROCESSING_FAILED");
        assertThat(error.path("retryable").asBoolean()).isTrue();
        assertThat(result.getResponse().getContentAsString())
                .doesNotContain("UPSTREAM_PRIVATE_MARKER");
        assertThat(AI_HANDLER_FAILURE.get()).isNull();
        var failedQuestion = jdbc.queryForMap("""
                SELECT status, failure_code FROM knowflow.questions
                 ORDER BY created_at DESC LIMIT 1
                """);
        assertThat(failedQuestion.get("status")).isEqualTo("FAILED");
        assertThat(failedQuestion.get("failure_code")).isEqualTo("AI_PROCESSING_FAILED");
    }

    @Test
    void pythonAnswerTimeoutMapsToRetryableGatewayTimeoutAndMarksQuestionFailed() throws Exception {
        JsonNode owner = register("question-ai-timeout@example.test");
        String token = owner.path("access_token").asText();
        String knowledgeBaseId = createKnowledgeBase(token, "AI timeout");
        publishDocument(token, knowledgeBaseId, "evidence.txt", "Local timeout evidence.",
                "ai-timeout-index");
        CountDownLatch responseGate = new CountDownLatch(1);
        AI_RESPONSE_GATE.set(responseGate);
        int originalBudget = questionProperties.getTotalBudgetSeconds();
        questionProperties.setTotalBudgetSeconds(1);

        org.springframework.test.web.servlet.MvcResult result;
        try {
            var initial = mockMvc.perform(post(
                            "/api/v1/knowledge-bases/{knowledgeBaseId}/questions", knowledgeBaseId)
                            .header("Authorization", "Bearer " + token)
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsBytes(
                                    new com.knowflow.api.answer.PublicQuestion(
                                            "What is the evidence?"))))
                    .andReturn();
            assertThat(initial.getRequest().isAsyncStarted()).isTrue();
            assertThat(AI_REQUEST_RECEIVED.get().await(5, TimeUnit.SECONDS)).isTrue();
            assertThat(initial.getAsyncResult(5_000)).isNotNull();
            result = mockMvc.perform(asyncDispatch(initial)).andReturn();
        } finally {
            responseGate.countDown();
            questionProperties.setTotalBudgetSeconds(originalBudget);
        }

        assertThat(result.getResponse().getStatus()).isEqualTo(504);
        JsonNode error = objectMapper.readTree(result.getResponse().getContentAsByteArray());
        assertThat(error.path("code").asText()).isEqualTo("PROCESSING_TIMEOUT");
        assertThat(error.path("retryable").asBoolean()).isTrue();
        assertThat(result.getResponse().getContentAsString())
                .doesNotContain("UPSTREAM_PRIVATE_MARKER");
        assertThat(AI_RECEIVED_REQUEST_ID.get()).isNotBlank();
        var failedQuestion = jdbc.queryForMap("""
                SELECT status, failure_code FROM knowflow.questions
                 ORDER BY created_at DESC LIMIT 1
                """);
        assertThat(failedQuestion.get("status")).isEqualTo("FAILED");
        assertThat(failedQuestion.get("failure_code")).isEqualTo("PROCESSING_TIMEOUT");
    }

    @Test
    void rejectedQuestionCompletionPreservesTimeoutFailureCode() throws Exception {
        JsonNode owner = register("question-expired-completion@example.test");
        String token = owner.path("access_token").asText();
        String knowledgeBaseId = createKnowledgeBase(token, "Expired completion");
        publishDocument(token, knowledgeBaseId, "evidence.txt", "Expiration evidence.",
                "expired-completion-index");
        CountDownLatch responseGate = new CountDownLatch(1);
        AI_RESPONSE_GATE.set(responseGate);

        var initial = mockMvc.perform(post(
                        "/api/v1/knowledge-bases/{knowledgeBaseId}/questions", knowledgeBaseId)
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsBytes(
                                new com.knowflow.api.answer.PublicQuestion("What is required?"))))
                .andReturn();
        org.springframework.test.web.servlet.MvcResult result;
        UUID questionId;
        try {
            assertThat(initial.getRequest().isAsyncStarted()).isTrue();
            assertThat(AI_REQUEST_RECEIVED.get().await(5, TimeUnit.SECONDS)).isTrue();
            questionId = jdbc.queryForObject("SELECT id FROM knowflow.questions WHERE request_id = ?",
                    UUID.class, AI_RECEIVED_REQUEST_ID.get());
            jdbc.update("UPDATE knowflow.questions SET deadline_at = clock_timestamp() - INTERVAL '1 second' WHERE id = ?",
                    questionId);
            responseGate.countDown();
            assertThat(initial.getAsyncResult(5_000)).isNotNull();
            result = mockMvc.perform(asyncDispatch(initial)).andReturn();
        } finally {
            responseGate.countDown();
        }

        assertThat(result.getResponse().getStatus()).isEqualTo(504);
        JsonNode error = objectMapper.readTree(result.getResponse().getContentAsByteArray());
        assertThat(error.path("code").asText()).isEqualTo("PROCESSING_TIMEOUT");
        assertThat(error.path("retryable").asBoolean()).isTrue();
        var failedQuestion = jdbc.queryForMap("""
                SELECT status, failure_code, answer_text FROM knowflow.questions WHERE id = ?
                """, questionId);
        assertThat(failedQuestion.get("status")).isEqualTo("FAILED");
        assertThat(failedQuestion.get("failure_code")).isEqualTo("PROCESSING_TIMEOUT");
        assertThat(failedQuestion.get("answer_text")).isNull();
        assertThat(jdbc.queryForObject("SELECT count(*) FROM knowflow.question_sources WHERE question_id = ?",
                Integer.class, questionId)).isZero();
    }

    @Test
    void finalAnswerTransactionUsesRemainingDeadlineAndCannotCommitAfterLockWaitTimeout()
            throws Exception {
        JsonNode owner = register("question-writeback-timeout@example.test");
        String token = owner.path("access_token").asText();
        String knowledgeBaseId = createKnowledgeBase(token, "Answer writeback timeout");
        publishDocument(token, knowledgeBaseId,
                "evidence.txt", "Writeback lock evidence.", "writeback-timeout-index");
        CountDownLatch responseGate = new CountDownLatch(1);
        AI_RESPONSE_GATE.set(responseGate);
        int originalBudget = questionProperties.getTotalBudgetSeconds();
        questionProperties.setTotalBudgetSeconds(5);
        CountDownLatch lockHeld = new CountDownLatch(1);
        CountDownLatch releaseLock = new CountDownLatch(1);
        var lockExecutor = Executors.newSingleThreadExecutor();
        java.util.concurrent.Future<?> lockTask = null;
        UUID questionId = null;
        try {
            var initial = mockMvc.perform(post(
                            "/api/v1/knowledge-bases/{knowledgeBaseId}/questions", knowledgeBaseId)
                            .header("Authorization", "Bearer " + token)
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsBytes(
                                    new com.knowflow.api.answer.PublicQuestion(
                                            "What is the evidence?"))))
                    .andReturn();
            assertThat(initial.getRequest().isAsyncStarted()).isTrue();
            assertThat(AI_REQUEST_RECEIVED.get().await(5, TimeUnit.SECONDS)).isTrue();
            questionId = jdbc.queryForObject("""
                    SELECT id FROM knowflow.questions ORDER BY created_at DESC LIMIT 1
                    """, UUID.class);
            UUID lockedQuestionId = questionId;
            lockTask = lockExecutor.submit(() -> transactions.executeWithoutResult(status -> {
                jdbc.queryForObject("SELECT id FROM knowflow.questions WHERE id = ? FOR UPDATE",
                        UUID.class, lockedQuestionId);
                lockHeld.countDown();
                try {
                    releaseLock.await();
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(interrupted);
                }
            }));
            assertThat(lockHeld.await(5, TimeUnit.SECONDS)).isTrue();
            responseGate.countDown();
            awaitQuestionWritebackLockWait();
            awaitQuestionWritebackLockWaitEnded();
            releaseLock.countDown();
            lockTask.get(5, TimeUnit.SECONDS);
            assertThat(initial.getAsyncResult(5_000)).isNotNull();
            var result = mockMvc.perform(asyncDispatch(initial)).andReturn();
            assertThat(result.getResponse().getStatus())
                    .withFailMessage("Timeout response: %s", result.getResponse().getContentAsString())
                    .isEqualTo(504);
        } finally {
            responseGate.countDown();
            questionProperties.setTotalBudgetSeconds(originalBudget);
            releaseLock.countDown();
            if (lockTask != null) {
                lockTask.get(5, TimeUnit.SECONDS);
            }
            lockExecutor.shutdownNow();
        }

        awaitQuestionStatus(questionId, "FAILED");
        var failedQuestion = jdbc.queryForMap("""
                SELECT status, failure_code, answer_text FROM knowflow.questions
                 WHERE id = ?
                """, questionId);
        assertThat(failedQuestion.get("failure_code")).isEqualTo("PROCESSING_TIMEOUT");
        assertThat(failedQuestion.get("answer_text")).isNull();
    }

    @Test
    void snapshotCreationUsesRequestDeadlineAndRollsBackWhenForeignKeyLockWaits()
            throws Exception {
        JsonNode owner = register("question-snapshot-timeout@example.test");
        String token = owner.path("access_token").asText();
        String knowledgeBaseId = createKnowledgeBase(token, "Snapshot lock timeout");
        publishDocument(token, knowledgeBaseId, "evidence.txt", "Snapshot timeout evidence.",
                "snapshot-timeout-index");
        UUID knowledgeBaseUuid = UUID.fromString(knowledgeBaseId);
        CountDownLatch lockHeld = new CountDownLatch(1);
        CountDownLatch releaseLock = new CountDownLatch(1);
        var lockExecutor = Executors.newSingleThreadExecutor();
        var lockTask = lockExecutor.submit(() -> transactions.executeWithoutResult(status -> {
            jdbc.queryForObject("SELECT id FROM knowflow.knowledge_bases WHERE id = ? FOR UPDATE",
                    UUID.class, knowledgeBaseUuid);
            lockHeld.countDown();
            try {
                releaseLock.await();
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(interrupted);
            }
        }));
        assertThat(lockHeld.await(5, TimeUnit.SECONDS)).isTrue();
        int originalBudget = questionProperties.getTotalBudgetSeconds();
        questionProperties.setTotalBudgetSeconds(1);
        try {
            var initial = mockMvc.perform(post(
                            "/api/v1/knowledge-bases/{knowledgeBaseId}/questions", knowledgeBaseId)
                            .header("Authorization", "Bearer " + token)
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsBytes(
                                    new com.knowflow.api.answer.PublicQuestion(
                                            "Wait before snapshot?"))))
                    .andReturn();
            assertThat(initial.getRequest().isAsyncStarted()).isTrue();
            assertThat(initial.getAsyncResult(5_000)).isNotNull();
            var result = mockMvc.perform(asyncDispatch(initial)).andReturn();
            assertThat(result.getResponse().getStatus())
                    .withFailMessage("Timeout response: %s", result.getResponse().getContentAsString())
                    .isEqualTo(504);
        } finally {
            questionProperties.setTotalBudgetSeconds(originalBudget);
            releaseLock.countDown();
            lockTask.get(5, TimeUnit.SECONDS);
            lockExecutor.shutdownNow();
        }
        assertThat(jdbc.queryForObject("""
                SELECT count(*) FROM knowflow.questions WHERE knowledge_base_id = ?
                """, Integer.class, knowledgeBaseUuid)).isZero();
    }

    @Test
    void timeoutCleanupWaitsForConnectionAfterInterruptInsteadOfLeavingQuestionProcessing()
            throws Exception {
        JsonNode owner = register("question-pool-timeout@example.test");
        String token = owner.path("access_token").asText();
        String knowledgeBaseId = createKnowledgeBase(token, "Question pool timeout");
        publishDocument(token, knowledgeBaseId, "evidence.txt", "Pool timeout evidence.",
                "pool-timeout-index");
        CountDownLatch responseGate = new CountDownLatch(1);
        AI_RESPONSE_GATE.set(responseGate);
        int originalBudget = questionProperties.getTotalBudgetSeconds();
        questionProperties.setTotalBudgetSeconds(1);
        List<Connection> heldConnections = new ArrayList<>();
        var connectionReleaser = Executors.newSingleThreadScheduledExecutor();

        org.springframework.test.web.servlet.MvcResult initial = mockMvc.perform(post(
                        "/api/v1/knowledge-bases/{knowledgeBaseId}/questions", knowledgeBaseId)
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsBytes(
                                new com.knowflow.api.answer.PublicQuestion("Pool pressure test"))))
                .andReturn();
        try {
            assertThat(initial.getRequest().isAsyncStarted()).isTrue();
            assertThat(AI_REQUEST_RECEIVED.get().await(5, TimeUnit.SECONDS)).isTrue();
            int poolSize = ((HikariDataSource) applicationDataSource).getMaximumPoolSize();
            for (int index = 0; index < poolSize; index++) {
                heldConnections.add(applicationDataSource.getConnection());
            }
            responseGate.countDown();
            connectionReleaser.schedule(() -> {
                try {
                    heldConnections.getFirst().close();
                } catch (java.sql.SQLException failure) {
                    throw new IllegalStateException(failure);
                }
            }, 1_100, TimeUnit.MILLISECONDS);
            assertThat(initial.getAsyncResult(5_000)).isNotNull();
            var result = mockMvc.perform(asyncDispatch(initial)).andReturn();
            assertThat(result.getResponse().getStatus())
                    .withFailMessage("Timeout response: %s", result.getResponse().getContentAsString())
                    .isEqualTo(504);
        } finally {
            responseGate.countDown();
            connectionReleaser.shutdownNow();
            for (Connection connection : heldConnections) {
                connection.close();
            }
            questionProperties.setTotalBudgetSeconds(originalBudget);
        }
        awaitQuestionStatus("FAILED");
        var failedQuestion = jdbc.queryForMap("""
                SELECT status, failure_code, answer_text FROM knowflow.questions
                 ORDER BY created_at DESC LIMIT 1
                """);
        assertThat(failedQuestion.get("failure_code")).isEqualTo("PROCESSING_TIMEOUT");
        assertThat(failedQuestion.get("answer_text")).isNull();
    }

    @Test
    void asyncQuestionCompletionCancelsProviderCallAndMarksHistoryCancelled() throws Exception {
        JsonNode owner = register("question-disconnect@example.test");
        String token = owner.path("access_token").asText();
        String knowledgeBaseId = createKnowledgeBase(token, "Question disconnect");
        publishDocument(token, knowledgeBaseId, "evidence.txt", "Local cancellation evidence.",
                "question-disconnect-index");
        CountDownLatch responseGate = new CountDownLatch(1);
        AI_RESPONSE_GATE.set(responseGate);

        var initial = mockMvc.perform(post(
                        "/api/v1/knowledge-bases/{knowledgeBaseId}/questions", knowledgeBaseId)
                        .header("Authorization", "Bearer " + token)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsBytes(
                                new com.knowflow.api.answer.PublicQuestion("Cancel this query"))))
                .andReturn();
        try {
            assertThat(initial.getRequest().isAsyncStarted()).isTrue();
            assertThat(AI_REQUEST_RECEIVED.get().await(5, TimeUnit.SECONDS)).isTrue();
            initial.getRequest().getAsyncContext().complete();
            responseGate.countDown();

            awaitQuestionStatus("CANCELLED");
            var cancelled = jdbc.queryForMap("""
                    SELECT status, failure_code, answer_text FROM knowflow.questions
                     ORDER BY created_at DESC LIMIT 1
                    """);
            assertThat(cancelled.get("failure_code")).isNull();
            assertThat(cancelled.get("answer_text")).isNull();
        } finally {
            responseGate.countDown();
        }
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
        assertThat(first.dispatch().runtimeProfile()).isEqualTo(new IndexDispatch.RuntimeProfile(
                "knowflow-index-v1", 800, 100, 16, 32, 1_048_576));
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
    void doesNotDispatchCandidateWithPipelineProfileOutsideRegisteredRuntime() throws Exception {
        JsonNode owner = register("pipeline-mismatch@example.test");
        String token = owner.path("access_token").asText();
        String knowledgeBaseId = createKnowledgeBase(token, "Pipeline mismatch");
        JsonNode uploaded = upload(token, knowledgeBaseId, "profile.txt", "profile test");
        UUID taskId = UUID.fromString(uploaded.path("task_id").asText());

        jdbc.update("""
                UPDATE knowflow.index_versions iv
                   SET pipeline_profile_id = 'unregistered-pipeline-v2'
                  FROM knowflow.indexing_tasks t
                 WHERE t.id = ? AND iv.id = t.index_version_id
                """, taskId);

        assertThat(indexingTasks.claimNext()).isEmpty();
        assertThat(jdbc.queryForObject("""
                SELECT status || ':' || failure_code FROM knowflow.indexing_tasks WHERE id = ?
                """, String.class, taskId)).isEqualTo("FAILED:INDEX_WRITE_FAILED");
        assertThat(jdbc.queryForObject("""
                SELECT status FROM knowflow.index_versions
                 WHERE id = (SELECT index_version_id FROM knowflow.indexing_tasks WHERE id = ?)
                """, String.class, taskId)).isEqualTo("FAILED");
        assertThat(jdbc.queryForObject("""
                SELECT lease_id IS NULL FROM knowflow.indexing_tasks WHERE id = ?
                """, Boolean.class, taskId)).isTrue();
    }

    @Test
    void dispatchesAndEnforcesSmallerRegisteredBatchLimits() throws Exception {
        String originalPipeline = indexingProperties.getPipelineProfileId();
        int originalChunkMax = indexingProperties.getChunkMaxCodepoints();
        int originalOverlap = indexingProperties.getOverlapCodepoints();
        int originalEmbeddingLimit = indexingProperties.getEmbeddingMaxBatchItems();
        int originalChunkLimit = indexingProperties.getMaxBatchChunks();
        try {
            indexingProperties.setPipelineProfileId("knowflow-index-v2");
            indexingProperties.setChunkMaxCodepoints(700);
            indexingProperties.setOverlapCodepoints(50);
            indexingProperties.setEmbeddingMaxBatchItems(8);
            indexingProperties.setMaxBatchChunks(1);

            JsonNode owner = register("smaller-profile@example.test");
            String token = owner.path("access_token").asText();
            String knowledgeBaseId = createKnowledgeBase(token, "Smaller profile");
            upload(token, knowledgeBaseId, "smaller.txt", "bounded index batch");
            ClaimedIndexTask claim = indexingTasks.claimNext().orElseThrow();
            JsonNode dispatch = objectMapper.valueToTree(claim.dispatch());
            assertThat(dispatch.path("runtime_profile_id").asText()).isEqualTo("runtime-default");
            assertThat(dispatch.path("runtime_profile").path("pipeline_profile_id").asText())
                    .isEqualTo(claim.lease().pipelineProfileId());
            assertThat(dispatch.path("runtime_profile").path("chunk_max_codepoints").asInt())
                    .isEqualTo(700);
            assertThat(dispatch.path("runtime_profile").path("overlap_codepoints").asInt())
                    .isEqualTo(50);
            assertThat(dispatch.path("runtime_profile").path("embedding_max_batch_items").asInt())
                    .isEqualTo(8);
            assertThat(dispatch.path("runtime_profile").path("index_max_batch_chunks").asInt())
                    .isEqualTo(1);

            String requestId = "small-batch-profile";
            IndexBatchRequest oneChunk = createBatch(claim.lease(), requestId, UUID.randomUUID(),
                    List.of("one chunk"));
            postBatch(oneChunk, requestId);

            IndexBatchRequest longChunk = createBatch(claim.lease(), requestId, UUID.randomUUID(),
                    "x".repeat(701));
            mockMvc.perform(post("/internal/v1/tasks/{taskId}/index-batches",
                            claim.lease().taskId())
                            .header("Authorization", "Bearer " + AI_SECRET)
                            .header("X-Request-ID", requestId)
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsBytes(longChunk)))
                    .andExpect(status().isPayloadTooLarge())
                    .andExpect(jsonPath("$.code").value("RESOURCE_LIMIT"));

            IndexBatchRequest twoChunks = createBatch(claim.lease(), requestId, UUID.randomUUID(),
                    List.of("first chunk", "second chunk"));
            mockMvc.perform(post("/internal/v1/tasks/{taskId}/index-batches",
                            claim.lease().taskId())
                            .header("Authorization", "Bearer " + AI_SECRET)
                            .header("X-Request-ID", requestId)
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(objectMapper.writeValueAsBytes(twoChunks)))
                    .andExpect(status().isPayloadTooLarge())
                    .andExpect(jsonPath("$.code").value("RESOURCE_LIMIT"));
        } finally {
            indexingProperties.setChunkMaxCodepoints(originalChunkMax);
            indexingProperties.setOverlapCodepoints(originalOverlap);
            indexingProperties.setEmbeddingMaxBatchItems(originalEmbeddingLimit);
            indexingProperties.setMaxBatchChunks(originalChunkLimit);
            indexingProperties.setPipelineProfileId(originalPipeline);
        }
    }

    @Test
    void appliesSmallerConfiguredIndexBatchBodyLimit() throws Exception {
        int originalLimit = indexingProperties.getMaxBatchBytes();
        try {
            indexingProperties.setMaxBatchBytes(128);

            JsonNode owner = register("small-body-profile@example.test");
            String token = owner.path("access_token").asText();
            String knowledgeBaseId = createKnowledgeBase(token, "Small body profile");
            upload(token, knowledgeBaseId, "small-body.txt", "bounded request body");
            ClaimedIndexTask claim = indexingTasks.claimNext().orElseThrow();
            assertThat(claim.dispatch().runtimeProfile().indexMaxBatchBytes()).isEqualTo(128);

            String requestId = "small-body-profile";
            IndexBatchRequest batch = createBatch(claim.lease(), requestId, UUID.randomUUID(),
                    "one chunk");
            byte[] body = objectMapper.writeValueAsBytes(batch);
            assertThat(body.length).isGreaterThan(128);
            mockMvc.perform(post("/internal/v1/tasks/{taskId}/index-batches",
                            claim.lease().taskId())
                            .header("Authorization", "Bearer " + AI_SECRET)
                            .header("X-Request-ID", requestId)
                            .contentType(MediaType.APPLICATION_JSON)
                            .content(body))
                    .andExpect(status().isPayloadTooLarge())
                    .andExpect(jsonPath("$.code").value("RESOURCE_LIMIT"));
        } finally {
            indexingProperties.setMaxBatchBytes(originalLimit);
        }
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
                "0.2.0", requestId, claim.lease()));

        var response = mockMvc.perform(post("/internal/v1/tasks/{taskId}/source",
                        claim.lease().taskId())
                        .header("Authorization", "Bearer document-test-internal-secret-long-enough")
                        .header("X-Request-ID", requestId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.APPLICATION_OCTET_STREAM)
                        .content(request))
                .andExpect(status().isOk())
                .andExpect(header().string("X-Contract-Version", "0.2.0"))
                .andExpect(header().string("X-Request-ID", requestId))
                .andExpect(header().string("X-Source-Format", "md"))
                .andExpect(header().string("X-Source-SHA256",
                        "5382bbc0935e381ac557c7a0e46d5fe8ec4480f0f2a8c12e1685afcabc408bbe"))
                .andExpect(header().doesNotExist("X-Object-Key"))
                .andReturn().getResponse();
        assertThat(response.getHeaders("X-Request-ID")).containsExactly(requestId);
        assertThat(response.getContentAsByteArray()).isEqualTo(sourceBytes);

        LeaseContext forged = new LeaseContext(claim.lease().taskId(), claim.lease().ownerId(),
                claim.lease().knowledgeBaseId(), claim.lease().documentId(),
                claim.lease().contentVersionId(), claim.lease().indexVersionId(),
                claim.lease().pipelineProfileId(), claim.lease().leaseId(),
                claim.lease().fencing(), "x".repeat(43));
        byte[] forgedRequest = objectMapper.writeValueAsBytes(new SourceReadRequest(
                "0.2.0", requestId, forged));
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
    void sourceStorageWaitDoesNotBlockHeartbeat() throws Exception {
        JsonNode owner = register("source-read-locks@example.test");
        String token = owner.path("access_token").asText();
        String knowledgeBaseId = createKnowledgeBase(token, "Source read locks");
        JsonNode uploaded = upload(token, knowledgeBaseId, "source-lock.txt", "source bytes");
        ClaimedIndexTask claim = indexingTasks.claimNext().orElseThrow();
        assertThat(claim.lease().taskId().toString()).isEqualTo(uploaded.path("task_id").asText());
        String requestId = "source-read-storage-wait";
        byte[] sourceRequest = objectMapper.writeValueAsBytes(new SourceReadRequest(
                ApiError.CONTRACT_VERSION, requestId, claim.lease()));
        BlockingObjectStore.ReadGate gate = blockingObjectStore.blockNextRead();

        try (var executor = Executors.newFixedThreadPool(2)) {
            var sourceRead = executor.submit(() -> mockMvc.perform(post(
                            "/internal/v1/tasks/{taskId}/source", claim.lease().taskId())
                    .header("Authorization", "Bearer " + AI_SECRET)
                    .header("X-Request-ID", requestId)
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_OCTET_STREAM)
                    .content(sourceRequest)).andReturn());

            assertThat(gate.started().await(5, TimeUnit.SECONDS)).isTrue();
            HeartbeatRequest heartbeat = new HeartbeatRequest(ApiError.CONTRACT_VERSION,
                    "heartbeat-during-source-read", claim.lease());
            var heartbeatCall = executor.submit(() -> mockMvc.perform(post(
                            "/internal/v1/tasks/{taskId}/heartbeat", claim.lease().taskId())
                    .header("Authorization", "Bearer " + AI_SECRET)
                    .header("X-Request-ID", heartbeat.requestId())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(objectMapper.writeValueAsBytes(heartbeat))).andReturn());
            assertThat(heartbeatCall.get(3, TimeUnit.SECONDS).getResponse().getStatus())
                    .isEqualTo(200);

            gate.release().countDown();
            assertThat(sourceRead.get(5, TimeUnit.SECONDS).getResponse().getStatus()).isEqualTo(200);
        } finally {
            gate.release().countDown();
        }
    }

    @Test
    void fileStorageWaitDoesNotBlockDeletionAndDeletedBytesAreNotReturned() throws Exception {
        JsonNode owner = register("file-read-locks@example.test");
        String token = owner.path("access_token").asText();
        String knowledgeBaseId = createKnowledgeBase(token, "File read locks");
        JsonNode uploaded = upload(token, knowledgeBaseId, "file-lock.txt", "private file bytes");
        String documentId = uploaded.path("document_id").asText();
        UUID documentUuid = UUID.fromString(documentId);
        String contentVersionId = jdbc.queryForObject("""
                SELECT current_content_version_id FROM knowflow.documents WHERE id = ?
                """, UUID.class, documentUuid).toString();
        BlockingObjectStore.ReadGate gate = blockingObjectStore.blockNextRead();

        try (var executor = Executors.newFixedThreadPool(2)) {
            var fileRead = executor.submit(() -> mockMvc.perform(get(
                            "/api/v1/documents/{documentId}/contents/{contentVersionId}/file",
                            documentId, contentVersionId)
                    .header("Authorization", "Bearer " + token)).andReturn());
            assertThat(gate.started().await(5, TimeUnit.SECONDS)).isTrue();

            var deletion = executor.submit(() -> mockMvc.perform(delete(
                            "/api/v1/documents/{documentId}", documentId)
                    .header("Authorization", "Bearer " + token)).andReturn());
            assertThat(deletion.get(3, TimeUnit.SECONDS).getResponse().getStatus()).isEqualTo(204);

            gate.release().countDown();
            assertThat(fileRead.get(5, TimeUnit.SECONDS).getResponse().getStatus()).isEqualTo(404);
        } finally {
            gate.release().countDown();
        }
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
        CompletionRequest completion = new CompletionRequest("0.2.0", requestId,
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
        CompletionRequest failure = new CompletionRequest("0.2.0", "retryable-failure",
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
        String completionRequestId = "delete-late-completion";
        String manifestHash = IndexManifestDigest.calculate(
                new IndexManifestDigest.ManifestIdentity(claim.lease().taskId(),
                        claim.lease().ownerId(), claim.lease().knowledgeBaseId(),
                        claim.lease().documentId(), claim.lease().contentVersionId(),
                        claim.lease().indexVersionId(), claim.lease().pipelineProfileId(),
                        "BAAI/bge-m3", 1024),
                1, 1, java.util.List.of(new IndexManifestDigest.BatchIdentity(
                        1, batch.batchId(), batch.batchSha256(), batch.chunks().size())));
        CompletionRequest lateCompletion = new CompletionRequest(ApiError.CONTRACT_VERSION,
                completionRequestId, claim.lease(), "SUCCEEDED",
                new CompletionRequest.Manifest(1, 1, 1024, "BAAI/bge-m3", manifestHash), null);
        mockMvc.perform(post("/internal/v1/tasks/{taskId}/completion",
                        claim.lease().taskId())
                        .header("Authorization", "Bearer " + AI_SECRET)
                        .header("X-Request-ID", completionRequestId)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsBytes(lateCompletion)))
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

    @Test
    void contentUpdatePublishesAtomicallyAndRetainsOnlyTwoSuccessfulGenerations() throws Exception {
        String token = register("update-owner@example.test").path("access_token").asText();
        String kb = createKnowledgeBase(token, "Updates");
        PublishedIndex first = publishDocument(token, kb, "first.txt", "First evidence.", "first-publish");
        UUID document = first.lease().documentId();
        var providerCalls = new java.util.concurrent.atomic.AtomicInteger();
        AI_RESPONSE.set(request -> {
            providerCalls.incrementAndGet();
            return new AiAnswerResponse(ApiError.CONTRACT_VERSION, request.requestId(),
                "Answer [s1]", true, List.of(new AiAnswerResponse.AiSource("s1", document,
                first.lease().contentVersionId(), first.lease().indexVersionId(), first.chunkId(),
                new AiAnswerResponse.Locator("text_range", null, 0, 15, "unicode_code_point"),
                "First evidence.")), new com.knowflow.api.answer.ModelProfile(
                "BAAI/bge-m3", "deepseek-flash"));
        });
        String idempotencyKey = UUID.randomUUID().toString();
        var asking = mockMvc.perform(post("/api/v1/knowledge-bases/{id}/questions", kb)
                .header("Authorization", "Bearer " + token)
                .header("Idempotency-Key", idempotencyKey).contentType(MediaType.APPLICATION_JSON)
                .content("{\"question\":\"What is the evidence?\"}")).andReturn();
        JsonNode answer = objectMapper.readTree(mockMvc.perform(asyncDispatch(asking))
                .andExpect(status().isOk()).andReturn().getResponse().getContentAsByteArray());
        String sourceId = answer.path("sources").get(0).path("source_id").asText();
        UUID questionId = jdbc.queryForObject("SELECT id FROM knowflow.questions WHERE request_id = ?",
                UUID.class, answer.path("request_id").asText());
        var duplicate = mockMvc.perform(post("/api/v1/knowledge-bases/{id}/questions", kb)
                .header("Authorization", "Bearer " + token)
                .header("Idempotency-Key", idempotencyKey).contentType(MediaType.APPLICATION_JSON)
                .content("{\"question\":\"What is the evidence?\"}")).andReturn();
        mockMvc.perform(asyncDispatch(duplicate))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.code").value("QUESTION_REQUEST_CONFLICT"));
        assertThat(providerCalls).hasValue(1);
        mockMvc.perform(get("/api/v1/questions").header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[0].question_id").value(questionId.toString()));
        mockMvc.perform(get("/api/v1/questions/{id}", questionId)
                .header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.sources[0].state").value("AVAILABLE"))
                .andExpect(jsonPath("$.embedding_model_profile_id").value("BAAI/bge-m3"))
                .andExpect(jsonPath("$.llm_model_profile_id").value("deepseek-flash"))
                .andExpect(jsonPath("$.sources[0].quote").value("First evidence."));
        JsonNode secondTask = updateContent(token, document, "second.md", "Second evidence.");
        assertThat(jdbc.queryForObject("SELECT current_content_version_id FROM knowflow.documents WHERE id = ?",
                UUID.class, document)).isEqualTo(first.lease().contentVersionId());
        assertThat(jdbc.queryForObject("SELECT active_index_version_id FROM knowflow.documents WHERE id = ?",
                UUID.class, document)).isEqualTo(first.lease().indexVersionId());
        mockMvc.perform(multipart("/api/v1/documents/{id}/contents", document)
                .file(new MockMultipartFile("file", "duplicate.txt", "text/plain", "Duplicate".getBytes(StandardCharsets.UTF_8)))
                .header("Authorization", "Bearer " + token)).andExpect(status().isConflict());
        PublishedIndex second = publishQueued(secondTask, "Second evidence.", "second-publish");
        mockMvc.perform(get("/api/v1/sources/{id}", sourceId)
                .header("Authorization", "Bearer " + token)).andExpect(status().isOk())
                .andExpect(jsonPath("$.index_version_id").value(first.lease().indexVersionId().toString()));
        mockMvc.perform(get("/api/v1/documents/{id}/contents/{version}/file", document,
                first.lease().contentVersionId()).header("Authorization", "Bearer " + token))
                .andExpect(status().isOk()).andExpect(header().string(HttpHeaders.CONTENT_DISPOSITION,
                        org.hamcrest.Matchers.containsString("first.txt")));
        publishQueued(updateContent(token, document, "third.txt", "Third evidence."), "Third evidence.", "third-publish");
        mockMvc.perform(get("/api/v1/sources/{id}", sourceId)
                .header("Authorization", "Bearer " + token)).andExpect(status().isNotFound());
        mockMvc.perform(get("/api/v1/documents/{id}/contents/{version}/file", document,
                first.lease().contentVersionId()).header("Authorization", "Bearer " + token))
                .andExpect(status().isNotFound());
        JsonNode expiredHistory = objectMapper.readTree(mockMvc.perform(
                get("/api/v1/questions/{id}", questionId)
                .header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.sources[0].state").value("VERSION_EXPIRED"))
                .andReturn().getResponse().getContentAsByteArray());
        assertThat(expiredHistory.path("sources").get(0).has("locator")).isTrue();
        assertThat(expiredHistory.path("sources").get(0).get("locator").isNull()).isTrue();
        assertThat(expiredHistory.path("sources").get(0).has("quote")).isTrue();
        assertThat(expiredHistory.path("sources").get(0).get("quote").isNull()).isTrue();
        String otherToken = register("history-other@example.test").path("access_token").asText();
        mockMvc.perform(get("/api/v1/questions/{id}", questionId)
                .header("Authorization", "Bearer " + otherToken)).andExpect(status().isNotFound());
        mockMvc.perform(delete("/api/v1/questions/{id}", questionId)
                .header("Authorization", "Bearer " + token)).andExpect(status().isNoContent());
        mockMvc.perform(get("/api/v1/questions/{id}", questionId)
                .header("Authorization", "Bearer " + token)).andExpect(status().isNotFound());
        assertThat(jdbc.queryForObject("SELECT count(*) FROM knowflow.question_sources WHERE question_id = ?",
                Integer.class, questionId)).isZero();
        assertThat(jdbc.queryForObject("SELECT count(*) FROM knowflow.chunks WHERE index_version_id = ?",
                Integer.class, first.lease().indexVersionId())).isZero();
        assertThat(jdbc.queryForObject("SELECT cleaned_at IS NULL FROM knowflow.index_versions WHERE id = ?",
                Boolean.class, second.lease().indexVersionId())).isTrue();
    }

    @Test
    void processingQuestionHistoryIncludesNullableFieldsAsJsonNull() throws Exception {
        JsonNode owner = register("processing-history@example.test");
        UUID userId = UUID.fromString(owner.path("user_id").asText());
        UUID knowledgeBaseId = UUID.fromString(createKnowledgeBase(
                owner.path("access_token").asText(), "Processing history"));
        UUID questionId = UUID.randomUUID();
        jdbc.update("""
                INSERT INTO knowflow.questions
                    (id, owner_user_id, knowledge_base_id, request_id, snapshot_id,
                     question_text, status, deadline_at)
                VALUES (?, ?, ?, ?, ?, ?, 'PROCESSING', CURRENT_TIMESTAMP + INTERVAL '30 seconds')
                """, questionId, userId, knowledgeBaseId,
                "processing-history-" + questionId, UUID.randomUUID(), "Pending question");

        String token = owner.path("access_token").asText();
        JsonNode list = objectMapper.readTree(mockMvc.perform(
                get("/api/v1/questions").header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsByteArray());
        JsonNode item = list.path("items").get(0);
        assertThat(item.path("question_id").asText()).isEqualTo(questionId.toString());
        assertJsonNull(item, "finished_at");

        JsonNode detail = objectMapper.readTree(mockMvc.perform(
                get("/api/v1/questions/{id}", questionId)
                        .header("Authorization", "Bearer " + token))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsByteArray());
        for (String field : List.of("finished_at", "answer", "has_answer", "failure_code",
                "embedding_model_profile_id", "llm_model_profile_id")) {
            assertJsonNull(detail, field);
        }
        assertThat(detail.path("sources").isEmpty()).isTrue();
    }

    private static void assertJsonNull(JsonNode object, String field) {
        assertThat(object.has(field)).isTrue();
        assertThat(object.get(field).isNull()).isTrue();
    }

    @Test
    void failedUpdatePreservesOldAnswersAndRebuildRetriesReuseTheOriginalTask() throws Exception {
        String token = register("update-failure@example.test").path("access_token").asText();
        String other = register("update-other@example.test").path("access_token").asText();
        String kb = createKnowledgeBase(token, "Failed update");
        PublishedIndex first = publishDocument(token, kb, "first.txt", "Old evidence.", "old-publish");
        UUID document = first.lease().documentId();
        JsonNode pending = updateContent(token, document, "bad.txt", "Bad evidence.");
        ClaimedIndexTask failed = indexingTasks.claimNext().orElseThrow();
        assertThat(failed.lease().taskId().toString()).isEqualTo(pending.path("task_id").asText());
        CompletionRequest failure = new CompletionRequest(ApiError.CONTRACT_VERSION, "update-failure",
                failed.lease(), "FAILED", null,
                new CompletionRequest.Failure("EMPTY_CONTENT", "No evidence", false));
        mockMvc.perform(post("/internal/v1/tasks/{id}/completion", failed.lease().taskId())
                .header("Authorization", "Bearer " + AI_SECRET).header("X-Request-ID", "update-failure")
                .contentType(MediaType.APPLICATION_JSON).content(objectMapper.writeValueAsBytes(failure)))
                .andExpect(status().isOk());
        assertThat(jdbc.queryForObject("SELECT pending_content_version_id FROM knowflow.documents WHERE id = ?",
                UUID.class, document)).isNull();
        assertThat(jdbc.queryForObject("SELECT active_index_version_id FROM knowflow.documents WHERE id = ?",
                UUID.class, document)).isEqualTo(first.lease().indexVersionId());
        AI_RESPONSE.set(request -> {
            assertThat(request.scope().indexes().getFirst().indexVersionId())
                    .isEqualTo(first.lease().indexVersionId());
            return new AiAnswerResponse(ApiError.CONTRACT_VERSION, request.requestId(), "No answer", false, List.of());
        });
        var asking = mockMvc.perform(post("/api/v1/knowledge-bases/{id}/questions", kb)
                .header("Authorization", "Bearer " + token).contentType(MediaType.APPLICATION_JSON)
                .content("{\"question\":\"Is the old index usable?\"}")).andReturn();
        mockMvc.perform(asyncDispatch(asking)).andExpect(status().isOk());
        JsonNode rebuild = rebuild(token, document);
        ClaimedIndexTask running = indexingTasks.claimNext().orElseThrow();
        assertThat(rebuild(token, document).path("task_id").asText()).isEqualTo(rebuild.path("task_id").asText());
        assertThat(running.lease().contentVersionId()).isEqualTo(first.lease().contentVersionId());
        mockMvc.perform(post("/api/v1/documents/{id}/rebuilds", document)
                .header("Authorization", "Bearer " + other)).andExpect(status().isNotFound());
        mockMvc.perform(multipart("/api/v1/documents/{id}/contents", document)
                .file(new MockMultipartFile("file", "other.txt", "text/plain", "Other".getBytes(StandardCharsets.UTF_8)))
                .header("Authorization", "Bearer " + other)).andExpect(status().isNotFound());
    }

    @Test
    void acceptedQuestionCompletesFromRetiredSnapshotEvenAfterTwoMorePublications() throws Exception {
        String token = register("snapshot-update@example.test").path("access_token").asText();
        String kb = createKnowledgeBase(token, "Snapshot");
        PublishedIndex first = publishDocument(token, kb, "first.txt", "First evidence.", "snapshot-first");
        UUID document = first.lease().documentId();
        CountDownLatch gate = new CountDownLatch(1);
        AI_RESPONSE_GATE.set(gate);
        AI_RESPONSE.set(request -> new AiAnswerResponse(ApiError.CONTRACT_VERSION, request.requestId(),
                "Answer [s1]", true, List.of(new AiAnswerResponse.AiSource("s1", document,
                first.lease().contentVersionId(), first.lease().indexVersionId(), first.chunkId(),
                new AiAnswerResponse.Locator("text_range", null, 0, 15, "unicode_code_point"),
                "First evidence."))));
        var asking = mockMvc.perform(post("/api/v1/knowledge-bases/{id}/questions", kb)
                .header("Authorization", "Bearer " + token).contentType(MediaType.APPLICATION_JSON)
                .content("{\"question\":\"Use the accepted snapshot\"}")).andReturn();
        try {
            assertThat(AI_REQUEST_RECEIVED.get().await(5, TimeUnit.SECONDS)).isTrue();
            publishQueued(updateContent(token, document, "second.txt", "Second evidence."),
                    "Second evidence.", "snapshot-second");
            publishQueued(updateContent(token, document, "third.txt", "Third evidence."),
                    "Third evidence.", "snapshot-third");
            assertThat(jdbc.queryForObject("SELECT cleaned_at IS NULL FROM knowflow.index_versions WHERE id = ?",
                    Boolean.class, first.lease().indexVersionId())).isTrue();
        } finally {
            gate.countDown();
        }
        mockMvc.perform(asyncDispatch(asking)).andExpect(status().isOk());
        new VersionRetentionService(jdbc, transactions, indexingProperties).cleanDocument(document);
        assertThat(jdbc.queryForObject("SELECT cleaned_at IS NOT NULL FROM knowflow.index_versions WHERE id = ?",
                Boolean.class, first.lease().indexVersionId())).isTrue();
    }

    private JsonNode updateContent(String token, UUID document, String name, String text) throws Exception {
        return objectMapper.readTree(mockMvc.perform(multipart("/api/v1/documents/{id}/contents", document)
                .file(new MockMultipartFile("file", name, "text/plain", text.getBytes(StandardCharsets.UTF_8)))
                .header("Authorization", "Bearer " + token)).andExpect(status().isAccepted())
                .andReturn().getResponse().getContentAsByteArray());
    }

    private JsonNode rebuild(String token, UUID document) throws Exception {
        return objectMapper.readTree(mockMvc.perform(post("/api/v1/documents/{id}/rebuilds", document)
                .header("Authorization", "Bearer " + token)).andExpect(status().isAccepted())
                .andReturn().getResponse().getContentAsByteArray());
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
        return publishQueued(uploaded, text, requestId);
    }

    private PublishedIndex publishQueued(JsonNode uploaded, String text, String requestId) throws Exception {
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

    private void assertSseContractFrames(String body) throws Exception {
        int sequence = 1;
        for (String frame : body.split("\\r?\\n\\r?\\n")) {
            if (frame.isBlank()) {
                continue;
            }
            String name = frame.lines().filter(line -> line.startsWith("event:"))
                    .map(line -> line.substring("event:".length()).trim())
                    .findFirst().orElseThrow();
            String data = frame.lines().filter(line -> line.startsWith("data:"))
                    .map(line -> line.substring("data:".length()).trim())
                    .findFirst().orElseThrow();
            JsonNode event = objectMapper.readTree(data);
            assertThat(event.path("event").asText()).isEqualTo(name);
            assertThat(event.path("contract_version").asText()).isEqualTo("0.2.0");
            assertThat(event.path("sequence").asInt()).isEqualTo(sequence++);
            switch (name) {
                case "started" -> {
                    if (event.has("model_profile")) {
                        assertJsonKeys(event, "contract_version", "request_id", "sequence", "event",
                                "model_profile");
                        assertJsonKeys(event.path("model_profile"), "embedding_model_profile_id",
                                "llm_model_profile_id");
                    } else {
                        assertJsonKeys(event, "contract_version", "request_id", "sequence", "event");
                    }
                }
                case "delta" -> assertJsonKeys(event, "contract_version", "request_id", "sequence",
                        "event", "delta");
                case "sources" -> {
                    assertJsonKeys(event, "contract_version", "request_id", "sequence", "event",
                            "has_answer", "sources");
                    for (JsonNode source : event.path("sources")) {
                        assertJsonKeys(source, "source_id", "document_id", "content_version_id",
                                "index_version_id", "chunk_id", "locator", "quote");
                        JsonNode locator = source.path("locator");
                        if ("pdf_page".equals(locator.path("kind").asText())) {
                            assertJsonKeys(locator, "kind", "page");
                        } else {
                            assertJsonKeys(locator, "kind", "start", "end", "unit");
                        }
                    }
                }
                case "completed", "cancelled" -> assertJsonKeys(event, "contract_version",
                        "request_id", "sequence", "event");
                case "error" -> assertJsonKeys(event, "contract_version", "request_id", "sequence",
                        "event", "code", "message", "retryable");
                default -> throw new AssertionError("Unexpected SSE event: " + name);
            }
        }
    }

    private static void assertJsonKeys(JsonNode node, String... expected) {
        List<String> fields = new ArrayList<>();
        node.fieldNames().forEachRemaining(fields::add);
        assertThat(fields).containsExactlyInAnyOrder(expected);
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
        AI_REQUEST_RECEIVED.get().countDown();
        try {
            TrustedAnswerRequest request = AI_MAPPER.readValue(exchange.getRequestBody(),
                    TrustedAnswerRequest.class);
            if (!requestId.equals(request.requestId())) {
                respond(exchange, 400, "{}");
                return;
            }
            AI_RESPONSE_GATE.get().await();
            if (AI_HTTP_STATUS.get() != 200) {
                respond(exchange, AI_HTTP_STATUS.get(), "{\"message\":\"UPSTREAM_PRIVATE_MARKER\"}");
                return;
            }
            AiAnswerResponse answer = AI_RESPONSE.get().apply(request);
            if (exchange.getRequestURI().getPath().endsWith("/stream")) {
                respondStream(exchange, answer);
            } else {
                respond(exchange, 200, AI_MAPPER.writeValueAsString(answer));
            }
        } catch (Exception failure) {
            AI_HANDLER_FAILURE.set(failure.getClass().getSimpleName() + ": "
                    + failure.getMessage());
            respond(exchange, 500, "{}");
        }
    }

    private static void respondStream(HttpExchange exchange, AiAnswerResponse answer)
            throws java.io.IOException {
        var started = AI_MAPPER.createObjectNode();
        started.put("contract_version", answer.contractVersion());
        started.put("request_id", answer.requestId());
        started.put("sequence", 1);
        started.put("event", "started");
        if (answer.modelProfile() != null) {
            started.set("model_profile", AI_MAPPER.valueToTree(answer.modelProfile()));
        }
        var delta = AI_MAPPER.createObjectNode();
        delta.put("contract_version", answer.contractVersion());
        delta.put("request_id", answer.requestId());
        delta.put("sequence", 2);
        delta.put("event", "delta");
        delta.put("delta", answer.answer());
        var sources = AI_MAPPER.createObjectNode();
        sources.put("contract_version", answer.contractVersion());
        sources.put("request_id", answer.requestId());
        sources.put("sequence", 3);
        sources.put("event", "sources");
        sources.put("has_answer", answer.hasAnswer());
        sources.set("sources", AI_MAPPER.valueToTree(answer.sources()));
        String body = "event: started\ndata: " + started + "\n\n"
                + "event: delta\ndata: " + delta + "\n\n"
                + "event: sources\ndata: " + sources + "\n\n";
        exchange.getResponseHeaders().set(HttpHeaders.CONTENT_TYPE, MediaType.TEXT_EVENT_STREAM_VALUE);
        exchange.sendResponseHeaders(200, 0);
        try (var output = exchange.getResponseBody()) {
            output.write(body.getBytes(StandardCharsets.UTF_8));
            output.flush();
            AI_STREAM_SOURCES_SENT.get().countDown();
            try {
                if (!AI_STREAM_TERMINAL_GATE.get().await(15, TimeUnit.SECONDS)) {
                    throw new java.io.IOException("Test stream terminal gate timed out");
                }
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                return;
            }
            String terminalEvent = AI_STREAM_TERMINAL_EVENT.get();
            if (!"truncated".equals(terminalEvent)) {
                var terminal = AI_MAPPER.createObjectNode();
                terminal.put("contract_version", answer.contractVersion());
                terminal.put("request_id", answer.requestId());
                terminal.put("sequence", 4);
                terminal.put("event", terminalEvent);
                if ("error".equals(terminalEvent)) {
                    terminal.put("code", "AI_PROCESSING_FAILED");
                    terminal.put("message", "Stream failed after sources");
                    terminal.put("retryable", true);
                } else if (!"completed".equals(terminalEvent)
                        && !"cancelled".equals(terminalEvent)) {
                    throw new java.io.IOException("Unknown test stream terminal event");
                }
                output.write(("event: " + terminalEvent + "\ndata: " + terminal + "\n\n")
                        .getBytes(StandardCharsets.UTF_8));
                output.flush();
            }
        } catch (java.io.IOException disconnected) {
            // The SSE disconnect regression deliberately closes this response before its terminal event.
        } finally {
            exchange.close();
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

    private org.springframework.test.web.servlet.MvcResult dispatchAsync(
            org.springframework.test.web.servlet.MvcResult result) throws Exception {
        assertThat(result.getRequest().isAsyncStarted()).isTrue();
        return mockMvc.perform(asyncDispatch(result)).andReturn();
    }

    private static AiAnswerResponse streamedAnswer(TrustedAnswerRequest request,
                                                   PublishedIndex published, String evidence) {
        TrustedAnswerRequest.IndexScope scope = request.scope().indexes().getFirst();
        return new AiAnswerResponse(ApiError.CONTRACT_VERSION, request.requestId(),
                "Streaming answer [stream-source]", true,
                List.of(new AiAnswerResponse.AiSource("stream-source", scope.documentId(),
                        scope.contentVersionId(), scope.indexVersionId(), published.chunkId(),
                        new AiAnswerResponse.Locator("text_range", null, 0,
                                evidence.codePointCount(0, evidence.length()), "unicode_code_point"), evidence)),
                new com.knowflow.api.answer.ModelProfile("synthetic-embedding",
                        "synthetic-llm"));
    }

    private void awaitSseEvent(org.springframework.test.web.servlet.MvcResult result,
                               String expected) throws Exception {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (System.nanoTime() < deadline) {
            if (result.getResponse().getContentAsString().contains(expected)) {
                return;
            }
            Thread.sleep(20);
        }
        assertThat(result.getResponse().getContentAsString()).contains(expected);
    }

    private void awaitQuestionStatus(String expected) throws InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        String current = null;
        while (System.nanoTime() < deadline) {
            current = jdbc.queryForObject("""
                    SELECT status FROM knowflow.questions ORDER BY created_at DESC LIMIT 1
                    """, String.class);
            if (expected.equals(current)) {
                return;
            }
            Thread.sleep(20);
        }
        assertThat(current).isEqualTo(expected);
    }

    private void awaitQuestionStatus(UUID questionId, String expected) throws InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(10);
        String current = null;
        while (System.nanoTime() < deadline) {
            current = jdbc.queryForObject("SELECT status FROM knowflow.questions WHERE id = ?",
                    String.class, questionId);
            if (expected.equals(current)) {
                return;
            }
            Thread.sleep(20);
        }
        assertThat(current).isEqualTo(expected);
    }

    private void awaitQuestionWritebackLockWait() throws InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(8);
        while (System.nanoTime() < deadline) {
            Integer waiting = jdbc.queryForObject("""
                    SELECT count(*) FROM pg_stat_activity
                     WHERE wait_event_type = 'Lock'
                       AND query ILIKE 'UPDATE knowflow.questions%status = ''SUCCEEDED''%'
                    """, Integer.class);
            if (waiting != null && waiting > 0) {
                return;
            }
            Thread.sleep(20);
        }
        assertThat(false).as("question final UPDATE should wait on the held question row").isTrue();
    }

    private void awaitQuestionWritebackLockWaitEnded() throws InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(8);
        while (System.nanoTime() < deadline) {
            Integer waiting = jdbc.queryForObject("""
                    SELECT count(*) FROM pg_stat_activity
                     WHERE wait_event_type = 'Lock'
                       AND query ILIKE 'UPDATE knowflow.questions%status = ''SUCCEEDED''%'
                    """, Integer.class);
            if (waiting != null && waiting == 0) {
                return;
            }
            Thread.sleep(20);
        }
        assertThat(false).as("question final UPDATE should stop waiting at its deadline").isTrue();
    }

    private static IndexBatchRequest createBatch(LeaseContext lease, String requestId,
                                                  UUID batchId, String text) {
        return createBatch(lease, requestId, batchId, List.of(text));
    }

    private static IndexBatchRequest createBatch(LeaseContext lease, String requestId,
                                                  UUID batchId, List<String> texts) {
        List<IndexBatchRequest.Chunk> chunks = new ArrayList<>();
        int start = 0;
        for (int index = 0; index < texts.size(); index++) {
            String text = texts.get(index);
            int end = start + text.codePointCount(0, text.length());
            chunks.add(new IndexBatchRequest.Chunk(UUID.randomUUID(), index + 1, text,
                    sha256(text.getBytes(StandardCharsets.UTF_8)),
                    new IndexBatchRequest.Locator("text_range", null, start, end,
                            "unicode_code_point"),
                    java.util.Collections.nCopies(1024, BigDecimal.ZERO)));
            start = end;
        }
        IndexBatchRequest candidate = new IndexBatchRequest("0.2.0", requestId, lease,
                batchId, 1, "0".repeat(64), chunks);
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
                                {"contract_version":"0.2.0","email":"%s",
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
                                {"contract_version":"0.2.0","name":"%s"}
                                """.formatted(name)))
                .andExpect(status().isCreated())
                .andReturn().getResponse().getContentAsByteArray());
        return created.path("id").asText();
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class StorageConcurrencyTestConfiguration {
        @Bean
        @Primary
        BlockingObjectStore blockingObjectStore(S3ObjectStore delegate) {
            return new BlockingObjectStore(delegate);
        }
    }

    static final class BlockingObjectStore implements ObjectStore {
        private final S3ObjectStore delegate;
        private final AtomicReference<ReadGate> nextRead = new AtomicReference<>();

        BlockingObjectStore(S3ObjectStore delegate) {
            this.delegate = delegate;
        }

        ReadGate blockNextRead() {
            ReadGate gate = new ReadGate();
            if (!nextRead.compareAndSet(null, gate)) {
                throw new IllegalStateException("A blocking storage read is already configured");
            }
            return gate;
        }

        @Override
        public void ensureBucket() {
            delegate.ensureBucket();
        }

        @Override
        public void putObject(String key, String contentType, byte[] contents) {
            delegate.putObject(key, contentType, contents);
        }

        @Override
        public byte[] getObject(String key, int maximumBytes) {
            ReadGate gate = nextRead.getAndSet(null);
            if (gate != null) {
                gate.started().countDown();
                try {
                    if (!gate.release().await(20, TimeUnit.SECONDS)) {
                        throw new ObjectStoreException("Test storage read was not released");
                    }
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw new ObjectStoreException("Test storage read was interrupted", interrupted);
                }
            }
            return delegate.getObject(key, maximumBytes);
        }

        @Override
        public void deleteObject(String key) {
            delegate.deleteObject(key);
        }

        static final class ReadGate {
            private final CountDownLatch started = new CountDownLatch(1);
            private final CountDownLatch release = new CountDownLatch(1);

            CountDownLatch started() { return started; }
            CountDownLatch release() { return release; }
        }
    }

    private record PublishedIndex(LeaseContext lease, UUID chunkId) {}
}
