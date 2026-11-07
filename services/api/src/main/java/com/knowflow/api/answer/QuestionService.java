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
import java.util.concurrent.Semaphore;
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
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Service
@Profile("database")
public class QuestionService {
    private static final Logger LOGGER = LoggerFactory.getLogger(QuestionService.class);
    private static final int MAX_SCOPE_DOCUMENTS = 100;
    private static final int CLEANUP_TIMEOUT_MILLIS = 2_000;
    private static final Pattern IDENTIFIER = Pattern.compile("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}");

    private final JdbcTemplate jdbc;
    private final TransactionTemplate transactions;
    private final AiAnswerClient client;
    private final QuestionProperties properties;
    private final Semaphore questionPermits;

    public QuestionService(JdbcTemplate jdbc, TransactionTemplate transactions,
                           AiAnswerClient client, QuestionProperties properties) {
        this.jdbc = jdbc;
        this.transactions = transactions;
        this.client = client;
        this.properties = properties;
        this.questionPermits = new Semaphore(properties.getMaxConcurrentRequests());
    }

    public AnswerResponse ask(AuthenticatedUser user, UUID knowledgeBaseId, PublicQuestion input) {
        return ask(user, knowledgeBaseId, input, System.nanoTime(), new QuestionCancellation());
    }

    AnswerResponse ask(AuthenticatedUser user, UUID knowledgeBaseId, PublicQuestion input,
                       long requestStartedAt, QuestionCancellation cancellation,
                       String idempotencyKey) {
        return ask(user, knowledgeBaseId, input, requestStartedAt, cancellation,
                parseIdempotencyKey(idempotencyKey));
    }

    Flux<PublicAnswerStreamEvent> stream(AuthenticatedUser user, UUID knowledgeBaseId,
                                         PublicQuestion input, QuestionCancellation cancellation) {
        return stream(user, knowledgeBaseId, input, cancellation, null);
    }

    Flux<PublicAnswerStreamEvent> stream(AuthenticatedUser user, UUID knowledgeBaseId,
                                         PublicQuestion input, QuestionCancellation cancellation,
                                         String idempotencyKey) {
        return stream(user, knowledgeBaseId, input, cancellation, idempotencyKey,
                System.nanoTime());
    }

    Flux<PublicAnswerStreamEvent> stream(AuthenticatedUser user, UUID knowledgeBaseId,
                                         PublicQuestion input, QuestionCancellation cancellation,
                                         String idempotencyKey, long requestStartedAt) {
        return stream(user, knowledgeBaseId, input, cancellation, idempotencyKey,
                requestStartedAt, UUID.randomUUID().toString());
    }

    Flux<PublicAnswerStreamEvent> stream(AuthenticatedUser user, UUID knowledgeBaseId,
                                         PublicQuestion input, QuestionCancellation cancellation,
                                         String idempotencyKey, long requestStartedAt,
                                         String requestId) {
        return Flux.defer(() -> {
            if (!questionPermits.tryAcquire()) {
                return Flux.just(new PublicAnswerStreamEvent(ApiError.CONTRACT_VERSION,
                        requestId, 1, "error", null, null, null, "AI_PROCESSING_FAILED",
                        "The AI service could not complete the request.", true));
            }
            try {
                String question = validateQuestion(input);
                QuestionSnapshot snapshot;
                try {
                    snapshot = createSnapshot(user, knowledgeBaseId, question, requestId,
                            requestStartedAt, cancellation, parseIdempotencyKey(idempotencyKey));
                } catch (ApiFailure failure) {
                    if ("QUESTION_REQUEST_CONFLICT".equals(failure.code())) {
                        return Flux.just(new PublicAnswerStreamEvent(ApiError.CONTRACT_VERSION,
                                requestId, 1, "error", null, null, null, failure.code(),
                                failure.getMessage(), false))
                                .doFinally(signal -> questionPermits.release());
                    }
                    throw failure;
                }
                TrustedAnswerRequest request = new TrustedAnswerRequest(ApiError.CONTRACT_VERSION,
                        requestId, question, new TrustedAnswerRequest.TrustedScope(user.id(),
                        knowledgeBaseId, snapshot.snapshotId(), snapshot.indexes().stream()
                        .map(index -> new TrustedAnswerRequest.IndexScope(index.documentId(),
                                index.contentVersionId(), index.indexVersionId())).toList()));
                StreamState state = new StreamState(requestId, snapshot, requestStartedAt, cancellation);
                Flux<PublicAnswerStreamEvent> upstream = client.stream(request,
                                remainingBudget(requestStartedAt))
                        .publishOn(Schedulers.boundedElastic())
                        .concatMap(event -> state.handle(event, user, request));
                return Flux.concat(Mono.fromCallable(() -> {
                            state.assertVisible();
                            return state.event("started");
                        }).subscribeOn(Schedulers.boundedElastic()), upstream)
                        .doOnCancel(() -> {
                            cancellation.clientDisconnected();
                            state.cancel();
                        })
                        .onErrorResume(failure -> state.error(failure))
                        .doFinally(signal -> questionPermits.release());
            } catch (RuntimeException | Error failure) {
                questionPermits.release();
                throw failure;
            }
        }).subscribeOn(Schedulers.boundedElastic());
    }

