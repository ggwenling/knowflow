package com.knowflow.api.knowledgebase;

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
public class KnowledgeBaseService {
    private static final int MAX_LIMIT = 100;
    private static final int MAX_OFFSET = 1_000_000;

    private final JdbcTemplate jdbc;

    public KnowledgeBaseService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public KnowledgeBaseResponse create(AuthenticatedUser user, CreateKnowledgeBaseRequest request) {
        requireCurrentContract(request.contractVersion());
        String name = request.name().strip();
        if (name.isEmpty() || name.length() > 200) {
            throw ApiFailure.invalidRequest();
        }

        UUID id = UUID.randomUUID();
        jdbc.update("""
                INSERT INTO knowflow.knowledge_bases (id, owner_user_id, name)
                VALUES (?, ?, ?)
                """, id, user.id(), name);
        return get(user, id);
    }

    public KnowledgeBaseListResponse list(AuthenticatedUser user, int requestedLimit, int offset) {
        int limit = requestedLimit;
        if (limit < 1 || limit > MAX_LIMIT || offset < 0 || offset > MAX_OFFSET) {
            throw ApiFailure.invalidRequest();
        }

        List<KnowledgeBaseResponse> rows = jdbc.query("""
                SELECT id, name, status, created_at, updated_at
                  FROM knowflow.knowledge_bases
                 WHERE owner_user_id = ? AND status = 'ACTIVE'
                 ORDER BY created_at DESC, id DESC
                 LIMIT ? OFFSET ?
                """, (result, row) -> new KnowledgeBaseResponse(
                ApiError.CONTRACT_VERSION,
                result.getObject("id", UUID.class),
                result.getString("name"),
                result.getString("status"),
                result.getObject("created_at", java.time.OffsetDateTime.class),
                result.getObject("updated_at", java.time.OffsetDateTime.class)),
                user.id(), limit + 1, offset);

        boolean hasMore = rows.size() > limit;
        List<KnowledgeBaseResponse> items = hasMore ? List.copyOf(rows.subList(0, limit)) : rows;
        return new KnowledgeBaseListResponse(ApiError.CONTRACT_VERSION, items, limit, offset, hasMore);
    }

    public KnowledgeBaseResponse get(AuthenticatedUser user, UUID id) {
        List<KnowledgeBaseResponse> rows = jdbc.query("""
                SELECT id, name, status, created_at, updated_at
                  FROM knowflow.knowledge_bases
                 WHERE id = ? AND owner_user_id = ? AND status = 'ACTIVE'
                """, (result, row) -> new KnowledgeBaseResponse(
                ApiError.CONTRACT_VERSION,
                result.getObject("id", UUID.class),
                result.getString("name"),
                result.getString("status"),
                result.getObject("created_at", java.time.OffsetDateTime.class),
                result.getObject("updated_at", java.time.OffsetDateTime.class)),
                id, user.id());
        if (rows.isEmpty()) {
            throw ApiFailure.resourceNotFound();
        }
        return rows.getFirst();
    }

    @Transactional
    public void delete(AuthenticatedUser user, UUID id) {
        int updated = jdbc.update("""
                UPDATE knowflow.knowledge_bases
                   SET status = 'DELETED', deleted_at = CURRENT_TIMESTAMP,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE id = ? AND owner_user_id = ? AND status = 'ACTIVE'
                """, id, user.id());
        if (updated == 0) {
            throw ApiFailure.resourceNotFound();
        }

        jdbc.update("""
                UPDATE knowflow.documents
                   SET status = 'DELETED', deleted_at = CURRENT_TIMESTAMP,
                       updated_at = CURRENT_TIMESTAMP
                 WHERE knowledge_base_id = ? AND owner_user_id = ? AND status = 'ACTIVE'
                """, id, user.id());
        jdbc.update("""
                UPDATE knowflow.indexing_tasks
                   SET status = 'CANCELLED', lease_id = NULL, lease_expires_at = NULL,
                       execution_token_hash = NULL, failure_code = NULL,
                       finished_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                 WHERE knowledge_base_id = ? AND owner_user_id = ?
                   AND status IN ('QUEUED', 'RUNNING')
                """, id, user.id());
    }

    private static void requireCurrentContract(String contractVersion) {
        if (!ApiError.CONTRACT_VERSION.equals(contractVersion)) {
            throw ApiFailure.invalidRequest();
        }
    }
}
