package com.knowflow.api.answer;

import java.util.UUID;

import com.knowflow.api.security.AuthenticatedUser;
import org.springframework.context.annotation.Profile;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Profile("database")
public class SourceController {
    private final SourceService sources;

    public SourceController(SourceService sources) {
        this.sources = sources;
    }

    @GetMapping("/api/v1/sources/{sourceId}")
    SourceResponse get(@AuthenticationPrincipal AuthenticatedUser user,
                       @PathVariable UUID sourceId) {
        return sources.get(user, sourceId);
    }
}
