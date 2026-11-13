package com.knowflow.api.db;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Statement;
import java.sql.Types;

import com.knowflow.api.config.ApplicationDatabaseConfiguration;
import com.knowflow.api.config.ApplicationDatabaseProperties;
import com.knowflow.api.config.DatabaseMigrationConfiguration;
import com.knowflow.api.config.DatabaseMigrationProperties;
import org.flywaydb.core.api.FlywayException;
import org.flywaydb.core.api.MigrationVersion;
import org.flywaydb.core.Flyway;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import javax.sql.DataSource;

@Testcontainers
class PostgreSqlMigrationIntegrationTest {
    private static final String ADMIN_PASSWORD = "test-only-admin-password";
    private static final String MIGRATOR_PASSWORD = "test-only-migrator-password";
    private static final String APP_PASSWORD = "test-only-app-password";
    private static final String AI_PASSWORD = "test-only-ai-password";
    private static final String IMAGE = "pgvector/pgvector:0.8.1-pg16"
            + "@sha256:33198da2828a14c30348d2ccb4750833d5ed9a44c88d840a0e523d7417120337";

    @Container
    private static final PostgreSQLContainer<?> DATABASE = new PostgreSQLContainer<>(
            DockerImageName.parse(IMAGE).asCompatibleSubstituteFor("postgres"))
            .withDatabaseName("knowflow")
            .withUsername("postgres")
            .withPassword(ADMIN_PASSWORD)
            .withInitScript("db/bootstrap-roles.sql");

    private final ApplicationContextRunner migrationContext = new ApplicationContextRunner()
            .withUserConfiguration(MigrationTestConfiguration.class)
            .withPropertyValues(
                    "spring.profiles.active=db-migrate",
                    "knowflow.database.migration.url=" + DATABASE.getJdbcUrl(),
                    "knowflow.database.migration.username=knowflow_migrator",
                    "knowflow.database.migration.password=" + MIGRATOR_PASSWORD);

    @BeforeAll
    static void provisionTestOnlyRolePasswords() throws SQLException {
        try (Connection connection = DriverManager.getConnection(
                DATABASE.getJdbcUrl(), DATABASE.getUsername(), DATABASE.getPassword());
             Statement statement = connection.createStatement()) {
            statement.execute("ALTER ROLE knowflow_migrator PASSWORD '" + MIGRATOR_PASSWORD + "'");
            statement.execute("ALTER ROLE knowflow_app PASSWORD '" + APP_PASSWORD + "'");
            statement.execute("ALTER ROLE knowflow_ai PASSWORD '" + AI_PASSWORD + "'");
        }
    }

