package com.knowflow.api.document;

import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.UUID;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import com.knowflow.api.error.ApiErrorWriter;
import com.knowflow.api.security.AuthenticatedUser;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@Profile("database & storage")
public class DocumentController {
    private static final Pattern BYTE_RANGE = Pattern.compile("bytes=(\\d*)-(\\d*)");
    private final DocumentService documents;
    private final ApiErrorWriter errors;

    public DocumentController(DocumentService documents, ApiErrorWriter errors) {
        this.documents = documents;
        this.errors = errors;
    }

    @PostMapping(path = "/api/v1/knowledge-bases/{knowledgeBaseId}/documents",
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    ResponseEntity<DocumentUploadAccepted> upload(
            @AuthenticationPrincipal AuthenticatedUser user,
            @PathVariable UUID knowledgeBaseId,
            @RequestParam("file") MultipartFile file) {
        DocumentUploadAccepted response = documents.upload(user, knowledgeBaseId, file);
        return ResponseEntity.status(HttpStatus.ACCEPTED)
                .location(URI.create("/api/v1/tasks/" + response.taskId()))
                .body(response);
    }

    @GetMapping("/api/v1/knowledge-bases/{knowledgeBaseId}/documents")
    DocumentListResponse list(
            @AuthenticationPrincipal AuthenticatedUser user,
            @PathVariable UUID knowledgeBaseId,
            @RequestParam(defaultValue = "50") @Min(1) @Max(100) int limit,
            @RequestParam(defaultValue = "0") @Min(0) @Max(1_000_000) int offset) {
        return documents.list(user, knowledgeBaseId, limit, offset);
    }

    @GetMapping("/api/v1/documents/{documentId}")
    DocumentResponse get(@AuthenticationPrincipal AuthenticatedUser user,
                         @PathVariable UUID documentId) {
        return documents.get(user, documentId);
    }

    @DeleteMapping("/api/v1/documents/{documentId}")
    ResponseEntity<Void> delete(@AuthenticationPrincipal AuthenticatedUser user,
                                @PathVariable UUID documentId) {
        documents.delete(user, documentId);
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/api/v1/documents/{documentId}/contents/{contentVersionId}/file")
    void readFile(HttpServletRequest request, HttpServletResponse response,
                  @AuthenticationPrincipal AuthenticatedUser user,
                  @PathVariable UUID documentId, @PathVariable UUID contentVersionId,
                  @org.springframework.web.bind.annotation.RequestHeader(
                          value = HttpHeaders.RANGE, required = false) String range)
            throws java.io.IOException {
        DocumentService.FileContent file = documents.readFile(user, documentId, contentVersionId);
        Range selected = parseRange(range, file.contents().length);
        if (range != null && selected == null) {
            response.setHeader(HttpHeaders.CONTENT_RANGE, "bytes */" + file.contents().length);
            errors.write(request, response, HttpStatus.REQUESTED_RANGE_NOT_SATISFIABLE,
                    "INVALID_REQUEST", "The requested byte range is not satisfiable.");
            return;
        }
        int start = selected == null ? 0 : Math.toIntExact(selected.start());
        int endExclusive = selected == null ? file.contents().length
                : Math.toIntExact(selected.end() + 1);
        response.setStatus(selected == null ? HttpStatus.OK.value() : HttpStatus.PARTIAL_CONTENT.value());
        response.setContentType(contentType(file.format()));
        response.setContentLength(endExclusive - start);
        response.setHeader(HttpHeaders.ACCEPT_RANGES, "bytes");
        response.setHeader(HttpHeaders.CACHE_CONTROL, "no-store");
        response.setHeader("X-Contract-Version", com.knowflow.api.error.ApiError.CONTRACT_VERSION);
        response.setHeader("X-Content-Version-ID", contentVersionId.toString());
        response.setHeader("X-Source-SHA256", file.sha256());
        response.setHeader(HttpHeaders.CONTENT_DISPOSITION,
                org.springframework.http.ContentDisposition.attachment()
                        .filename(file.originalName(), StandardCharsets.UTF_8).build().toString());
        if (selected != null) {
            response.setHeader(HttpHeaders.CONTENT_RANGE, "bytes " + selected.start() + "-"
                    + selected.end() + "/" + file.contents().length);
        }
        response.getOutputStream().write(file.contents(), start, endExclusive - start);
    }

    @GetMapping("/api/v1/tasks/{taskId}")
    TaskStatusResponse getTask(@AuthenticationPrincipal AuthenticatedUser user,
                               @PathVariable UUID taskId) {
        return documents.getTask(user, taskId);
    }

    private static Range parseRange(String header, int size) {
        if (header == null) {
            return null;
        }
        Matcher matcher = BYTE_RANGE.matcher(header);
        if (!matcher.matches() || size == 0 || (matcher.group(1).isEmpty()
                && matcher.group(2).isEmpty())) {
            return null;
        }
        try {
            long start;
            long end;
            if (matcher.group(1).isEmpty()) {
                long suffixLength = Long.parseLong(matcher.group(2));
                if (suffixLength <= 0) {
                    return null;
                }
                start = Math.max(0, size - suffixLength);
                end = size - 1L;
            } else {
                start = Long.parseLong(matcher.group(1));
                end = matcher.group(2).isEmpty() ? size - 1L
                        : Long.parseLong(matcher.group(2));
                if (start >= size || end < start) {
                    return null;
                }
                end = Math.min(end, size - 1L);
            }
            return new Range(start, end);
        } catch (NumberFormatException invalidRange) {
            return null;
        }
    }

    private static String contentType(String format) {
        return switch (format) {
            case "pdf" -> "application/pdf";
            case "md" -> "text/markdown; charset=utf-8";
            default -> "text/plain; charset=utf-8";
        };
    }

    private record Range(long start, long end) {}
}
