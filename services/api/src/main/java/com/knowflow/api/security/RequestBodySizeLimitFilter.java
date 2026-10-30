package com.knowflow.api.security;

import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.Charset;
import java.util.UUID;

import com.knowflow.api.error.ApiErrorWriter;
import jakarta.servlet.ReadListener;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletInputStream;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletRequestWrapper;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpStatus;
import org.springframework.web.filter.OncePerRequestFilter;

/** Enforces the draft.5 JSON batch cap even for chunked requests without Content-Length. */
public final class RequestBodySizeLimitFilter extends OncePerRequestFilter {
    public static final int MAX_INDEX_BATCH_BYTES = 1_048_576;

    private final ApiErrorWriter errors;

    public RequestBodySizeLimitFilter(ApiErrorWriter errors) {
        this.errors = errors;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    jakarta.servlet.FilterChain chain)
            throws ServletException, IOException {
        if (!"POST".equals(request.getMethod()) || !isIndexBatchPath(request.getRequestURI())) {
            chain.doFilter(request, response);
            return;
        }
        if (request.getContentLengthLong() > MAX_INDEX_BATCH_BYTES) {
            writeLimitError(request, response);
            return;
        }
        byte[] body = request.getInputStream().readNBytes(MAX_INDEX_BATCH_BYTES + 1);
        if (body.length > MAX_INDEX_BATCH_BYTES) {
            writeLimitError(request, response);
            return;
        }
        chain.doFilter(new BufferedRequest(request, body), response);
    }

    private void writeLimitError(HttpServletRequest request, HttpServletResponse response)
            throws IOException {
        errors.write(request, response, HttpStatus.PAYLOAD_TOO_LARGE, "RESOURCE_LIMIT",
                "The index batch exceeds the configured request limit.");
    }

    private static boolean isIndexBatchPath(String path) {
        String prefix = "/internal/v1/tasks/";
        String suffix = "/index-batches";
        if (path == null || !path.startsWith(prefix) || !path.endsWith(suffix)) {
            return false;
        }
        String id = path.substring(prefix.length(), path.length() - suffix.length());
        try {
            UUID.fromString(id);
            return true;
        } catch (IllegalArgumentException malformed) {
            return false;
        }
    }

    private static final class BufferedRequest extends HttpServletRequestWrapper {
        private final byte[] body;

        private BufferedRequest(HttpServletRequest request, byte[] body) {
            super(request);
            this.body = body;
        }

        @Override
        public ServletInputStream getInputStream() {
            ByteArrayInputStream input = new ByteArrayInputStream(body);
            return new ServletInputStream() {
                @Override
                public int read() {
                    return input.read();
                }

                @Override
                public boolean isFinished() {
                    return input.available() == 0;
                }

                @Override
                public boolean isReady() {
                    return true;
                }

                @Override
                public void setReadListener(ReadListener listener) {
                    try {
                        if (input.available() > 0) {
                            listener.onDataAvailable();
                        }
                        if (input.available() == 0) {
                            listener.onAllDataRead();
                        }
                    } catch (IOException failure) {
                        listener.onError(failure);
                    }
                }
            };
        }

        @Override
        public BufferedReader getReader() {
            Charset charset = Charset.forName(getCharacterEncoding() == null
                    ? "UTF-8" : getCharacterEncoding());
            return new BufferedReader(new InputStreamReader(getInputStream(), charset));
        }

        @Override
        public int getContentLength() {
            return body.length;
        }

        @Override
        public long getContentLengthLong() {
            return body.length;
        }
    }
}