    @Test
    void migratesRealPgvectorSchemaIdempotentlyAndEnforcesRoleAndDataBoundaries() {
        Flyway v7Flyway = migrationFlyway("7");
        assertThat(v7Flyway.migrate().migrationsExecuted).isEqualTo(7);
        assertThat(v7Flyway.info().current().getVersion().getVersion()).isEqualTo("7");
        verifyQuestionSourceRetentionUpgrade();
        insertV9ModelBeforeProbeMigration();
        migrationContext.run(context -> {
            assertThat(context).hasNotFailed();
            Flyway flyway = context.getBean(Flyway.class);
            assertThat(flyway.info().current().getVersion().getVersion()).isEqualTo("11");
            assertThat(queryLong("SELECT count(*) FROM knowflow.questions WHERE selected_llm_model_id IS NULL"))
                    .isEqualTo(1L);
            assertThat(queryLong("""
                    SELECT count(*) FROM information_schema.columns
                     WHERE table_schema = 'knowflow' AND table_name = 'questions'
                       AND column_name IN ('idempotency_key', 'deadline_at',
                                           'embedding_model_profile_id', 'llm_model_profile_id')
                    """)).isEqualTo(4L);
            assertThat(queryLong("""
                    SELECT count(*) FROM pg_indexes
                     WHERE schemaname = 'knowflow' AND indexname IN (
                         'questions_owner_idempotency_key_uq',
                         'questions_processing_deadline_idx')
                    """)).isEqualTo(2L);

            var extensionVersion = queryString(
                    "SELECT extversion FROM pg_extension WHERE extname = 'vector'");
            assertThat(extensionVersion).isEqualTo("0.8.1");

            try (Connection app = connect("knowflow_app", APP_PASSWORD)) {
                verifyModelProbeMigration(app);
                assertConstraintViolation(app, """
                        INSERT INTO knowflow.content_versions
                            (id, document_id, version_no, source_sha256, source_format, object_key, byte_size, original_name)
                        VALUES (
                            '00000000-0000-0000-0000-000000000202',
                            '00000000-0000-0000-0000-000000000102', 2,
                            'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
                            'txt', 'objects/doc-102/content-201', 42, 'notes.txt')
                        """, "23505");
                assertConstraintViolation(app, """
                        INSERT INTO knowflow.users (id, email)
                        VALUES ('00000000-0000-0000-0000-000000000002', 'OWNER@example.test')
                        """, "23505");
                assertConstraintViolation(app, """
                        INSERT INTO knowflow.documents
                            (id, knowledge_base_id, owner_user_id, original_name)
                        VALUES (
                            '00000000-0000-0000-0000-000000000003',
                            '00000000-0000-0000-0000-000000000101',
                            '00000000-0000-0000-0000-000000000002',
                            'cross-owner.txt')
                        """, "23503");
                assertConstraintViolation(app, """
                        INSERT INTO knowflow.index_versions
                            (id, document_id, content_version_id, pipeline_profile_id,
                             generation, embedding_model_profile_id, embedding_dimensions)
                        VALUES (
                            '00000000-0000-0000-0000-000000000202',
                            '00000000-0000-0000-0000-000000000102',
                            '00000000-0000-0000-0000-000000000201',
                            'pipeline-v1', 2, 'BAAI/bge-m3', 768)
                        """, "23514");
                assertConstraintViolation(app, """
                        INSERT INTO knowflow.chunks
                            (id, index_version_id, document_id, content_version_id,
                             sequence_no, text_content, text_sha256, locator_kind,
                             source_start, source_end)
                        VALUES (
                            '00000000-0000-0000-0000-000000000302',
                            '00000000-0000-0000-0000-000000000301',
                            '00000000-0000-0000-0000-000000000102',
                            '00000000-0000-0000-0000-000000000201',
                            2, 'x', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                            'text_range', 5, 5)
                        """, "23514");

                execute(app, """
                        INSERT INTO knowflow.chunks
                            (id, index_version_id, document_id, content_version_id,
                             sequence_no, text_content, text_sha256, locator_kind,
                             source_start, source_end)
                        VALUES (
                            '00000000-0000-0000-0000-000000000303',
                            '00000000-0000-0000-0000-000000000301',
                            '00000000-0000-0000-0000-000000000102',
                            '00000000-0000-0000-0000-000000000201',
                            2, 'def', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                            'text_range', 3, 6)
                        """);
                insertEmbedding(app, "00000000-0000-0000-0000-000000000302", zeroVector(1024));
                assertThat(queryLong(app,
                        "SELECT count(*) FROM knowflow.chunk_embeddings")).isEqualTo(1L);

                assertThatThrownBy(() -> insertEmbedding(app,
                        "00000000-0000-0000-0000-000000000303", "[0.1, 0.2]"))
                        .isInstanceOf(SQLException.class);

                try (Connection ai = connect("knowflow_ai", AI_PASSWORD)) {
                    assertThat(queryLong(ai,
                            "SELECT count(*) FROM knowflow.knowledge_bases")).isEqualTo(1L);
                    assertPermissionDenied(ai, """
                            UPDATE knowflow.documents SET status = 'DELETED'
                            WHERE id = '00000000-0000-0000-0000-000000000102'
                            """);
                    assertPermissionDenied(ai, """
                            UPDATE knowflow.indexing_tasks SET status = 'SUCCEEDED'
                            WHERE id = '00000000-0000-0000-0000-000000000401'
                            """);
                    assertPermissionDenied(ai, """
                            INSERT INTO knowflow.chunks
                                (id, index_version_id, document_id, content_version_id,
                                 sequence_no, text_content, text_sha256, locator_kind,
                                 source_start, source_end)
                            VALUES (
                                '00000000-0000-0000-0000-000000000304',
                                '00000000-0000-0000-0000-000000000301',
                                '00000000-0000-0000-0000-000000000102',
                                '00000000-0000-0000-0000-000000000201',
                                3, 'forbidden',
                                'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                                'text_range', 6, 15)
                            """);
                    assertPermissionDenied(ai, "SELECT token_sha256 FROM knowflow.user_sessions");
                    assertPermissionDenied(ai,
                            "SELECT count(*) FROM knowflow.index_batch_receipts");
                    assertPermissionDenied(ai,
                            "SELECT count(*) FROM knowflow.storage_cleanup_queue");
                    assertPermissionDenied(ai,
                            "SELECT count(*) FROM knowflow.index_cleanup_queue");
                    assertPermissionDenied(ai,
                            "SELECT count(*) FROM knowflow.execution_cancellation_queue");
                    assertPermissionDenied(ai, "SELECT count(*) FROM knowflow.questions");
                    assertPermissionDenied(ai,
                            "SELECT count(*) FROM knowflow.question_scope_indexes");
                    assertPermissionDenied(ai, "SELECT count(*) FROM knowflow.question_sources");
                }

                assertPermissionDenied(app, "CREATE TABLE knowflow.forbidden_ddl (id INTEGER)");
            } catch (SQLException exception) {
                throw new AssertionError("Real PostgreSQL migration verification failed", exception);
            }

            var repeatedMigration = flyway.migrate();
            assertThat(repeatedMigration.migrationsExecuted).isZero();
            assertThat(queryLong("SELECT count(*) FROM knowflow.users")).isEqualTo(1L);
            verifyProfileBoundApplicationDataSource();

            DatabaseMigrationApplication.run(new String[] {
                    "--knowflow.database.migration.url=" + DATABASE.getJdbcUrl(),
                    "--knowflow.database.migration.username=knowflow_migrator",
                    "--knowflow.database.migration.password=" + MIGRATOR_PASSWORD
            });
            assertThat(queryLong("SELECT count(*) FROM knowflow.users")).isEqualTo(1L);
        });
    }

