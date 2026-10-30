package com.knowflow.api.security;

import java.io.IOException;
import java.util.UUID;
import java.util.regex.Pattern;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.filter.OncePerRequestFilter;

public final class RequestIdFilter extends OncePerRequestFilter {
    public static final String ATTRIBUTE = RequestIdFilter.class.getName() + ".requestId";
    public static final String HEADER = "X-Request-ID";
    private static final Pattern SAFE_REQUEST_ID = Pattern.compile(
            "[A-Za-z0-9][A-Za-z0-9._:-]{0,127}");

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain filterChain) throws ServletException, IOException {
        String proposed = request.getHeader(HEADER);
        String requestId = proposed != null && SAFE_REQUEST_ID.matcher(proposed).matches()
                ? proposed : UUID.randomUUID().toString();
        request.setAttribute(ATTRIBUTE, requestId);
        response.setHeader(HEADER, requestId);
        filterChain.doFilter(request, response);
    }
}
