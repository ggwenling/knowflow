package com.knowflow.api.security;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.List;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public final class InternalSecretAuthenticationFilter extends OncePerRequestFilter {
    private static final String INTERNAL_PATH = "/internal/";
    private static final String BEARER_PREFIX = "Bearer ";
    private final byte[] expectedSecret;

    public InternalSecretAuthenticationFilter(String sharedSecret) {
        this.expectedSecret = sharedSecret.getBytes(StandardCharsets.UTF_8);
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        String path = request.getRequestURI();
        String contextPath = request.getContextPath();
        if (!contextPath.isEmpty() && path.startsWith(contextPath)) {
            path = path.substring(contextPath.length());
        }
        String authorization = request.getHeader("Authorization");
        if (path.startsWith(INTERNAL_PATH) && authorization != null
                && authorization.startsWith(BEARER_PREFIX)) {
            byte[] candidate = authorization.substring(BEARER_PREFIX.length())
                    .getBytes(StandardCharsets.UTF_8);
            if (candidate.length == expectedSecret.length
                    && MessageDigest.isEqual(expectedSecret, candidate)) {
                var authentication = UsernamePasswordAuthenticationToken.authenticated(
                        "internal-ai-service", null,
                        List.of(new SimpleGrantedAuthority("ROLE_INTERNAL_AI")));
                SecurityContextHolder.getContext().setAuthentication(authentication);
            }
        }
        filterChain.doFilter(request, response);
    }
}