    private static void insertV9ModelBeforeProbeMigration() {
        Flyway v9 = migrationFlyway("9");
        assertThat(v9.migrate().migrationsExecuted).isEqualTo(1);
        try (Connection app = connect("knowflow_app", APP_PASSWORD)) {
            execute(app, """
                    INSERT INTO knowflow.llm_models
                        (id, owner_user_id, base_url, protocol, model_id, encrypted_key, supports_tools, revision)
                    VALUES ('00000000-0000-4000-8000-000000000901',
                            '00000000-0000-0000-0000-000000000001',
                            'https://provider.example.test', 'responses', 'legacy', decode('aabb', 'hex'), false,
                            '00000000-0000-4000-8000-000000000902')
                    """);
        } catch (SQLException invalid) { throw new AssertionError(invalid); }
    }

    private static void verifyModelProbeMigration(Connection app) throws SQLException {
        String id = "00000000-0000-4000-8000-000000000901";
        assertThat(queryLong(app, "SELECT count(*) FROM knowflow.llm_models WHERE last_probe_at IS NULL "
                + "AND last_probe_status IS NULL")).isEqualTo(1L);
        for (String fields : new String[]{"last_probe_at=now()", "last_probe_status='success'",
                "last_probe_at=now(), last_probe_status='failed'",
                "last_probe_at=now(), last_probe_status='unknown'"}) {
            assertConstraintViolation(app, "UPDATE knowflow.llm_models SET " + fields + " WHERE id='" + id + "'", "23514");
        }
        execute(app, "UPDATE knowflow.llm_models SET supports_tools=true, last_probe_at='2026-11-12T01:02:03Z', "
                + "last_probe_status='success', revision='00000000-0000-4000-8000-000000000903' WHERE id='" + id + "' "
                + "AND owner_user_id='00000000-0000-0000-0000-000000000001' "
                + "AND revision='00000000-0000-4000-8000-000000000902'");
        assertThat(queryLong(app, "SELECT count(*) FROM knowflow.llm_models WHERE supports_tools=true "
                + "AND last_probe_status='success' AND last_probe_at='2026-11-12T01:02:03Z'")).isEqualTo(1L);
        // Owner predicates and CAS leave a successful result untouched on rejection.
        execute(app, "UPDATE knowflow.llm_models SET supports_tools=false WHERE id='" + id + "' "
                + "AND owner_user_id='00000000-0000-0000-0000-000000000099'");
        execute(app, "UPDATE knowflow.llm_models SET supports_tools=false WHERE id='" + id + "' "
                + "AND revision='00000000-0000-4000-8000-000000000902'");
        assertThat(queryLong(app, "SELECT count(*) FROM knowflow.llm_models WHERE supports_tools=true")).isEqualTo(1L);
        assertConstraintViolation(app, "UPDATE knowflow.llm_models SET last_probe_at=NULL WHERE id='" + id + "'", "23514");
        assertConstraintViolation(app, "UPDATE knowflow.llm_models SET last_probe_status=NULL WHERE id='" + id + "'", "23514");
        try (Connection ai = connect("knowflow_ai", AI_PASSWORD)) {
            assertPermissionDenied(ai, "SELECT encrypted_key, last_probe_at FROM knowflow.llm_models");
            assertPermissionDenied(ai, "UPDATE knowflow.llm_models SET last_probe_at=now()");
        }
    }

