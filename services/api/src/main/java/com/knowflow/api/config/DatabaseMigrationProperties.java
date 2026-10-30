package com.knowflow.api.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "knowflow.database.migration")
public class DatabaseMigrationProperties {
    private String url;
    private String username;
    private String password;

    public String getUrl() {
        return url;
    }

    public void setUrl(String url) {
        this.url = url;
    }

    public String getUsername() {
        return username;
    }

    public void setUsername(String username) {
        this.username = username;
    }

    public String getPassword() {
        return password;
    }

    public void setPassword(String password) {
        this.password = password;
    }

    public void requireValid() {
        if (url == null || !url.startsWith("jdbc:postgresql://")
                || !url.chars().allMatch(character -> character >= 0x21 && character <= 0x7e)
                || containsEmbeddedCredentials(url)) {
            throw new IllegalStateException(
                    "KNOWFLOW_MIGRATION_DATABASE_URL must be a PostgreSQL JDBC URL without credentials");
        }
        if (username == null || username.isBlank()) {
            throw new IllegalStateException("KNOWFLOW_MIGRATION_DATABASE_USERNAME is required");
        }
        if (password == null || password.isBlank()) {
            throw new IllegalStateException("KNOWFLOW_MIGRATION_DATABASE_PASSWORD is required");
        }
    }

    private static boolean containsEmbeddedCredentials(String jdbcUrl) {
        String normalized = jdbcUrl.toLowerCase(java.util.Locale.ROOT);
        return normalized.matches(".*[?&](user|password)=.*");
    }
}
