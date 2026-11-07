package com.knowflow.api.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "knowflow.database.migration")
public class DatabaseMigrationProperties {
    private String url;
    private String username;
    private String password;
    private String target;

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

    public String getTarget() {
        return target;
    }

    public void setTarget(String target) {
        this.target = target;
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
        if (target != null && !target.isBlank()
                && !target.matches("^(0|[1-9][0-9]*)(\\.(0|[1-9][0-9]*))*$")) {
            throw new IllegalStateException(
                    "KNOWFLOW_MIGRATION_TARGET must be a numeric dotted version such as 2 or 2.1");
        }
    }

    private static boolean containsEmbeddedCredentials(String jdbcUrl) {
        String normalized = jdbcUrl.toLowerCase(java.util.Locale.ROOT);
        return normalized.matches(".*[?&](user|password)=.*");
    }
}
