package com.knowflow.api.answer;

import java.nio.charset.StandardCharsets;
import java.sql.SQLException;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.CancellationException;
import java.util.concurrent.TimeUnit;
import java.util.UUID;
import java.util.concurrent.TimeoutException;
import java.util.regex.Pattern;

import com.knowflow.api.error.ApiError;
import com.knowflow.api.error.ApiFailure;
import com.knowflow.api.config.QuestionProperties;
import com.knowflow.api.security.AuthenticatedUser;
import org.springframework.context.annotation.Profile;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.TransactionException;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

@Service
@Profile("database")
public class QuestionService {
    private static final int MAX_SCOPE_DOCUMENTS = 100;
    private static final int CLEANUP_TIMEOUT_MILLIS = 2_000;
    private static final Pattern IDENTIFIER = Pattern.compile("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}");

    private final JdbcTemplate jdbc;
    private final TransactionTemplate transactions;
    private final AiAnswerClient client;
    private final QuestionProperties properties;

    public QuestionService(JdbcTemplate jdbc, TransactionTemplate transactions,
                           AiAnswerClient client, QuestionProperties properties) {
        this.jdbc = jdbc;
        this.transactions = transactions;
        this.client = client;
        this.properties = properties;
    }

    public AnswerResponse ask(AuthenticatedUser user, UUID knowledgeBaseId, PublicQuestion input) {
        return ask(user, knowledgeBaseId, input, System.nanoTime(), new QuestionCancellation());
    }

    AnswerResponse ask(AuthenticatedUser user, UUID knowledgeBaseId, PublicQuestion input,
                       long requestStartedAt, QuestionCancellation cancellation) {
        String question = validateQuestion(input);
        String requestId = UUID.randomUUID().toString();
        QuestionSnapshot snapshot;
        try {
            snapshot = createSnapshot(user, knowledgeBaseId, question, requestId,
                    requestStartedAt, cancellation);
        } catch (RuntimeException failure) {
            if (cancellation.reason() == QuestionCancellation.Reason.TIMEOUT
                    || isTimeout(failure)) {
                throw ApiFailure.processingTimeout();
            }
            if (cancellation.reason() == QuestionCancellation.Reason.CLIENT_DISCONNECTED) {
                throw new CancellationException("Question request was cancelled");
            }
            throw failure;
        }
        if (cancellation.reason() != null) {
            return cancelQuestion(snapshot.questionId(), cancellation);
        }
        try {
            remainingBudget(requestStartedAt);
        } catch (RuntimeException expired) {
            markFailed(snapshot.questionId(), "PROCESSING_TIMEOUT");
            throw ApiFailure.processingTimeout();
        }
        TrustedAnswerRequest request = new TrustedAnswerRequest(ApiError.CONTRACT_VERSION,
                requestId, question, new TrustedAnswerRequest.TrustedScope(user.id(),
                knowledgeBaseId, snapshot.snapshotId(), snapshot.indexes().stream()
                .map(index -> new TrustedAnswerRequest.IndexScope(index.documentId(),
                        index.contentVersionId(), index.indexVersionId())).toList()));

        AiAnswerResponse response;
        try {
            if (cancellation.reason() != null) {
                throw new CancellationException("Question request was cancelled");
            }
            response = client.answer(request, remainingBudget(requestStartedAt));
            validateAnswer(response);
            if (cancellation.reason() != null) {
                throw new CancellationException("Question request was cancelled");
            }
            remainingBudget(requestStartedAt);
        } catch (CancellationException cancelled) {
            return cancelQuestion(snapshot.questionId(), cancellation);
        } catch (RuntimeException failure) {
            if (cancellation.reason() != null) {
                return cancelQuestion(snapshot.questionId(), cancellation);
            }
            boolean timeout = isTimeout(failure);
            markFailed(snapshot.questionId(), timeout ? "PROCESSING_TIMEOUT" : "AI_PROCESSING_FAILED");
            throw timeout ? ApiFailure.processingTimeout() : ApiFailure.aiProcessingFailed();
        }

        try {
            AnswerResponse saved = transactions.execute(status -> {
                registerDeadlineCheck(requestStartedAt, cancellation);
                return saveAnswer(user, snapshot, requestId, response, cancellation,
                        requestStartedAt);
            });
            if (saved == null) {
                throw new IllegalStateException("Question persistence did not return a response");
            }
            return saved;
        } catch (CancellationException cancelled) {
            return cancelQuestion(snapshot.questionId(), cancellation);
        } catch (ApiFailure failure) {
            if (cancellation.reason() != null) {
                return cancelQuestion(snapshot.questionId(), cancellation);
            }
            markFailed(snapshot.questionId(), "DOCUMENT_UNAVAILABLE".equals(failure.code())
                    ? "DOCUMENT_UNAVAILABLE" : "AI_PROCESSING_FAILED");
            throw failure;
        } catch (DataAccessException storageFailure) {
            if (cancellation.reason() != null) {
                return cancelQuestion(snapshot.questionId(), cancellation);
            }
            boolean timeout = isTimeout(storageFailure);
            markFailed(snapshot.questionId(), timeout ? "PROCESSING_TIMEOUT" : "AI_PROCESSING_FAILED");
            if (timeout) {
                throw ApiFailure.processingTimeout();
            }
            throw storageFailure;
        } catch (RuntimeException failure) {
            if (cancellation.reason() != null) {
                return cancelQuestion(snapshot.questionId(), cancellation);
            }
            boolean timeout = isTimeout(failure);
            markFailed(snapshot.questionId(), timeout ? "PROCESSING_TIMEOUT" : "AI_PROCESSING_FAILED");
            if (timeout) {
                throw ApiFailure.processingTimeout();
            }
            throw failure;
        }
    }

