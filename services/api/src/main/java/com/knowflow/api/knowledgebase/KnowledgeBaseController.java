package com.knowflow.api.knowledgebase;

import java.net.URI;
import java.util.UUID;

import com.knowflow.api.security.AuthenticatedUser;
import jakarta.validation.Valid;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Profile("database")
@RequestMapping("/api/v1/knowledge-bases")
public class KnowledgeBaseController {
    private final KnowledgeBaseService knowledgeBases;

    public KnowledgeBaseController(KnowledgeBaseService knowledgeBases) {
        this.knowledgeBases = knowledgeBases;
    }

    @PostMapping
    ResponseEntity<KnowledgeBaseResponse> create(
            @AuthenticationPrincipal AuthenticatedUser user,
            @Valid @RequestBody CreateKnowledgeBaseRequest request) {
        KnowledgeBaseResponse response = knowledgeBases.create(user, request);
        return ResponseEntity.created(URI.create("/api/v1/knowledge-bases/" + response.id()))
                .body(response);
    }

    @GetMapping
    KnowledgeBaseListResponse list(
            @AuthenticationPrincipal AuthenticatedUser user,
            @RequestParam(defaultValue = "50") int limit,
            @RequestParam(defaultValue = "0") int offset) {
        return knowledgeBases.list(user, limit, offset);
    }

    @GetMapping("/{id}")
    KnowledgeBaseResponse get(
            @AuthenticationPrincipal AuthenticatedUser user,
            @PathVariable UUID id) {
        return knowledgeBases.get(user, id);
    }

    @DeleteMapping("/{id}")
    ResponseEntity<Void> delete(
            @AuthenticationPrincipal AuthenticatedUser user,
            @PathVariable UUID id) {
        knowledgeBases.delete(user, id);
        return ResponseEntity.status(HttpStatus.NO_CONTENT).build();
    }
}