    AnswerResponse ask(AuthenticatedUser user, UUID knowledgeBaseId, PublicQuestion input,
                       long requestStartedAt, QuestionCancellation cancellation) {
        return ask(user, knowledgeBaseId, input, requestStartedAt, cancellation, (UUID) null);
    }

    AnswerResponse ask(AuthenticatedUser user, UUID knowledgeBaseId, PublicQuestion input,
                       long requestStartedAt, QuestionCancellation cancellation,
                       UUID idempotencyKey) {
        if (!questionPermits.tryAcquire()) {
            throw ApiFailure.aiProcessingFailed();
        }
        try {
            return askAdmitted(user, knowledgeBaseId, input, requestStartedAt,
                    cancellation, idempotencyKey);
        } finally {
            questionPermits.release();
        }
    }

    private AnswerResponse askAdmitted(AuthenticatedUser user, UUID knowledgeBaseId,
                                       PublicQuestion input, long requestStartedAt,
                                       QuestionCancellation cancellation,
                                       UUID idempotencyKey) {
        String question = validateQuestion(input);
        String requestId = UUID.randomUUID().toString();
        QuestionSnapshot snapshot;
        try {
            snapshot = createSnapshot(user, knowledgeBaseId, question, requestId,
                    requestStartedAt, cancellation, idempotencyKey);
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
        long aiStartedAt = System.nanoTime();
        try {
            if (cancellation.reason() != null) {
                throw new CancellationException("Question request was cancelled");
            }
            response = client.answer(request, remainingBudget(requestStartedAt));
            LOGGER.info("question_stage request_id={} stage=ai_answer duration_ms={} outcome=success",
                    requestId, TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - aiStartedAt));
            validateAnswer(response);
            if (cancellation.reason() != null) {
                throw new CancellationException("Question request was cancelled");
            }
            remainingBudget(requestStartedAt);
        } catch (CancellationException cancelled) {
            return cancelQuestion(snapshot.questionId(), cancellation);
        } catch (RuntimeException failure) {
            String failureCode = failure instanceof ApiFailure apiFailure
                    ? apiFailure.code() : "AI_PROCESSING_FAILED";
            LOGGER.info("question_stage request_id={} stage=ai_answer duration_ms={} outcome=failed code={}",
                    requestId, TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - aiStartedAt),
                    failureCode);
            if (cancellation.reason() != null) {
                return cancelQuestion(snapshot.questionId(), cancellation);
            }
            boolean timeout = isTimeout(failure);
            markFailed(snapshot.questionId(), timeout ? "PROCESSING_TIMEOUT" : "AI_PROCESSING_FAILED");
            throw timeout ? ApiFailure.processingTimeout() : ApiFailure.aiProcessingFailed();
        }