    private QuestionSnapshot createSnapshot(AuthenticatedUser user, UUID knowledgeBaseId,
                                            String question, String requestId,
                                            long requestStartedAt,
                                            QuestionCancellation cancellation) {
        QuestionSnapshot snapshot = transactions.execute(status -> {
            registerDeadlineCheck(requestStartedAt, cancellation);
            setStatementTimeout(requestStartedAt, cancellation);
            Integer ownerCount = jdbc.queryForObject("""
                    SELECT count(*) FROM knowflow.knowledge_bases
                     WHERE id = ? AND owner_user_id = ? AND status = 'ACTIVE'
                    """, Integer.class, knowledgeBaseId, user.id());
            if (ownerCount == null || ownerCount != 1) {
                throw ApiFailure.resourceNotFound();
            }
            setStatementTimeout(requestStartedAt, cancellation);
            List<IndexRef> indexes = jdbc.query("""
                    SELECT d.id AS document_id, d.current_content_version_id,
                           d.active_index_version_id
                      FROM knowflow.documents d
                      JOIN knowflow.index_versions iv
                        ON iv.id = d.active_index_version_id
                       AND iv.document_id = d.id
                       AND iv.content_version_id = d.current_content_version_id
                     WHERE d.knowledge_base_id = ? AND d.owner_user_id = ?
                       AND d.status = 'ACTIVE' AND iv.status = 'READY'
                     ORDER BY d.id
                     LIMIT ?
                    """, (result, row) -> new IndexRef(
                    result.getObject("document_id", UUID.class),
                    result.getObject("current_content_version_id", UUID.class),
                    result.getObject("active_index_version_id", UUID.class)),
                    knowledgeBaseId, user.id(), MAX_SCOPE_DOCUMENTS + 1);
            if (indexes.isEmpty()) {
                throw ApiFailure.knowledgeBaseNotReady();
            }
            if (indexes.size() > MAX_SCOPE_DOCUMENTS) {
                throw ApiFailure.scopeLimit();
            }
            UUID questionId = UUID.randomUUID();
            UUID snapshotId = UUID.randomUUID();
            setStatementTimeout(requestStartedAt, cancellation);
            jdbc.update("""
                    INSERT INTO knowflow.questions
                        (id, owner_user_id, knowledge_base_id, request_id, snapshot_id, question_text)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """, questionId, user.id(), knowledgeBaseId, requestId, snapshotId, question);
            for (IndexRef index : indexes) {
                setStatementTimeout(requestStartedAt, cancellation);
                jdbc.update("""
                        INSERT INTO knowflow.question_scope_indexes
                            (question_id, owner_user_id, knowledge_base_id, document_id,
                             content_version_id, index_version_id)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """, questionId, user.id(), knowledgeBaseId, index.documentId(),
                        index.contentVersionId(), index.indexVersionId());
            }
            return new QuestionSnapshot(questionId, snapshotId, user.id(), knowledgeBaseId,
                    List.copyOf(indexes));
        });
        if (snapshot == null) {
            throw new IllegalStateException("Question snapshot transaction returned no result");
        }
        return snapshot;
    }

