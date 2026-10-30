package com.knowflow.api.security;

import java.io.IOException;
import java.util.List;
import java.util.regex.Pattern;

import com.knowflow.api.auth.AuthService;
import com.knowflow.api.error.ApiErrorWriter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.dao.DataAccessException;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

final class BearerSessionAuthenticationFilter extends OncePerRequestFilter {
    private static final String API_PATH = "/api/";
    private static final String BEARER_PREFIX = "Bearer ";
    private static final Pattern OPAQUE_TOKEN = Pattern.compile("[A-Za-z0-9_-]{43}");

    private final JdbcTemplate jdbc;
    private final ApiErrorWriter errors;

    BearerSessionAuthenticationFilter(JdbcTemplate jdbc, ApiErrorWriter errors) {
        this.jdbc = jdbc;
        this.errors = errors;
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
        if (path.startsWith(API_PATH) && authorization != null
                && authorization.startsWith(BEARER_PREFIX)) {
            String token = authorization.substring(BEARER_PREFIX.length());
            if (OPAQUE_TOKEN.matcher(token).matches()) {
                try {
                    authenticate(token);
                } catch (DataAccessException exception) {
                    errors.write(request, response, HttpStatus.INTERNAL_SERVER_ERROR,
                            "INTERNAL_ERROR", "The request could not be processed.");
                    return;
                }
            }
        }
        filterChain.doFilter(request, response);
    }

    private void authenticate(String token) {
        String tokenHash = AuthService.sha256(token);
        List<AuthenticatedUser> users = jdbc.query("""
                SELECT u.id, u.email, s.token_sha256
                  FROM knowflow.user_sessions s
                  JOIN knowflow.users u ON u.id = s.user_id
                 WHERE s.token_sha256 = ?
                   AND s.revoked_at IS NULL
                   AND s.expires_at > CURRENT_TIMESTAMP
                """, (result, row) -> new AuthenticatedUser(
                result.getObject("id", java.util.UUID.class),
                result.getString("email"), result.getString("token_sha256")), tokenHash);

        if (!users.isEmpty()) {
            var authentication = UsernamePasswordAuthenticationToken.authenticated(
                    users.getFirst(), null, List.of(new SimpleGrantedAuthority("ROLE_USER")));
            SecurityContextHolder.getContext().setAuthentication(authentication);
        }
    }
}
