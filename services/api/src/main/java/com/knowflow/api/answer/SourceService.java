package com.knowflow.api.answer;

import java.util.List;
import java.util.UUID;

import com.knowflow.api.error.ApiError;
import com.knowflow.api.error.ApiFailure;
import com.knowflow.api.security.AuthenticatedUser;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service
@Profile("database")
public class SourceService {
    private final JdbcTemplate jdbc;

    public SourceService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public SourceResponse get(AuthenticatedUser user, UUID sourceId) {
        List<SourceResponse> sources = jdbc.query("""
                SELECT qs.source_id, qs.document_id, qs.content_version_id,
                       qs.index_version_id, qs.chunk_id, qs.locator_kind, qs.source_page,
                       qs.source_start, qs.source_end, qs.quote
                  FROM knowflow.question_sources qs
                  JOIN knowflow.questions q
                    ON q.id = qs.question_id AND q.owner_user_id = qs.owner_user_id
                   AND q.knowledge_base_id = qs.knowledge_base_id AND q.status = 'SUCCEEDED'
                  JOIN knowflow.documents d
                    ON d.id = qs.document_id AND d.knowledge_base_id = qs.knowledge_base_id
                   AND d.owner_user_id = qs.owner_user_id AND d.status = 'ACTIVE'
                  JOIN knowflow.knowledge_bases kb
                    ON kb.id = d.knowledge_base_id AND kb.owner_user_id = d.owner_user_id
                   AND kb.status = 'ACTIVE'
                 WHERE qs.source_id = ? AND qs.owner_user_id = ?
                   AND d.current_content_version_id = qs.content_version_id
                   AND d.active_index_version_id = qs.index_version_id
                """, (result, row) -> new SourceResponse(ApiError.CONTRACT_VERSION,
                result.getObject("source_id", UUID.class),
                result.getObject("document_id", UUID.class),
                result.getObject("content_version_id", UUID.class),
                result.getObject("index_version_id", UUID.class),
                result.getObject("chunk_id", UUID.class),
                new SourceResponse.Locator(result.getString("locator_kind"),
                        result.getObject("source_page", Integer.class),
                        result.getObject("source_start", Integer.class),
                        result.getObject("source_end", Integer.class),
                        "text_range".equals(result.getString("locator_kind"))
                                ? "unicode_code_point" : null),
                result.getString("quote")), sourceId, user.id());
        if (sources.isEmpty()) {
            throw ApiFailure.resourceNotFound();
        }
        return sources.getFirst();
    }
}