    private AnswerResponse saveAnswer(AuthenticatedUser user, QuestionSnapshot snapshot,
                                      String requestId, AiAnswerResponse response,
                                      QuestionCancellation cancellation,
                                      long requestStartedAt) {
        requireNotCancelled(cancellation);
        setStatementTimeout(requestStartedAt, cancellation);
        lockKnowledgeBase(user.id(), snapshot.knowledgeBaseId());
        for (IndexRef index : snapshot.indexes()) {
            setStatementTimeout(requestStartedAt, cancellation);
            List<Boolean> stillVisible = jdbc.query("""
                    SELECT d.status = 'ACTIVE' AND kb.status = 'ACTIVE'
                           AND d.current_content_version_id = ?
                           AND d.active_index_version_id = ? AND iv.status = 'READY'
                      FROM knowflow.documents d
                      JOIN knowflow.knowledge_bases kb
                        ON kb.id = d.knowledge_base_id AND kb.owner_user_id = d.owner_user_id
                      JOIN knowflow.index_versions iv ON iv.id = d.active_index_version_id
                     WHERE d.id = ? AND d.knowledge_base_id = ? AND d.owner_user_id = ?
                     FOR UPDATE OF d
                    """, (result, row) -> result.getBoolean(1), index.contentVersionId(),
                    index.indexVersionId(), index.documentId(), snapshot.knowledgeBaseId(),
                    snapshot.ownerId());
            if (stillVisible.isEmpty() || !stillVisible.getFirst()) {
                throw ApiFailure.documentUnavailable();
            }
        }

        List<SourceResponse> storedSources = new ArrayList<>(response.sources().size());
        Set<String> upstreamSourceIds = new HashSet<>();
        String publicAnswer = response.answer();
        for (AiAnswerResponse.AiSource source : response.sources()) {
            requireNotCancelled(cancellation);
            if (source == null || source.sourceId() == null
                    || !IDENTIFIER.matcher(source.sourceId()).matches()
                    || !upstreamSourceIds.add(source.sourceId()) || source.documentId() == null
                    || source.contentVersionId() == null || source.indexVersionId() == null
                    || source.chunkId() == null || source.quote() == null
                    || source.quote().isBlank() || source.quote().codePointCount(0,
                    source.quote().length()) > 16000 || source.locator() == null) {
                throw ApiFailure.aiProcessingFailed();
            }
            IndexRef allowed = snapshot.indexes().stream()
                    .filter(index -> index.documentId().equals(source.documentId())
                            && index.contentVersionId().equals(source.contentVersionId())
                            && index.indexVersionId().equals(source.indexVersionId()))
                    .findFirst().orElseThrow(ApiFailure::aiProcessingFailed);
            setStatementTimeout(requestStartedAt, cancellation);
            StoredChunk chunk = readCurrentChunk(snapshot, allowed, source);
            if (!source.quote().equals(chunk.text()) && !chunk.text().contains(source.quote())) {
                throw ApiFailure.aiProcessingFailed();
            }
            if (!sameLocator(source.locator(), chunk.locator())) {
                throw ApiFailure.aiProcessingFailed();
            }
            UUID publicSourceId = UUID.nameUUIDFromBytes((snapshot.questionId() + ":"
                    + source.sourceId()).getBytes(StandardCharsets.UTF_8));
            setStatementTimeout(requestStartedAt, cancellation);
            jdbc.update("""
                    INSERT INTO knowflow.question_sources
                        (source_id, question_id, owner_user_id, knowledge_base_id, document_id,
                         content_version_id, index_version_id, chunk_id, locator_kind,
                         source_page, source_start, source_end, quote)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, publicSourceId, snapshot.questionId(), snapshot.ownerId(),
                    snapshot.knowledgeBaseId(), source.documentId(), source.contentVersionId(),
                    source.indexVersionId(), source.chunkId(), chunk.locator().kind(),
                    chunk.locator().page(), chunk.locator().start(), chunk.locator().end(),
                    source.quote());
            storedSources.add(new SourceResponse(ApiError.CONTRACT_VERSION, publicSourceId,
                    source.documentId(), source.contentVersionId(), source.indexVersionId(),
                    source.chunkId(), toPublicLocator(chunk.locator()), source.quote()));
            publicAnswer = publicAnswer.replace("[" + source.sourceId() + "]",
                    "[" + publicSourceId + "]");
        }
        requireNotCancelled(cancellation);
        setStatementTimeout(requestStartedAt, cancellation);
        jdbc.update("""
                UPDATE knowflow.questions
                   SET status = 'SUCCEEDED', answer_text = ?, has_answer = ?,
                       finished_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                 WHERE id = ? AND status = 'PROCESSING'
                """, publicAnswer, response.hasAnswer(), snapshot.questionId());
        requireNotCancelled(cancellation);
        remainingBudget(requestStartedAt);
        return new AnswerResponse(ApiError.CONTRACT_VERSION, requestId, publicAnswer,
                response.hasAnswer(), List.copyOf(storedSources));
    }

    private StoredChunk readCurrentChunk(QuestionSnapshot snapshot, IndexRef allowed,
                                         AiAnswerResponse.AiSource source) {
        List<StoredChunk> rows = jdbc.query("""
                SELECT ch.text_content, ch.locator_kind, ch.source_page, ch.source_start,
                       ch.source_end
                  FROM knowflow.chunks ch
                  JOIN knowflow.documents d
                    ON d.id = ch.document_id AND d.knowledge_base_id = ?
                   AND d.owner_user_id = ? AND d.status = 'ACTIVE'
                  JOIN knowflow.knowledge_bases kb
                    ON kb.id = d.knowledge_base_id AND kb.owner_user_id = d.owner_user_id
                   AND kb.status = 'ACTIVE'
                 WHERE ch.id = ? AND ch.document_id = ? AND ch.content_version_id = ?
                   AND ch.index_version_id = ? AND d.current_content_version_id = ?
                   AND d.active_index_version_id = ch.index_version_id
                """, (result, row) -> new StoredChunk(result.getString("text_content"),
                new AiAnswerResponse.Locator(result.getString("locator_kind"),
                        (Integer) result.getObject("source_page"),
                        (Integer) result.getObject("source_start"),
                        (Integer) result.getObject("source_end"),
                        "text_range".equals(result.getString("locator_kind"))
                                ? "unicode_code_point" : null)),
                snapshot.knowledgeBaseId(), snapshot.ownerId(), source.chunkId(),
                allowed.documentId(), allowed.contentVersionId(), allowed.indexVersionId(),
                allowed.contentVersionId());
        if (rows.isEmpty()) {
            throw ApiFailure.aiProcessingFailed();
        }
        return rows.getFirst();
    }

    private void lockKnowledgeBase(UUID ownerId, UUID knowledgeBaseId) {
        List<UUID> rows = jdbc.query("""
                SELECT id FROM knowflow.knowledge_bases
                 WHERE id = ? AND owner_user_id = ? AND status = 'ACTIVE'
                 FOR UPDATE
                """, (result, row) -> result.getObject(1, UUID.class),
                knowledgeBaseId, ownerId);
        if (rows.isEmpty()) {
            throw ApiFailure.documentUnavailable();
        }
    }

    private void setStatementTimeout(long requestStartedAt,
                                     QuestionCancellation cancellation) {
        requireNotCancelled(cancellation);
        long remainingNanos = remainingBudget(requestStartedAt).toNanos();
        long timeoutMillis = Math.max(1, (remainingNanos + 999_999) / 1_000_000);
        String timeout = timeoutMillis + "ms";
        jdbc.queryForObject("SELECT set_config('statement_timeout', ?, true)",
                String.class, timeout);
        jdbc.queryForObject("SELECT set_config('lock_timeout', ?, true)",
                String.class, timeout);
    }

    private void registerDeadlineCheck(long requestStartedAt,
                                       QuestionCancellation cancellation) {
        TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void beforeCommit(boolean readOnly) {
                        requireNotCancelled(cancellation);
                        remainingBudget(requestStartedAt);
                    }
                });
    }

    private void markFailed(UUID questionId, String failureCode) {
        boundedCleanup(() -> jdbc.update("""
                UPDATE knowflow.questions
                   SET status = 'FAILED', failure_code = ?, answer_text = NULL,
                       has_answer = NULL, finished_at = CURRENT_TIMESTAMP,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE id = ? AND status = 'PROCESSING'
                """, failureCode, questionId));
    }

    private AnswerResponse cancelQuestion(UUID questionId, QuestionCancellation cancellation) {
        boolean interrupted = Thread.interrupted();
        try {
            if (cancellation.reason() == QuestionCancellation.Reason.TIMEOUT) {
                markFailed(questionId, "PROCESSING_TIMEOUT");
                throw ApiFailure.processingTimeout();
            }
            markCancelled(questionId);
            return null;
        } finally {
            if (interrupted) {
                Thread.currentThread().interrupt();
            }
        }
    }

    private void markCancelled(UUID questionId) {
        boundedCleanup(() -> jdbc.update("""
                UPDATE knowflow.questions
                   SET status = 'CANCELLED', answer_text = NULL, has_answer = NULL,
                       failure_code = NULL, finished_at = CURRENT_TIMESTAMP,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE id = ? AND status = 'PROCESSING'
                """, questionId));
    }

    private void boundedCleanup(Runnable update) {
        try {
            transactions.executeWithoutResult(status -> {
                String timeout = CLEANUP_TIMEOUT_MILLIS + "ms";
                jdbc.queryForObject("SELECT set_config('statement_timeout', ?, true)",
                        String.class, timeout);
                jdbc.queryForObject("SELECT set_config('lock_timeout', ?, true)",
                        String.class, timeout);
                update.run();
            });
        } catch (DataAccessException | TransactionException ignored) {
            // A database outage cannot be repaired synchronously; the row remains PROCESSING.
        }
    }

    private Duration remainingBudget(long requestStartedAt) {
        long totalNanos = TimeUnit.SECONDS.toNanos(properties.getTotalBudgetSeconds());
        long remainingNanos = totalNanos - (System.nanoTime() - requestStartedAt);
        if (remainingNanos <= 0) {
            throw new IllegalStateException("Question budget exhausted",
                    new java.util.concurrent.TimeoutException());
        }
        return Duration.ofNanos(remainingNanos);
    }

    private static void requireNotCancelled(QuestionCancellation cancellation) {
        if (cancellation.reason() != null) {
            throw new CancellationException("Question request was cancelled");
        }
    }

    private static String validateQuestion(PublicQuestion input) {
        if (input == null || input.question() == null || input.question().isBlank()
                || input.question().indexOf('\0') >= 0
                || input.question().codePointCount(0, input.question().length()) > 16000) {
            throw ApiFailure.invalidRequest();
        }
        return input.question();
    }

    private static void validateAnswer(AiAnswerResponse response) {
        if (response == null || response.answer() == null || response.hasAnswer() == null
                || response.sources() == null || response.sources().size() > 5
                || response.answer().codePointCount(0, response.answer().length()) > 16000
                || (response.hasAnswer() && response.sources().isEmpty())
                || (!response.hasAnswer() && !response.sources().isEmpty())) {
            throw ApiFailure.aiProcessingFailed();
        }
    }

    private static boolean sameLocator(AiAnswerResponse.Locator actual,
                                       AiAnswerResponse.Locator stored) {
        return actual != null && java.util.Objects.equals(actual.kind(), stored.kind())
                && java.util.Objects.equals(actual.page(), stored.page())
                && java.util.Objects.equals(actual.start(), stored.start())
                && java.util.Objects.equals(actual.end(), stored.end())
                && java.util.Objects.equals(actual.unit(), stored.unit());
    }

    private static SourceResponse.Locator toPublicLocator(AiAnswerResponse.Locator locator) {
        return new SourceResponse.Locator(locator.kind(), locator.page(), locator.start(),
                locator.end(), locator.unit());
    }

    private static boolean isTimeout(Throwable failure) {
        for (Throwable current = failure; current != null; current = current.getCause()) {
            if (current instanceof TimeoutException
                    || current.getClass().getSimpleName().toLowerCase(java.util.Locale.ROOT)
                    .contains("timeout")
                    || current instanceof SQLException sqlException
                    && ("57014".equals(sqlException.getSQLState())
                    || "55P03".equals(sqlException.getSQLState()))) {
                return true;
            }
        }
        return false;
    }

    private record IndexRef(UUID documentId, UUID contentVersionId, UUID indexVersionId) {}
    private record QuestionSnapshot(UUID questionId, UUID snapshotId, UUID ownerId,
                                    UUID knowledgeBaseId, List<IndexRef> indexes) {}
    private record StoredChunk(String text, AiAnswerResponse.Locator locator) {}
}
