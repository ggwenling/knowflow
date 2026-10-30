package com.knowflow.api.auth;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Base64;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import java.util.UUID;

import com.knowflow.api.error.ApiError;
import com.knowflow.api.error.ApiFailure;
import com.knowflow.api.security.AuthenticatedUser;
import org.springframework.context.annotation.Profile;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Profile("database")
public class AuthService {
    private static final Duration SESSION_LIFETIME = Duration.ofHours(8);
    private static final String DUMMY_PASSWORD = "dummy-account-password-never-issued";
    private static final SecureRandom RANDOM = new SecureRandom();

    private final JdbcTemplate jdbc;
    private final PasswordEncoder passwordEncoder;
    private final Clock clock;
    private final String dummyPasswordHash;

    public AuthService(JdbcTemplate jdbc, PasswordEncoder passwordEncoder, Clock clock) {
        this.jdbc = jdbc;
        this.passwordEncoder = passwordEncoder;
        this.clock = clock;
        this.dummyPasswordHash = passwordEncoder.encode(DUMMY_PASSWORD);
    }

    @Transactional
    public AuthSessionResponse register(RegisterRequest request) {
        requireCurrentContract(request.contractVersion());
        String email = normalizeEmail(request.email());
        String passwordHash = passwordEncoder.encode(request.password());
        UUID userId = UUID.randomUUID();
        try {
            jdbc.update("""
                    INSERT INTO knowflow.users (id, email, password_hash)
                    VALUES (?, ?, ?)
                    """, userId, email, passwordHash);
        } catch (DuplicateKeyException exception) {
            throw ApiFailure.accountCreateRejected();
        }
        return createSession(userId, email);
    }

    @Transactional
    public AuthSessionResponse login(LoginRequest request) {
        requireCurrentContract(request.contractVersion());
        String email = normalizeEmail(request.email());
        List<Credentials> matches = jdbc.query("""
                SELECT id, email, password_hash
                  FROM knowflow.users
                 WHERE LOWER(email) = ?
                 LIMIT 1
                """, (result, row) -> new Credentials(
                result.getObject("id", UUID.class), result.getString("email"),
                result.getString("password_hash")), email);

        Credentials credentials = matches.isEmpty() ? null : matches.getFirst();
        String encodedPassword = credentials == null || credentials.passwordHash() == null
                ? dummyPasswordHash : credentials.passwordHash();
        boolean passwordMatches = passwordEncoder.matches(request.password(), encodedPassword);
        if (credentials == null || credentials.passwordHash() == null || !passwordMatches) {
            throw ApiFailure.unauthenticated();
        }
        return createSession(credentials.userId(), credentials.email());
    }

    public CurrentUserResponse currentUser(AuthenticatedUser user) {
        return new CurrentUserResponse(ApiError.CONTRACT_VERSION, user.id(), user.email());
    }

    @Transactional
    public void logout(AuthenticatedUser user) {
        jdbc.update("""
                UPDATE knowflow.user_sessions
                   SET revoked_at = CURRENT_TIMESTAMP
                 WHERE token_sha256 = ? AND revoked_at IS NULL
                """, user.tokenSha256());
    }

    private AuthSessionResponse createSession(UUID userId, String email) {
        byte[] tokenBytes = new byte[32];
        RANDOM.nextBytes(tokenBytes);
        String token = Base64.getUrlEncoder().withoutPadding().encodeToString(tokenBytes);
        String tokenSha256 = sha256(token);
        OffsetDateTime expiresAt = OffsetDateTime.ofInstant(
                clock.instant().plus(SESSION_LIFETIME), ZoneOffset.UTC);

        jdbc.update("""
                INSERT INTO knowflow.user_sessions (token_sha256, user_id, expires_at)
                VALUES (?, ?, ?)
                """, tokenSha256, userId, expiresAt);

        return new AuthSessionResponse(ApiError.CONTRACT_VERSION, userId, email,
                token, "Bearer", expiresAt);
    }

    private static void requireCurrentContract(String contractVersion) {
        if (!ApiError.CONTRACT_VERSION.equals(contractVersion)) {
            throw ApiFailure.invalidRequest();
        }
    }

    private static String normalizeEmail(String email) {
        return email.strip().toLowerCase(Locale.ROOT);
    }

    public static String sha256(String value) {
        try {
            return HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256")
                            .digest(value.getBytes(StandardCharsets.US_ASCII)));
        } catch (java.security.NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 is unavailable", exception);
        }
    }

    private record Credentials(UUID userId, String email, String passwordHash) {
    }
}
