package com.knowflow.api.indexing;

import java.util.UUID;

import com.knowflow.api.error.ApiFailure;
import com.knowflow.api.security.RequestIdFilter;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.context.annotation.Profile;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Profile("database")
public class CompletionController {
    private final CompletionService completions;

    public CompletionController(CompletionService completions) {
        this.completions = completions;
    }

    @PostMapping(path = "/internal/v1/tasks/{taskId}/completion",
            consumes = MediaType.APPLICATION_JSON_VALUE, produces = MediaType.APPLICATION_JSON_VALUE)
    CompletionReceipt complete(HttpServletRequest servletRequest, @PathVariable UUID taskId,
                               @RequestBody CompletionRequest request) {
        Object requestId = servletRequest.getAttribute(RequestIdFilter.ATTRIBUTE);
        if (request.lease() == null || !taskId.equals(request.lease().taskId())
                || !(requestId instanceof String id) || !id.equals(request.requestId())) {
            throw ApiFailure.leaseRejected();
        }
        return completions.complete(taskId, request);
    }
}
