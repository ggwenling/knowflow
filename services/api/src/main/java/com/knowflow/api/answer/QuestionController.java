package com.knowflow.api.answer;

import java.util.UUID;

import com.knowflow.api.security.AuthenticatedUser;
import org.springframework.context.annotation.Profile;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Profile("database")
public class QuestionController {
    private final QuestionService questions;

    public QuestionController(QuestionService questions) {
        this.questions = questions;
    }

    @PostMapping("/api/v1/knowledge-bases/{knowledgeBaseId}/questions")
    AnswerResponse ask(@AuthenticationPrincipal AuthenticatedUser user,
                       @PathVariable UUID knowledgeBaseId,
                       @RequestBody PublicQuestion question) {
        return questions.ask(user, knowledgeBaseId, question);
    }
}
