package com.knowflow.api.indexing;

import java.util.UUID;

import com.knowflow.api.error.ApiFailure;
import com.knowflow.api.security.RequestIdFilter;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Profile("database & storage")
public class InternalIndexingController {
    private final SourceReadService sources;

    public InternalIndexingController(SourceReadService sources) {
        this.sources = sources;
    }

    @PostMapping(path = "/internal/v1/tasks/{taskId}/source",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    ResponseEntity<byte[]> readSource(HttpServletRequest servletRequest,
                                      @PathVariable UUID taskId,
                                      @RequestBody SourceReadRequest request) {
        Object requestId = servletRequest.getAttribute(RequestIdFilter.ATTRIBUTE);
        if (request.lease() == null || !taskId.equals(request.lease().taskId())
                || !(requestId instanceof String id) || !id.equals(request.requestId())) {
            throw ApiFailure.leaseRejected();
        }
        SourceReadService.SourceFile source = sources.read(taskId, request);
        String contentType = "pdf".equals(source.format())
                ? "application/pdf" : "text/plain; charset=utf-8";
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType(contentType))
                .contentLength(source.contents().length)
                .header("X-Contract-Version", source.contractVersion())
                .header("X-Task-ID", source.taskId().toString())
                .header("X-Document-ID", source.documentId().toString())
                .header("X-Content-Version-ID", source.contentVersionId().toString())
                .header("X-Source-Format", source.format())
                .header("X-Source-SHA256", source.sha256())
                .header(HttpHeaders.CACHE_CONTROL, "no-store")
                .body(source.contents());
    }
}