    private static void verifyQuestionSourceRetentionUpgrade() {
        try (Connection app = connect("knowflow_app", APP_PASSWORD)) {
            insertValidKnowledgeGraph(app);
            insertQuestionForSourceTests(app);
            insertQuestionSource(app, "00000000-0000-0000-0000-000000000501",
                    null, null, null, null, "retained quote with missing locator");

            Flyway flyway = migrationFlyway("8");
            assertThatThrownBy(flyway::migrate).isInstanceOf(FlywayException.class);
            assertThat(flyway.info().current().getVersion().getVersion()).isEqualTo("7");
            assertThat(queryLong(app, """
                    SELECT count(*) FROM knowflow.question_sources
                     WHERE source_id = '00000000-0000-0000-0000-000000000501'
                    """)).isEqualTo(1L);

            execute(app, """
                    DELETE FROM knowflow.question_sources
                     WHERE source_id = '00000000-0000-0000-0000-000000000501'
                    """);
            assertThat(flyway.migrate().migrationsExecuted).isEqualTo(1);
            assertThat(flyway.info().current().getVersion().getVersion()).isEqualTo("8");

            insertQuestionSource(app, "00000000-0000-0000-0000-000000000502",
                    "pdf_page", 1, null, null, "PDF quote");
            insertQuestionSource(app, "00000000-0000-0000-0000-000000000503",
                    "text_range", null, 0, 3, "abc");
            insertQuestionSource(app, "00000000-0000-0000-0000-000000000504",
                    null, null, null, null, null);

            assertQuestionSourceShapeRejected(app, "00000000-0000-0000-0000-000000000505",
                    null, null, null, null, "quote without locator kind");
            assertQuestionSourceShapeRejected(app, "00000000-0000-0000-0000-000000000506",
                    "pdf_page", null, null, null, "PDF quote without page");
            assertQuestionSourceShapeRejected(app, "00000000-0000-0000-0000-000000000507",
                    "text_range", null, null, 3, "range without start");
            assertQuestionSourceShapeRejected(app, "00000000-0000-0000-0000-000000000508",
                    "text_range", null, 0, null, "range without end");
        } catch (SQLException exception) {
            throw new AssertionError("Question source retention migration verification failed", exception);
        }
    }

