package com.knowflow.api.answer;

import org.springframework.context.annotation.Profile;
import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

@Service
@Profile("database")
public class QuestionRecoveryService {
    private final JdbcTemplate jdbc;

    public QuestionRecoveryService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Scheduled(fixedDelayString = "${knowflow.question.recovery-delay-millis:1000}")
    public void recoverExpiredQuestions() {
        try {
            jdbc.update("""
                    WITH expired AS (
                        SELECT id
                          FROM knowflow.questions
                         WHERE status = 'PROCESSING'
                           AND deadline_at < clock_timestamp() - INTERVAL '2 seconds'
                         ORDER BY deadline_at, id
                         LIMIT 100
                         FOR UPDATE SKIP LOCKED
                    )
                    UPDATE knowflow.questions q
                       SET status = 'FAILED', failure_code = 'PROCESSING_TIMEOUT',
                           answer_text = NULL, has_answer = NULL,
                           finished_at = clock_timestamp(), updated_at = clock_timestamp()
                      FROM expired
                     WHERE q.id = expired.id AND q.status = 'PROCESSING'
                    """);
        } catch (DataAccessException unavailable) {
            // A later scheduled pass retries recovery after the database returns.
        }
    }
}
