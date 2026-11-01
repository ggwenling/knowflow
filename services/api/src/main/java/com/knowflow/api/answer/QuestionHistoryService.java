package com.knowflow.api.answer;

import java.util.List;
import java.util.UUID;

import com.knowflow.api.error.ApiError;
import com.knowflow.api.error.ApiFailure;
import com.knowflow.api.security.AuthenticatedUser;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Profile("database")
public class QuestionHistoryService {
    private static final int MAX_LIMIT = 100;
    private static final int MAX_OFFSET = 1_000_000;

    private final JdbcTemplate jdbc;

    public QuestionHistoryService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public QuestionHistoryListResponse list(AuthenticatedUser user, int limit, int offset) {
        if (limit < 1 || limit > MAX_LIMIT || offset < 0 || offset > MAX_OFFSET) {
            throw ApiFailure.invalidRequest();
        }
        List<QuestionHistoryItem> rows = jdbc.query("""
                SELECT id, knowledge_base_id, question_text, status, created_at, finished_at
                  FROM knowflow.questions
                 WHERE owner_user_id = ?
                 ORDER BY created_at DESC, id DESC
                 LIMIT ? OFFSET ?
                """, (result, row) -> new QuestionHistoryItem(
                result.getObject("id", UUID.class),
                result.getObject("knowledge_base_id", UUID.class),
                result.getString("question_text"), result.getString("status"),
                result.getObject("created_at", java.time.OffsetDateTime.class),
                result.getObject("finished_at", java.time.OffsetDateTime.class)),
                user.id(), limit + 1, offset);
        boolean hasMore = rows.size() > limit;
        List<QuestionHistoryItem> items = hasMore
                ? List.copyOf(rows.subList(0, limit)) : rows;
        return new QuestionHistoryListResponse(ApiError.CONTRACT_VERSION,
                items, limit, offset, hasMore);
    }

    public QuestionHistoryDetail get(AuthenticatedUser user, UUID questionId) {
        List<QuestionHistoryDetail> questions = jdbc.query("""
                SELECT id, knowledge_base_id, question_text, status, created_at, finished_at,
                       answer_text, has_answer, failure_code,
                       embedding_model_profile_id, llm_model_profile_id
                  FROM knowflow.questions
                 WHERE id = ? AND owner_user_id = ?
                """, (result, row) -> new QuestionHistoryDetail(
                ApiError.CONTRACT_VERSION, result.getObject("id", UUID.class),
                result.getObject("knowledge_base_id", UUID.class),
                result.getString("question_text"), result.getString("status"),
                result.getObject("created_at", java.time.OffsetDateTime.class),
                result.getObject("finished_at", java.time.OffsetDateTime.class),
                result.getString("answer_text"),
                (Boolean) result.getObject("has_answer"), result.getString("failure_code"),
                result.getString("embedding_model_profile_id"),
                result.getString("llm_model_profile_id"), List.of()), questionId, user.id());
        if (questions.isEmpty()) {
            throw ApiFailure.resourceNotFound();
        }
        QuestionHistoryDetail question = questions.getFirst();
        List<QuestionHistorySource> sources = jdbc.query("""
                SELECT qs.source_id, qs.document_id, qs.content_version_id,
                       qs.index_version_id, qs.chunk_id, qs.locator_kind, qs.source_page,
                       qs.source_start, qs.source_end, qs.quote,
                       CASE
                         WHEN d.status IS DISTINCT FROM 'ACTIVE'
                           OR kb.status IS DISTINCT FROM 'ACTIVE' THEN 'DOCUMENT_DELETED'
                         WHEN iv.id IS NULL OR iv.cleaned_at IS NOT NULL
                           OR iv.id NOT IN (
                               SELECT kept.id FROM knowflow.index_versions kept
                                WHERE kept.document_id = qs.document_id
                                  AND kept.ready_at IS NOT NULL
                                ORDER BY kept.ready_at DESC, kept.id DESC LIMIT 2
                           ) THEN 'VERSION_EXPIRED'
                         ELSE 'AVAILABLE'
                       END AS source_state
                  FROM knowflow.question_sources qs
                  JOIN knowflow.questions q ON q.id = qs.question_id
                   AND q.owner_user_id = qs.owner_user_id
                  LEFT JOIN knowflow.documents d ON d.id = qs.document_id
                   AND d.owner_user_id = qs.owner_user_id
                  LEFT JOIN knowflow.knowledge_bases kb ON kb.id = qs.knowledge_base_id
                   AND kb.owner_user_id = qs.owner_user_id
                  LEFT JOIN knowflow.index_versions iv ON iv.id = qs.index_version_id
                   AND iv.document_id = qs.document_id
                   AND iv.content_version_id = qs.content_version_id
                 WHERE qs.question_id = ? AND qs.owner_user_id = ?
                 ORDER BY qs.created_at, qs.source_id
                """, (result, row) -> {
            String state = result.getString("source_state");
            SourceResponse.Locator locator = "AVAILABLE".equals(state)
                    ? new SourceResponse.Locator(result.getString("locator_kind"),
                    result.getObject("source_page", Integer.class),
                    result.getObject("source_start", Integer.class),
                    result.getObject("source_end", Integer.class),
                    "text_range".equals(result.getString("locator_kind"))
                            ? "unicode_code_point" : null)
                    : null;
            return new QuestionHistorySource(result.getObject("source_id", UUID.class),
                    result.getObject("document_id", UUID.class),
                    result.getObject("content_version_id", UUID.class),
                    result.getObject("index_version_id", UUID.class),
                    result.getObject("chunk_id", UUID.class), state, locator,
                    "AVAILABLE".equals(state) ? result.getString("quote") : null);
        }, questionId, user.id());
        return new QuestionHistoryDetail(question.contractVersion(), question.questionId(),
                question.knowledgeBaseId(), question.question(), question.status(),
                question.createdAt(), question.finishedAt(), question.answer(),
                question.hasAnswer(), question.failureCode(),
                question.embeddingModelProfileId(), question.llmModelProfileId(), sources);
    }

    @Transactional
    public void delete(AuthenticatedUser user, UUID questionId) {
        List<String> statuses = jdbc.query("""
                SELECT status FROM knowflow.questions
                 WHERE id = ? AND owner_user_id = ?
                 FOR UPDATE
                """, (result, row) -> result.getString(1), questionId, user.id());
        if (statuses.isEmpty()) {
            throw ApiFailure.resourceNotFound();
        }
        if ("PROCESSING".equals(statuses.getFirst())) {
            throw ApiFailure.questionInProgress();
        }
        jdbc.update("DELETE FROM knowflow.question_sources WHERE question_id = ?", questionId);
        jdbc.update("DELETE FROM knowflow.question_scope_indexes WHERE question_id = ?", questionId);
        jdbc.update("DELETE FROM knowflow.questions WHERE id = ? AND owner_user_id = ?",
                questionId, user.id());
    }
}