    private static void verifyProfileBoundApplicationDataSource() {
        new ApplicationContextRunner()
                .withUserConfiguration(ApplicationDataSourceTestConfiguration.class)
                .withPropertyValues(
                        "spring.profiles.active=database",
                        "knowflow.database.application.url=" + DATABASE.getJdbcUrl(),
                        "knowflow.database.application.username=knowflow_app",
                        "knowflow.database.application.password=" + APP_PASSWORD)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    try (Connection connection = context.getBean(DataSource.class).getConnection()) {
                        assertThat(queryString(connection, "SELECT session_user"))
                                .isEqualTo("knowflow_app");
                        assertThat(queryLong(connection,
                                "SELECT count(*) FROM knowflow.knowledge_bases")).isEqualTo(1L);
                        assertPermissionDenied(connection,
                                "CREATE TABLE knowflow.application_must_not_own_schema (id INTEGER)");
                    } catch (SQLException exception) {
                        throw new AssertionError("Application datasource verification failed", exception);
                    }
                });
    }

    private static void insertValidKnowledgeGraph(Connection app) throws SQLException {
        execute(app, """
                INSERT INTO knowflow.users (id, email)
                VALUES ('00000000-0000-0000-0000-000000000001', 'owner@example.test')
                """);
        execute(app, """
                INSERT INTO knowflow.knowledge_bases (id, owner_user_id, name)
                VALUES ('00000000-0000-0000-0000-000000000101',
                        '00000000-0000-0000-0000-000000000001', 'Research')
                """);
        execute(app, """
                INSERT INTO knowflow.documents
                    (id, knowledge_base_id, owner_user_id, original_name)
                VALUES ('00000000-0000-0000-0000-000000000102',
                        '00000000-0000-0000-0000-000000000101',
                        '00000000-0000-0000-0000-000000000001', 'notes.txt')
                """);
        execute(app, """
                INSERT INTO knowflow.content_versions
                    (id, document_id, version_no, source_sha256, source_format, object_key, byte_size, original_name)
                VALUES ('00000000-0000-0000-0000-000000000201',
                        '00000000-0000-0000-0000-000000000102', 1,
                        'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                        'txt', 'objects/doc-102/content-201', 42, 'notes.txt')
                """);
        execute(app, """
                UPDATE knowflow.documents
                   SET current_content_version_id = '00000000-0000-0000-0000-000000000201'
                 WHERE id = '00000000-0000-0000-0000-000000000102'
                """);
        execute(app, """
                INSERT INTO knowflow.index_versions
                    (id, document_id, content_version_id, pipeline_profile_id,
                     generation, embedding_model_profile_id)
                VALUES ('00000000-0000-0000-0000-000000000301',
                        '00000000-0000-0000-0000-000000000102',
                        '00000000-0000-0000-0000-000000000201',
                        'pipeline-v1', 1, 'BAAI/bge-m3')
                """);
        execute(app, """
                INSERT INTO knowflow.indexing_tasks
                    (id, owner_user_id, knowledge_base_id, document_id,
                     content_version_id, index_version_id)
                VALUES ('00000000-0000-0000-0000-000000000401',
                        '00000000-0000-0000-0000-000000000001',
                        '00000000-0000-0000-0000-000000000101',
                        '00000000-0000-0000-0000-000000000102',
                        '00000000-0000-0000-0000-000000000201',
                        '00000000-0000-0000-0000-000000000301')
                """);
        execute(app, """
                INSERT INTO knowflow.chunks
                    (id, index_version_id, document_id, content_version_id,
                     sequence_no, text_content, text_sha256, locator_kind, source_start, source_end)
                VALUES ('00000000-0000-0000-0000-000000000302',
                        '00000000-0000-0000-0000-000000000301',
                        '00000000-0000-0000-0000-000000000102',
                        '00000000-0000-0000-0000-000000000201', 1, 'abc',
                        'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                        'text_range', 0, 3)
                """);
    }

    private static void insertQuestionForSourceTests(Connection app) throws SQLException {
        execute(app, """
                INSERT INTO knowflow.questions
                    (id, owner_user_id, knowledge_base_id, request_id, snapshot_id,
                     question_text, deadline_at)
                VALUES ('00000000-0000-0000-0000-000000000401',
                        '00000000-0000-0000-0000-000000000001',
                        '00000000-0000-0000-0000-000000000101',
                        'migration-source-shape',
                        '00000000-0000-0000-0000-000000000402',
                        'Question source shape', CURRENT_TIMESTAMP + INTERVAL '30 seconds')
                """);
    }

    private static void insertQuestionSource(Connection app, String sourceId, String locatorKind,
                                             Integer sourcePage, Integer sourceStart,
                                             Integer sourceEnd, String quote) throws SQLException {
        try (PreparedStatement statement = app.prepareStatement("""
                INSERT INTO knowflow.question_sources
                    (source_id, question_id, owner_user_id, knowledge_base_id, document_id,
                     content_version_id, index_version_id, chunk_id, locator_kind, source_page,
                     source_start, source_end, quote)
                VALUES (?, '00000000-0000-0000-0000-000000000401',
                        '00000000-0000-0000-0000-000000000001',
                        '00000000-0000-0000-0000-000000000101',
                        '00000000-0000-0000-0000-000000000102',
                        '00000000-0000-0000-0000-000000000201',
                        '00000000-0000-0000-0000-000000000301',
                        '00000000-0000-0000-0000-000000000302', ?, ?, ?, ?, ?)
                """)) {
            statement.setObject(1, java.util.UUID.fromString(sourceId));
            statement.setObject(2, locatorKind, Types.VARCHAR);
            statement.setObject(3, sourcePage, Types.INTEGER);
            statement.setObject(4, sourceStart, Types.INTEGER);
            statement.setObject(5, sourceEnd, Types.INTEGER);
            statement.setString(6, quote);
            statement.execute();
        }
    }

    private static void assertQuestionSourceShapeRejected(Connection app, String sourceId,
                                                          String locatorKind, Integer sourcePage,
                                                          Integer sourceStart, Integer sourceEnd,
                                                          String quote) {
        assertThatThrownBy(() -> insertQuestionSource(app, sourceId, locatorKind, sourcePage,
                sourceStart, sourceEnd, quote))
                .isInstanceOf(SQLException.class)
                .extracting(exception -> ((SQLException) exception).getSQLState())
                .isEqualTo("23514");
    }

    private static Flyway migrationFlyway(String targetVersion) {
        var configuration = Flyway.configure()
                .dataSource(DATABASE.getJdbcUrl(), "knowflow_migrator", MIGRATOR_PASSWORD)
                .defaultSchema("knowflow_flyway")
                .schemas("knowflow_flyway", "knowflow")
                .createSchemas(false)
                .cleanDisabled(true)
                .locations("classpath:db/migration");
        if (targetVersion != null) {
            configuration.target(MigrationVersion.fromVersion(targetVersion));
        }
        return configuration.load();
    }

    private static String zeroVector(int dimensions) {
        return "[" + "0,".repeat(dimensions - 1) + "0]";
    }

    private static void insertEmbedding(Connection connection, String chunkId, String vector)
            throws SQLException {
        try (var statement = connection.prepareStatement("""
                INSERT INTO knowflow.chunk_embeddings
                    (chunk_id, index_version_id, document_id, content_version_id,
                     embedding_model_profile_id, embedding)
                VALUES (?, '00000000-0000-0000-0000-000000000301',
                        '00000000-0000-0000-0000-000000000102',
                        '00000000-0000-0000-0000-000000000201',
                        'BAAI/bge-m3', ?::public.vector(1024))
                """)) {
            statement.setObject(1, java.util.UUID.fromString(chunkId));
            statement.setString(2, vector);
            statement.execute();
        }
    }

    private static void assertConstraintViolation(Connection connection, String sql, String state) {
        assertThatThrownBy(() -> execute(connection, sql))
                .isInstanceOf(SQLException.class)
                .extracting(exception -> ((SQLException) exception).getSQLState())
                .isEqualTo(state);
    }

    private static void assertPermissionDenied(Connection connection, String sql) {
        assertConstraintViolation(connection, sql, "42501");
    }

    private static void execute(Connection connection, String sql) throws SQLException {
        try (Statement statement = connection.createStatement()) {
            statement.execute(sql);
        }
    }

    private static long queryLong(Connection connection, String sql) {
        try (Statement statement = connection.createStatement();
             var result = statement.executeQuery(sql)) {
            result.next();
            return result.getLong(1);
        } catch (SQLException exception) {
            throw new AssertionError("Database query failed", exception);
        }
    }

    private static long queryLong(String sql) {
        try (Connection connection = connect("knowflow_app", APP_PASSWORD)) {
            return queryLong(connection, sql);
        } catch (SQLException exception) {
            throw new AssertionError("Database query failed", exception);
        }
    }

    private static String queryString(String sql) {
        try (Connection connection = DriverManager.getConnection(
                DATABASE.getJdbcUrl(), DATABASE.getUsername(), DATABASE.getPassword());
             Statement statement = connection.createStatement();
             var result = statement.executeQuery(sql)) {
            result.next();
            return result.getString(1);
        } catch (SQLException exception) {
            throw new AssertionError("Database query failed", exception);
        }
    }

    private static String queryString(Connection connection, String sql) {
        try (Statement statement = connection.createStatement();
             var result = statement.executeQuery(sql)) {
            result.next();
            return result.getString(1);
        } catch (SQLException exception) {
            throw new AssertionError("Database query failed", exception);
        }
    }

    private static Connection connect(String username, String password) throws SQLException {
        return DriverManager.getConnection(DATABASE.getJdbcUrl(), username, password);
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(DatabaseMigrationProperties.class)
    @Import(DatabaseMigrationConfiguration.class)
    static class MigrationTestConfiguration {
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(ApplicationDatabaseProperties.class)
    @Import(ApplicationDatabaseConfiguration.class)
    static class ApplicationDataSourceTestConfiguration {
    }
}
