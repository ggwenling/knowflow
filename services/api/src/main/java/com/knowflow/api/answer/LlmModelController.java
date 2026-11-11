package com.knowflow.api.answer;

import java.util.UUID;

import com.knowflow.api.security.AuthenticatedUser;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController
@Profile("database")
@RequestMapping("/api/v1/llm-models")
class LlmModelController {
    private final LlmModelService models;

    LlmModelController(LlmModelService models) {
        this.models = models;
    }

    @GetMapping
    LlmModelService.Catalog list(@AuthenticationPrincipal AuthenticatedUser user) {
        return models.list(user.id());
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    LlmModelService.Model create(@AuthenticationPrincipal AuthenticatedUser user,
                                 @RequestBody LlmModelService.Input input) {
        return models.save(user.id(), null, input);
    }

    @PutMapping("/{id}")
    LlmModelService.Model edit(@AuthenticationPrincipal AuthenticatedUser user, @PathVariable UUID id,
                               @RequestBody LlmModelService.Input input) {
        return models.save(user.id(), id, input);
    }

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    void delete(@AuthenticationPrincipal AuthenticatedUser user, @PathVariable UUID id) {
        models.delete(user.id(), id);
    }
}