        try {
            long persistenceStartedAt = System.nanoTime();
            AnswerResponse saved = transactions.execute(status -> {
                registerDeadlineCheck(requestStartedAt, cancellation);
                return saveAnswer(user, snapshot, requestId, response, cancellation,
                        requestStartedAt);
            });
            if (saved == null) {
                throw new IllegalStateException("Question persistence did not return a response");
            }
            LOGGER.info("question_stage request_id={} stage=persistence duration_ms={} outcome=success",
                    requestId, TimeUnit.NANOSECONDS.toMillis(
                            System.nanoTime() - persistenceStartedAt));
            return saved;
        } catch (CancellationException cancelled) {
            return cancelQuestion(snapshot.questionId(), cancellation);
        } catch (ApiFailure failure) {
            if (cancellation.reason() != null) {
                return cancelQuestion(snapshot.questionId(), cancellation);
            }
            String failureCode = "DOCUMENT_UNAVAILABLE".equals(failure.code())
                    || "PROCESSING_TIMEOUT".equals(failure.code())
                    ? failure.code() : "AI_PROCESSING_FAILED";
            markFailed(snapshot.questionId(), failureCode);
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
                                            QuestionCancellation cancellation,
                                            UUID idempotencyKey) {
        QuestionSnapshot snapshot = transactions.execute(status -> {
            registerDeadlineCheck(requestStartedAt, cancellation);
            setStatementTimeout(requestStartedAt, cancellation);
            List<UUID> ownedKnowledgeBases = jdbc.query("""
                    SELECT id FROM knowflow.knowledge_bases
                     WHERE id = ? AND owner_user_id = ? AND status = 'ACTIVE'
                     FOR SHARE
                    """, (row, index) -> row.getObject(1, UUID.class), knowledgeBaseId, user.id());
            if (ownedKnowledgeBases.isEmpty()) {
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
                       AND d.status = 'ACTIVE' AND iv.status = 'READY' AND iv.cleaned_at IS NULL
                     ORDER BY d.id
                     LIMIT ? FOR SHARE OF d
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
            long remainingMillis = Math.max(1, remainingBudget(requestStartedAt).toMillis());
            List<UUID> inserted;
            if (idempotencyKey == null) {
                inserted = jdbc.query("""
                        INSERT INTO knowflow.questions
                            (id, owner_user_id, knowledge_base_id, request_id, snapshot_id,
                             question_text, deadline_at)
                        VALUES (?, ?, ?, ?, ?, ?, clock_timestamp() + (? * INTERVAL '1 millisecond'))
                        RETURNING id
                        """, (result, row) -> result.getObject(1, UUID.class), questionId,
                        user.id(), knowledgeBaseId, requestId, snapshotId, question, remainingMillis);
            } else {
                inserted = jdbc.query("""
                        INSERT INTO knowflow.questions
                            (id, owner_user_id, knowledge_base_id, request_id, snapshot_id,
                             question_text, idempotency_key, deadline_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?,
                                clock_timestamp() + (? * INTERVAL '1 millisecond'))
                        ON CONFLICT (owner_user_id, idempotency_key)
                            WHERE idempotency_key IS NOT NULL DO NOTHING
                        RETURNING id
                        """, (result, row) -> result.getObject(1, UUID.class), questionId,
                        user.id(), knowledgeBaseId, requestId, snapshotId, question,
                        idempotencyKey, remainingMillis);
            }
            if (inserted.isEmpty()) {
                throw ApiFailure.questionRequestConflict();
            }
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

    static UUID parseIdempotencyKey(String value) {
        if (value == null) {
            return null;
        }
        try {
            UUID parsed = UUID.fromString(value);
            if (!parsed.toString().equalsIgnoreCase(value)) {
                throw ApiFailure.invalidRequest();
            }
            return parsed;
        } catch (IllegalArgumentException invalid) {
            throw ApiFailure.invalidRequest();
        }
    }

    private AnswerResponse saveAnswer(AuthenticatedUser user, QuestionSnapshot snapshot,
                                      String requestId, AiAnswerResponse response,
                                      QuestionCancellation cancellation,
                                      long requestStartedAt) {
        AnswerResponse prepared = prepareAnswer(user, snapshot, requestId, response,
                cancellation, requestStartedAt);
        for (SourceResponse source : prepared.sources()) {
            requireNotCancelled(cancellation);
            setStatementTimeout(requestStartedAt, cancellation);
            SourceResponse.Locator locator = source.locator();
            jdbc.update("""
                    INSERT INTO knowflow.question_sources
                        (source_id, question_id, owner_user_id, knowledge_base_id, document_id,
                         content_version_id, index_version_id, chunk_id, locator_kind,
                         source_page, source_start, source_end, quote)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, source.sourceId(), snapshot.questionId(), snapshot.ownerId(),
                    snapshot.knowledgeBaseId(), source.documentId(), source.contentVersionId(),
                    source.indexVersionId(), source.chunkId(), locator.kind(), locator.page(),
                    locator.start(), locator.end(), source.quote());
        }
        requireNotCancelled(cancellation);
        setStatementTimeout(requestStartedAt, cancellation);
        int updated = jdbc.update("""
                UPDATE knowflow.questions
                   SET status = 'SUCCEEDED', answer_text = ?, has_answer = ?,
                       embedding_model_profile_id = ?, llm_model_profile_id = ?,
                       finished_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                 WHERE id = ? AND status = 'PROCESSING'
                   AND deadline_at > clock_timestamp()
                """, prepared.answer(), prepared.hasAnswer(),
                response.modelProfile() == null ? null
                        : response.modelProfile().embeddingModelProfileId(),
                response.modelProfile() == null ? null
                        : response.modelProfile().llmModelProfileId(), snapshot.questionId());
        if (updated != 1) {
            throw ApiFailure.processingTimeout();
        }
        requireNotCancelled(cancellation);
        remainingBudget(requestStartedAt);
        return prepared;
    }

    private AnswerResponse prepareAnswer(AuthenticatedUser user, QuestionSnapshot snapshot,
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
                           AND iv.status IN ('READY', 'RETIRED')
                           AND iv.cleaned_at IS NULL
                      FROM knowflow.documents d
                      JOIN knowflow.knowledge_bases kb
                        ON kb.id = d.knowledge_base_id AND kb.owner_user_id = d.owner_user_id
                      JOIN knowflow.index_versions iv ON iv.document_id = d.id
                       AND iv.content_version_id = ? AND iv.id = ?
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
            if (!locatorWithinChunk(source.locator(), chunk.locator())) {
                throw ApiFailure.aiProcessingFailed();
            }
            UUID publicSourceId = UUID.nameUUIDFromBytes((snapshot.questionId() + ":"
                    + source.sourceId()).getBytes(StandardCharsets.UTF_8));
            storedSources.add(new SourceResponse(ApiError.CONTRACT_VERSION, publicSourceId,
                    source.documentId(), source.contentVersionId(), source.indexVersionId(),
                    source.chunkId(), toPublicLocator(source.locator()), source.quote()));
            publicAnswer = publicAnswer.replace("[" + source.sourceId() + "]",
                    "[" + publicSourceId + "]");
        }
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
                  JOIN knowflow.index_versions iv ON iv.id = ch.index_version_id
                   AND iv.document_id = ch.document_id AND iv.content_version_id = ch.content_version_id
                   AND iv.status IN ('READY', 'RETIRED') AND iv.cleaned_at IS NULL
                 WHERE ch.id = ? AND ch.document_id = ? AND ch.content_version_id = ?
                   AND ch.index_version_id = ?
                """, (result, row) -> new StoredChunk(result.getString("text_content"),
                new AiAnswerResponse.Locator(result.getString("locator_kind"),
                        (Integer) result.getObject("source_page"),
                        (Integer) result.getObject("source_start"),
                        (Integer) result.getObject("source_end"),
                        "text_range".equals(result.getString("locator_kind"))
                                ? "unicode_code_point" : null)),
                snapshot.knowledgeBaseId(), snapshot.ownerId(), source.chunkId(),
                allowed.documentId(), allowed.contentVersionId(), allowed.indexVersionId());
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

    static boolean locatorWithinChunk(AiAnswerResponse.Locator actual,
                                      AiAnswerResponse.Locator stored) {
        if (actual == null || stored == null
                || !java.util.Objects.equals(actual.kind(), stored.kind())) {
            return false;
        }
        if ("pdf_page".equals(stored.kind())) {
            return java.util.Objects.equals(actual.page(), stored.page())
                    && actual.start() == null && actual.end() == null
                    && actual.unit() == null;
        }
        if ("text_range".equals(stored.kind())) {
            return actual.page() == null
                    && java.util.Objects.equals(actual.unit(), stored.unit())
                    && actual.start() != null && actual.end() != null
                    && stored.start() != null && stored.end() != null
                    && actual.start() >= stored.start()
                    && actual.end() > actual.start()
                    && actual.end() <= stored.end();
        }
        return false;
    }

    private static SourceResponse.Locator toPublicLocator(AiAnswerResponse.Locator locator) {
        return new SourceResponse.Locator(locator.kind(), locator.page(), locator.start(),
                locator.end(), locator.unit());
    }

    private static boolean isTimeout(Throwable failure) {
        for (Throwable current = failure; current != null; current = current.getCause()) {
            if ((current instanceof ApiFailure apiFailure
                    && "PROCESSING_TIMEOUT".equals(apiFailure.code()))
                    || current instanceof TimeoutException
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

    private final class StreamState {
        private final String requestId;
        private final QuestionSnapshot snapshot;
        private final long requestStartedAt;
        private final QuestionCancellation cancellation;
        private final StringBuilder answer = new StringBuilder();
        private final StreamCitationMapper citations;
        private long sequence;
        private boolean sourcesPrepared;
        private AiAnswerResponse pendingAnswer;
        private ModelProfile modelProfile;

        private StreamState(String requestId, QuestionSnapshot snapshot, long requestStartedAt,
                            QuestionCancellation cancellation) {
            this.requestId = requestId;
            this.snapshot = snapshot;
            this.requestStartedAt = requestStartedAt;
            this.cancellation = cancellation;
            this.citations = new StreamCitationMapper(snapshot.questionId());
        }

        private Flux<PublicAnswerStreamEvent> handle(AiAnswerStreamEvent event,
                                                       AuthenticatedUser user,
                                                       TrustedAnswerRequest request) {
            assertVisible();
            return switch (event.event()) {
                case "started" -> Mono.fromCallable(() -> {
                            ModelProfile profile = event.modelProfile();
                            modelProfile = profile;
                            if (profile != null) {
                                jdbc.update("""
                                        UPDATE knowflow.questions
                                           SET embedding_model_profile_id = ?,
                                               llm_model_profile_id = ?,
                                               updated_at = CURRENT_TIMESTAMP
                                         WHERE id = ? AND status = 'PROCESSING'
                                        """, profile.embeddingModelProfileId(),
                                        profile.llmModelProfileId(), snapshot.questionId());
                            }
                            return Boolean.TRUE;
                        }).subscribeOn(Schedulers.boundedElastic()).thenMany(Flux.empty());
                case "delta" -> {
                    answer.append(event.delta());
                    String visible = citations.feed(event.delta());
                    yield visible.isEmpty() ? Flux.empty() : Flux.just(deltaEvent(visible));
                }
                case "sources" -> prepareAndEmitSources(event, user, request);
                case "completed" -> {
                    if (!sourcesPrepared || pendingAnswer == null) {
                        yield Flux.error(new IllegalStateException("AI stream completed before sources"));
                    }
                    yield Mono.fromCallable(() -> transactions.execute(status -> {
                                registerDeadlineCheck(requestStartedAt, cancellation);
                                saveAnswer(user, snapshot, requestId, pendingAnswer, cancellation,
                                        requestStartedAt);
                                return event("completed");
                            }))
                            .switchIfEmpty(Mono.error(new IllegalStateException(
                                    "Question stream completion did not return an event")))
                            .subscribeOn(Schedulers.boundedElastic()).flux();
                }
                case "cancelled" -> {
                    cancellation.clientDisconnected();
                    if (cancellation.reason() == QuestionCancellation.Reason.TIMEOUT) {
                        markFailed(snapshot.questionId(), "PROCESSING_TIMEOUT");
                        yield Flux.just(errorEvent("PROCESSING_TIMEOUT", "PROCESSING_TIMEOUT", true));
                    }
                    markCancelled(snapshot.questionId());
                    yield Flux.just(event("cancelled"));
                }
                case "error" -> {
                    if (cancellation.reason() == QuestionCancellation.Reason.CLIENT_DISCONNECTED) {
                        markCancelled(snapshot.questionId());
                        yield Flux.empty();
                    }
                    boolean timeout = cancellation.reason() == QuestionCancellation.Reason.TIMEOUT;
                    String code = timeout ? "PROCESSING_TIMEOUT" : event.code();
                    String message = timeout ? code : event.message();
                    markFailed(snapshot.questionId(), code);
                    yield Flux.just(errorEvent(code, message, timeout || event.retryable()));
                }
                default -> Flux.error(new IllegalStateException("AI stream event type is unknown"));
            };
        }

        private Flux<PublicAnswerStreamEvent> prepareAndEmitSources(AiAnswerStreamEvent event,
                                                                      AuthenticatedUser user,
                                                                      TrustedAnswerRequest request) {
            List<AiAnswerResponse.AiSource> sources = event.sources().stream()
                    .map(source -> new AiAnswerResponse.AiSource(source.sourceId(), source.documentId(),
                            source.contentVersionId(), source.indexVersionId(), source.chunkId(),
                            source.locator(), source.quote())).toList();
            AiAnswerResponse response = new AiAnswerResponse(ApiError.CONTRACT_VERSION, requestId,
                    answer.toString(), event.hasAnswer(), sources, modelProfile);
            validateAnswer(response);
            citations.finish(sources.stream().map(AiAnswerResponse.AiSource::sourceId).collect(java.util.stream.Collectors.toSet()));
            return Mono.fromCallable(() -> transactions.execute(status -> {
                        registerDeadlineCheck(requestStartedAt, cancellation);
                        setStatementTimeout(requestStartedAt, cancellation);
                        return prepareAnswer(user, snapshot, requestId, response, cancellation,
                                requestStartedAt);
                    }))
                    .switchIfEmpty(Mono.error(new IllegalStateException(
                            "Question stream persistence did not return a response")))
                    .subscribeOn(Schedulers.boundedElastic())
                    .map(saved -> {
                        assertVisible();
                        pendingAnswer = response;
                        sourcesPrepared = true;
                        List<AnswerStreamSource> publicSources = saved.sources().stream()
                                .map(source -> new AnswerStreamSource(source.sourceId(), source.documentId(),
                                        source.contentVersionId(), source.indexVersionId(), source.chunkId(),
                                        source.locator(), source.quote())).toList();
                        return sourcesEvent(saved.hasAnswer(), publicSources);
                    }).flux();
        }

        private Flux<PublicAnswerStreamEvent> error(Throwable failure) {
            if (cancellation.reason() == QuestionCancellation.Reason.CLIENT_DISCONNECTED) {
                markCancelled(snapshot.questionId());
                return Flux.empty();
            }
            boolean timeout = cancellation.reason() == QuestionCancellation.Reason.TIMEOUT
                    || isTimeout(failure);
            String code = timeout ? "PROCESSING_TIMEOUT"
                    : failure instanceof ApiFailure apiFailure
                    && "DOCUMENT_UNAVAILABLE".equals(apiFailure.code())
                    ? "DOCUMENT_UNAVAILABLE" : "AI_PROCESSING_FAILED";
            markFailed(snapshot.questionId(), code);
            return Flux.just(errorEvent(code, code,
                    timeout || "AI_PROCESSING_FAILED".equals(code)));
        }

        private void cancel() {
            if (cancellation.reason() == QuestionCancellation.Reason.TIMEOUT) {
                markFailed(snapshot.questionId(), "PROCESSING_TIMEOUT");
            } else {
                markCancelled(snapshot.questionId());
            }
        }

        private void assertVisible() {
            String predicates = snapshot.indexes().stream()
                    .map(ignored -> "(d.id = ? AND iv.content_version_id = ? AND iv.id = ?)")
                    .collect(java.util.stream.Collectors.joining(" OR "));
            List<Object> parameters = new ArrayList<>();
            parameters.add(snapshot.knowledgeBaseId());
            parameters.add(snapshot.ownerId());
            for (IndexRef index : snapshot.indexes()) {
                parameters.add(index.documentId());
                parameters.add(index.contentVersionId());
                parameters.add(index.indexVersionId());
            }
            Integer visible = jdbc.queryForObject("""
                    SELECT count(DISTINCT d.id)
                      FROM knowflow.documents d
                      JOIN knowflow.knowledge_bases kb
                        ON kb.id = d.knowledge_base_id AND kb.owner_user_id = d.owner_user_id
                      JOIN knowflow.index_versions iv ON iv.document_id = d.id
                     WHERE d.knowledge_base_id = ? AND d.owner_user_id = ?
                       AND d.status = 'ACTIVE' AND kb.status = 'ACTIVE'
                       AND iv.status IN ('READY', 'RETIRED') AND iv.cleaned_at IS NULL
                       AND (""" + predicates + ")", Integer.class, parameters.toArray());
            if (visible == null || visible != snapshot.indexes().size()) {
                throw ApiFailure.documentUnavailable();
            }
        }

        private PublicAnswerStreamEvent event(String type) {
            return new PublicAnswerStreamEvent(ApiError.CONTRACT_VERSION, requestId, ++sequence,
                    type, null, null, null, null, null, null);
        }

        private PublicAnswerStreamEvent deltaEvent(String delta) {
            return new PublicAnswerStreamEvent(ApiError.CONTRACT_VERSION, requestId, ++sequence,
                    "delta", delta, null, null, null, null, null);
        }

        private PublicAnswerStreamEvent sourcesEvent(boolean hasAnswer,
                                                       List<AnswerStreamSource> sources) {
            return new PublicAnswerStreamEvent(ApiError.CONTRACT_VERSION, requestId, ++sequence,
                    "sources", null, hasAnswer, sources, null, null, null);
        }

        private PublicAnswerStreamEvent errorEvent(String code, String message, boolean retryable) {
            return new PublicAnswerStreamEvent(ApiError.CONTRACT_VERSION, requestId, ++sequence,
                    "error", null, null, null, code, message, retryable);
        }
    }
}
